import asyncio
import json
from pathlib import Path

from app.database import connect
from app.letter_writer import build_cover_letter
from app.scoring import load_profile, score_vacancy
from app.settings import get_settings


async def run_browser(action, payload=None, timeout=120):
    process = await asyncio.create_subprocess_exec(
        'node',
        'app/browser_agent.js',
        action,
        json.dumps(payload or {}, ensure_ascii=False),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(Path.cwd()),
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        raise RuntimeError(
            f'Браузерная операция {action} превысила {timeout} секунд'
        )

    text = stdout.decode('utf-8', errors='replace').strip()
    err = stderr.decode('utf-8', errors='replace').strip()

    try:
        result = json.loads(text)
    except Exception as exc:
        raise RuntimeError(
            f'Некорректный ответ браузера: {text or err}'
        ) from exc

    if not result.get('ok'):
        raise RuntimeError(result.get('error', 'Browser action failed'))
    return result


def row_to_vacancy(row):
    data = dict(row)
    raw = {}
    try:
        raw = json.loads(data.get('raw_json') or '{}')
    except Exception:
        raw = {}

    raw.update({
        'id': data.get('id'),
        'name': data.get('name'),
        'employer': {'name': data.get('employer') or ''},
        'salary': {
            'from': data.get('salary_from'),
            'to': data.get('salary_to'),
            'currency': data.get('currency'),
        } if data.get('salary_from') or data.get('salary_to') else None,
        'area': {'name': data.get('area') or ''},
        'schedule': {'name': data.get('schedule') or ''},
        'employment': {'name': data.get('employment') or ''},
        'alternate_url': data.get('url'),
        'full_description': data.get('full_description') or '',
    })
    return raw


def hard_block(red_flags):
    text = ' '.join(red_flags or []).lower()
    return any(term in text for term in (
        'обязательный переезд',
        'готовность к переезду',
        'командиров',
        'менеджер по продажам',
        'sales manager',
        'backend',
        'python developer',
        'java developer',
    ))


async def enrich_and_prepare(vacancy_id, force=False):
    settings = get_settings()
    profile = load_profile()

    with connect() as connection:
        row = connection.execute(
            'SELECT * FROM vacancies WHERE id=?',
            (vacancy_id,),
        ).fetchone()
    if not row:
        raise RuntimeError('Vacancy not found')

    vacancy = row_to_vacancy(row)
    details = await run_browser(
        'details',
        {'url': vacancy['alternate_url']},
    )

    vacancy['full_description'] = details.get('description') or ''
    vacancy['snippet'] = {
        'requirement': vacancy['full_description'],
        'responsibility': '',
    }
    scoring = score_vacancy(vacancy, profile)
    letter = build_cover_letter(vacancy, profile)

    with connect() as connection:
        connection.execute(
            '''UPDATE vacancies SET
            full_description=?,
            match_score=?,
            match_reasons=?,
            red_flags=?,
            recommended_projects=?,
            cover_letter=?,
            updated_at=CURRENT_TIMESTAMP
            WHERE id=?''',
            (
                vacancy['full_description'],
                scoring['score'],
                json.dumps(scoring['reasons'], ensure_ascii=False),
                json.dumps(scoring['red_flags'], ensure_ascii=False),
                json.dumps(scoring['projects'], ensure_ascii=False),
                letter,
                vacancy_id,
            ),
        )
        connection.commit()

    if (
        not force
        and scoring['score'] < settings.auto_prepare_min_score
    ):
        note = (
            f"Score {scoring['score']} ниже "
            f"{settings.auto_prepare_min_score}"
        )
        with connect() as connection:
            connection.execute(
                '''UPDATE vacancies SET
                preparation_status='below_threshold',
                preparation_note=?,
                updated_at=CURRENT_TIMESTAMP
                WHERE id=?''',
                (note, vacancy_id),
            )
            connection.commit()
        return {
            'status': 'below_threshold',
            'note': note,
            'score': scoring['score'],
            'letter': letter,
        }

    if details.get('archived') or not details.get('canRespond'):
        note = 'Вакансия закрыта или отклик недоступен.'
        with connect() as connection:
            connection.execute(
                '''UPDATE vacancies SET
                preparation_status='unavailable',
                preparation_note=?,
                updated_at=CURRENT_TIMESTAMP
                WHERE id=?''',
                (note, vacancy_id),
            )
            connection.commit()
        return {
            'status': 'unavailable',
            'note': note,
            'score': scoring['score'],
            'letter': letter,
        }

    if hard_block(scoring.get('red_flags')):
        note = 'Автоподготовка остановлена из-за жёсткого красного флага.'
        with connect() as connection:
            connection.execute(
                '''UPDATE vacancies SET
                preparation_status='blocked',
                preparation_note=?,
                updated_at=CURRENT_TIMESTAMP
                WHERE id=?''',
                (note, vacancy_id),
            )
            connection.commit()
        return {
            'status': 'blocked',
            'note': note,
            'score': scoring['score'],
            'letter': letter,
        }

    result = await run_browser(
        'prepare',
        {
            'url': vacancy['alternate_url'],
            'cover_letter': letter,
            'resume_title': settings.hh_resume_title,
        },
    )

    preparation_status = (
        'needs_manual'
        if result.get('needsManual')
        else 'ready_to_review'
    )
    status = 'shortlisted' if result.get('needsManual') else 'ready'

    with connect() as connection:
        connection.execute(
            '''UPDATE vacancies SET
            preparation_status=?,
            preparation_note=?,
            prepared_url=?,
            prepared_at=CURRENT_TIMESTAMP,
            status=?,
            updated_at=CURRENT_TIMESTAMP
            WHERE id=?''',
            (
                preparation_status,
                result.get('note') or '',
                result.get('preparedUrl') or '',
                status,
                vacancy_id,
            ),
        )
        connection.commit()

    return {
        'status': preparation_status,
        'score': scoring['score'],
        'letter': letter,
        'result': result,
    }
