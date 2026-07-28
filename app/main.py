import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.database import (
    VALID_STATUSES,
    connect,
    get_meta,
    init_db,
)
from app.settings import get_settings
from app.workflow import enrich_and_prepare, run_browser


app = FastAPI(title='Silvana Career Agent', version='0.6.0')
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')


class SearchPayload(BaseModel):
    query: Optional[str] = None
    area: int = 1
    per_page: int = 30


class StatusPayload(BaseModel):
    status: str


@app.on_event('startup')
def startup():
    init_db()


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        'index.html',
        {'request': request},
    )


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'version': '0.6.0',
        'last_worker_run': get_meta('last_worker_run'),
    }


def serialize(row):
    data = dict(row)
    for key in (
        'match_reasons',
        'red_flags',
        'recommended_projects',
    ):
        try:
            data[key] = json.loads(data.get(key) or '[]')
        except Exception:
            data[key] = []
    return data


def vacancy_or_404(vacancy_id):
    with connect() as connection:
        row = connection.execute(
            'SELECT * FROM vacancies WHERE id=?',
            (vacancy_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, 'Vacancy not found')
    return serialize(row)


def check_token(token):
    expected = get_settings().career_review_token
    if not expected or token != expected:
        raise HTTPException(403, 'Invalid review token')


@app.get('/api/vacancies')
def vacancies(
    status: Optional[str] = None,
    min_score: int = 0,
    limit: int = 200,
):
    query = 'SELECT * FROM vacancies WHERE match_score>=?'
    params = [min_score]
    if status:
        query += ' AND status=?'
        params.append(status)
    query += (
        ' ORDER BY CASE WHEN status="ready" THEN 0 ELSE 1 END,'
        ' match_score DESC,created_at DESC LIMIT ?'
    )
    params.append(min(limit, 500))

    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return {'items': [serialize(row) for row in rows]}


@app.get('/api/stats')
def stats():
    with connect() as connection:
        total = connection.execute(
            'SELECT COUNT(*) FROM vacancies'
        ).fetchone()[0]
        grouped = {
            row['status']: row['count']
            for row in connection.execute(
                '''SELECT status,COUNT(*) count
                FROM vacancies GROUP BY status'''
            ).fetchall()
        }
    return {
        'total': total,
        'new': grouped.get('new', 0),
        'ready': grouped.get('ready', 0),
        'applied': grouped.get('applied', 0),
        'interview': grouped.get('interview', 0),
        'offer': grouped.get('offer', 0),
    }


@app.post('/api/search')
async def search(payload: SearchPayload):
    queries = [payload.query] if payload.query else ['AI Creator']
    processed = 0
    saved = 0

    with connect() as connection:
        for query in queries:
            result = await run_browser(
                'search',
                {
                    'query': query,
                    'area': payload.area,
                    'per_page': payload.per_page,
                },
            )
            for item in result.get('items', []):
                processed += 1
                salary = item.get('salary') or {}
                employer = (item.get('employer') or {}).get('name')
                area = (item.get('area') or {}).get('name')
                schedule = (item.get('schedule') or {}).get('name')
                employment = (item.get('employment') or {}).get('name')

                connection.execute(
                    '''INSERT INTO vacancies(
                    id,name,employer,salary_from,salary_to,currency,
                    area,schedule,employment,url,published_at,status,
                    raw_json,source_query,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    employer=excluded.employer,
                    salary_from=excluded.salary_from,
                    salary_to=excluded.salary_to,
                    currency=excluded.currency,
                    area=excluded.area,
                    schedule=excluded.schedule,
                    employment=excluded.employment,
                    url=excluded.url,
                    raw_json=excluded.raw_json,
                    source_query=excluded.source_query,
                    updated_at=CURRENT_TIMESTAMP''',
                    (
                        item['id'],
                        item.get('name'),
                        employer,
                        salary.get('from'),
                        salary.get('to'),
                        salary.get('currency'),
                        area,
                        schedule,
                        employment,
                        item.get('alternate_url'),
                        item.get('published_at'),
                        'new',
                        json.dumps(item, ensure_ascii=False),
                        query,
                    ),
                )
                saved += 1
        connection.commit()

    return {
        'processed': processed,
        'saved': saved,
        'queries': queries,
        'source': 'authorized_browser',
    }


@app.post('/api/vacancies/{vacancy_id}/prepare')
async def prepare_vacancy(vacancy_id: str):
    vacancy_or_404(vacancy_id)
    try:
        return await enrich_and_prepare(vacancy_id, force=True)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.patch('/api/vacancies/{vacancy_id}/status')
def change_status(vacancy_id: str, payload: StatusPayload):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(400, 'Unknown status')

    with connect() as connection:
        cursor = connection.execute(
            '''UPDATE vacancies
            SET status=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?''',
            (payload.status, vacancy_id),
        )
        connection.commit()

    if not cursor.rowcount:
        raise HTTPException(404, 'Vacancy not found')
    return {'id': vacancy_id, 'status': payload.status}


@app.get('/api/browser/status')
async def browser_status():
    return await run_browser('status')


@app.get('/review/{vacancy_id}')
async def review(vacancy_id: str, token: str):
    check_token(token)
    vacancy = vacancy_or_404(vacancy_id)

    focused = await run_browser(
        'focus',
        {
            'vacancy_id': vacancy_id,
            'prepared_url': vacancy.get('prepared_url'),
        },
    )

    if not focused.get('found'):
        await enrich_and_prepare(vacancy_id, force=True)
        await run_browser(
            'focus',
            {'vacancy_id': vacancy_id},
        )

    return RedirectResponse(
        get_settings().career_browser_url,
        status_code=302,
    )


@app.get('/decision/{vacancy_id}/{status}')
def decision(vacancy_id: str, status: str, token: str):
    check_token(token)
    if status not in {'ignored'}:
        raise HTTPException(400, 'Unsupported decision')

    with connect() as connection:
        cursor = connection.execute(
            '''UPDATE vacancies
            SET status=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?''',
            (status, vacancy_id),
        )
        connection.commit()

    if not cursor.rowcount:
        raise HTTPException(404, 'Vacancy not found')

    return HTMLResponse(
        '<!doctype html><meta charset="utf-8">'
        '<style>body{font-family:Arial;padding:40px}</style>'
        '<h2>Вакансия пропущена</h2>'
        '<p>Она больше не занимает место в очереди.</p>'
    )


if __name__ == '__main__':
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        'app.main:app',
        host=settings.app_host,
        port=settings.app_port,
    )
