import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.database import VALID_STATUSES, connect, init_db
from app.hh_client import HHClient
from app.scoring import load_profile, score_vacancy
from app.settings import get_settings

DEFAULT_QUERIES = [
    'AI Creator', 'нейрокреатор', 'Generative Visual Designer',
    'AI Video Creator', 'AI Content Producer', 'Visual Concept Designer',
    'Creative Technologist', 'Junior AI Art Director',
    'Creative Producer', 'Content Designer', 'Digital Designer'
]

app = FastAPI(title='Silvana Career Agent', version='0.3.0')
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

class SearchPayload(BaseModel):
    query: Optional[str] = None
    area: int = 1
    per_page: int = 30

class StatusPayload(BaseModel):
    status: str

class BrowserVacancyPayload(BaseModel):
    vacancy_id: str
    cover_letter: Optional[str] = None

@app.on_event('startup')
def startup():
    init_db()

@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})

@app.get('/health')
def health():
    return {'status': 'ok', 'version': '0.3.0'}

def ser(row):
    data = dict(row)
    for key in ('match_reasons', 'red_flags', 'recommended_projects'):
        try:
            data[key] = json.loads(data.get(key) or '[]')
        except Exception:
            data[key] = []
    return data

def get_vacancy(vacancy_id: str):
    with connect() as conn:
        row = conn.execute('SELECT * FROM vacancies WHERE id=?', (vacancy_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Vacancy not found')
    return ser(row)

def default_cover_letter(v):
    projects = ', '.join(v.get('recommended_projects') or [])
    return (
        f"Здравствуйте! Меня заинтересовала вакансия «{v['name']}» в {v.get('employer') or 'вашей компании'}. "
        "Я работаю на стыке AI-креатива, визуального концептинга и AI-video production: "
        "разрабатываю key visual, moodboard и storyboard, создаю генеративные визуалы и видео "
        "с помощью Midjourney, Seedance, Veo, Kling и ChatGPT. "
        "У меня есть коммерческий опыт B2B-контента, web-дизайна и упаковки сложных продуктов "
        "в понятную визуальную коммуникацию. "
        + (f"Для этой роли могу показать проекты: {projects}. " if projects else "")
        + "Буду рада обсудить задачи и показать релевантные кейсы."
    )

async def run_browser(action: str, payload: dict | None = None):
    proc = await asyncio.create_subprocess_exec(
        'node', 'app/browser_agent.js', action,
        json.dumps(payload or {}, ensure_ascii=False),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(Path.cwd())
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=70)
    text = stdout.decode('utf-8', errors='replace').strip()
    try:
        result = json.loads(text)
    except Exception:
        raise HTTPException(500, f'Browser agent returned invalid response: {text or stderr.decode(errors="replace")}')
    if not result.get('ok'):
        raise HTTPException(409, result.get('error', 'Browser automation failed'))
    return result

@app.get('/api/vacancies')
def vacancies(status: Optional[str] = None, min_score: int = 0, limit: int = 200):
    q = 'SELECT * FROM vacancies WHERE match_score>=?'
    p = [min_score]
    if status:
        q += ' AND status=?'
        p.append(status)
    q += ' ORDER BY match_score DESC,published_at DESC LIMIT ?'
    p.append(min(limit, 500))
    with connect() as c:
        rows = c.execute(q, p).fetchall()
    return {'items': [ser(r) for r in rows]}

@app.get('/api/stats')
def stats():
    with connect() as c:
        total = c.execute('SELECT COUNT(*) FROM vacancies').fetchone()[0]
        g = {r['status']: r['count'] for r in c.execute('SELECT status,COUNT(*) count FROM vacancies GROUP BY status').fetchall()}
    return {'total': total, 'new': g.get('new', 0), 'shortlisted': g.get('shortlisted', 0), 'applied': g.get('applied', 0), 'interview': g.get('interview', 0), 'offer': g.get('offer', 0)}

@app.post('/api/search')
async def search(payload: SearchPayload):
    profile = load_profile()
    queries = [payload.query] if payload.query else DEFAULT_QUERIES
    processed = saved = 0
    with connect() as c:
        for query in queries:
            result = await HHClient().search_vacancies(query, area=payload.area, per_page=payload.per_page)
            for item in result.get('items', []):
                processed += 1
                sc = score_vacancy(item, profile)
                sal = item.get('salary') or {}
                emp = (item.get('employer') or {}).get('name')
                area = (item.get('area') or {}).get('name')
                schedule = (item.get('schedule') or {}).get('name')
                employment = (item.get('employment') or {}).get('name')
                old = c.execute('SELECT status FROM vacancies WHERE id=?', (item['id'],)).fetchone()
                status = old['status'] if old else 'new'
                c.execute(
                    '''INSERT OR REPLACE INTO vacancies(id,name,employer,salary_from,salary_to,currency,area,schedule,employment,url,published_at,match_score,match_reasons,red_flags,recommended_projects,status,raw_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)''',
                    (item['id'], item.get('name'), emp, sal.get('from'), sal.get('to'), sal.get('currency'), area, schedule, employment, item.get('alternate_url'), item.get('published_at'), sc['score'], json.dumps(sc['reasons'], ensure_ascii=False), json.dumps(sc['red_flags'], ensure_ascii=False), json.dumps(sc['projects'], ensure_ascii=False), status, json.dumps(item, ensure_ascii=False))
                )
                saved += 1
        c.commit()
    return {'processed': processed, 'saved': saved, 'queries': queries}

@app.patch('/api/vacancies/{vacancy_id}/status')
def change(vacancy_id: str, payload: StatusPayload):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(400, 'Unknown status')
    with connect() as c:
        cur = c.execute('UPDATE vacancies SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (payload.status, vacancy_id))
        c.commit()
        if not cur.rowcount:
            raise HTTPException(404, 'Vacancy not found')
    return {'id': vacancy_id, 'status': payload.status}

@app.get('/api/browser/status')
async def browser_status():
    return await run_browser('status')

@app.post('/api/browser/open')
async def browser_open(payload: BrowserVacancyPayload):
    vacancy = get_vacancy(payload.vacancy_id)
    return await run_browser('open', {'url': vacancy['url']})

@app.post('/api/browser/prepare')
async def browser_prepare(payload: BrowserVacancyPayload):
    vacancy = get_vacancy(payload.vacancy_id)
    cover_letter = payload.cover_letter or default_cover_letter(vacancy)
    result = await run_browser('prepare', {'url': vacancy['url'], 'cover_letter': cover_letter})
    result['cover_letter'] = cover_letter
    return result

if __name__ == '__main__':
    import uvicorn
    s = get_settings()
    uvicorn.run('app.main:app', host=s.app_host, port=s.app_port)
