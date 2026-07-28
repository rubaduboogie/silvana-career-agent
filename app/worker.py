import asyncio
import json
import random
import sys
from datetime import datetime, timezone

from app.database import connect, get_meta, init_db, set_meta
from app.settings import get_settings
from app.telegram_notifier import TelegramError, escape, send_message
from app.workflow import enrich_and_prepare, run_browser


SEARCH_QUERIES = [
    'AI Creator',
    'нейрокреатор',
    'AI Video Creator',
    'Generative Visual Designer',
    'AI Content Producer',
    'Visual Concept Designer',
    'Creative Technologist',
    'Junior AI Art Director',
    'Creative Producer',
]


def save_search_item(connection, item, query):
    salary = item.get('salary') or {}
    employer = (item.get('employer') or {}).get('name')
    area = (item.get('area') or {}).get('name')
    schedule = (item.get('schedule') or {}).get('name')
    employment = (item.get('employment') or {}).get('name')

    old = connection.execute(
        'SELECT status FROM vacancies WHERE id=?',
        (item['id'],),
    ).fetchone()
    status = old['status'] if old else 'new'

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
        published_at=excluded.published_at,
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
            status,
            json.dumps(item, ensure_ascii=False),
            query,
        ),
    )
    return old is None


def salary_text(row):
    parts = []
    if row['salary_from']:
        parts.append(f"от {row['salary_from']:,}".replace(',', ' '))
    if row['salary_to']:
        parts.append(f"до {row['salary_to']:,}".replace(',', ' '))
    currency = '₽' if row['currency'] == 'RUR' else (row['currency'] or '')
    return f"{' '.join(parts)} {currency}".strip() or 'не указана'


def review_url(vacancy_id):
    settings = get_settings()
    return (
        f'{settings.career_agent_url}/review/{vacancy_id}'
        f'?token={settings.career_review_token}'
    )


def ignore_url(vacancy_id):
    settings = get_settings()
    return (
        f'{settings.career_agent_url}/decision/{vacancy_id}/ignored'
        f'?token={settings.career_review_token}'
    )


def notify_ready(vacancy_id, result):
    with connect() as connection:
        row = connection.execute(
            'SELECT * FROM vacancies WHERE id=?',
            (vacancy_id,),
        ).fetchone()

    letter = result.get('letter') or row['cover_letter'] or ''
    preview = letter[:650]
    if len(letter) > 650:
        preview += '…'

    manual = result['status'] == 'needs_manual'
    heading = (
        '🟡 <b>Отклик почти подготовлен</b>'
        if manual else
        '✅ <b>Отклик подготовлен</b>'
    )
    instruction = (
        'Нужно проверить дополнительные поля или выбор резюме.'
        if manual else
        'Сопроводительное вставлено. Финальная отправка не нажата.'
    )

    text = (
        f'{heading}\n\n'
        f'<b>{escape(row["name"])}</b>\n'
        f'{escape(row["employer"] or "")}\n'
        f'🎯 Match Score: <b>{row["match_score"]}/100</b>\n'
        f'💰 {escape(salary_text(row))}\n\n'
        f'{escape(instruction)}\n\n'
        f'<b>Сопроводительное</b>\n'
        f'{escape(preview)}'
    )

    buttons = [
        [{
            'text': 'Проверить и отправить',
            'url': review_url(vacancy_id),
        }],
        [
            {
                'text': 'Вакансия',
                'url': row['url'],
            },
            {
                'text': 'Пропустить',
                'url': ignore_url(vacancy_id),
            },
        ],
    ]
    send_message(text, buttons)

    with connect() as connection:
        connection.execute(
            '''UPDATE vacancies
            SET telegram_notified_at=CURRENT_TIMESTAMP
            WHERE id=?''',
            (vacancy_id,),
        )
        connection.commit()


def notify_error_once(message):
    fingerprint = message[:500]
    previous = get_meta('last_worker_error')
    if fingerprint == previous:
        return

    try:
        send_message(
            '⚠️ <b>Career Agent требует внимания</b>\n\n'
            f'{escape(message)}\n\n'
            'При капче открой облачный HH-браузер.'
        )
        set_meta('last_worker_error', fingerprint)
    except TelegramError:
        pass


async def search_and_prepare():
    settings = get_settings()
    init_db()

    new_ids = []
    seen = set()

    with connect() as connection:
        for index, query in enumerate(SEARCH_QUERIES):
            result = await run_browser(
                'search',
                {'query': query, 'area': 1, 'per_page': 20},
            )

            for item in result.get('items', []):
                vacancy_id = item.get('id')
                if not vacancy_id or vacancy_id in seen:
                    continue
                seen.add(vacancy_id)
                if save_search_item(connection, item, query):
                    new_ids.append(vacancy_id)

            connection.commit()
            if index < len(SEARCH_QUERIES) - 1:
                await asyncio.sleep(random.uniform(4.0, 7.0))

    with connect() as connection:
        ready_count = connection.execute(
            '''SELECT COUNT(*) FROM vacancies
            WHERE preparation_status IN (
                'ready_to_review','needs_manual'
            ) AND status NOT IN (
                'applied','ignored','rejected'
            )'''
        ).fetchone()[0]

        backlog = [
            row['id']
            for row in connection.execute(
                '''SELECT id FROM vacancies
                WHERE status='new'
                AND COALESCE(preparation_status,'')=''
                ORDER BY created_at DESC
                LIMIT 20'''
            ).fetchall()
        ]

    candidates = list(dict.fromkeys(new_ids + backlog))
    available_slots = max(0, settings.max_ready_to_review - ready_count)
    max_prepare = min(settings.max_prepare_per_run, available_slots)
    prepared = 0

    for vacancy_id in candidates:
        if prepared >= max_prepare:
            break

        try:
            result = await enrich_and_prepare(vacancy_id)
        except Exception as exc:
            with connect() as connection:
                connection.execute(
                    '''UPDATE vacancies SET
                    preparation_status='error',
                    preparation_note=?,
                    updated_at=CURRENT_TIMESTAMP
                    WHERE id=?''',
                    (str(exc)[:1000], vacancy_id),
                )
                connection.commit()
            if 'провер' in str(exc).lower() or 'captcha' in str(exc).lower():
                raise
            continue

        if result.get('status') == 'below_threshold':
            continue

        if result['status'] in ('ready_to_review', 'needs_manual'):
            notify_ready(vacancy_id, result)
            prepared += 1

    set_meta('last_worker_error', '')
    set_meta(
        'last_worker_run',
        datetime.now(timezone.utc).isoformat(),
    )
    print(json.dumps({
        'status': 'ok',
        'unique_found': len(seen),
        'new_found': len(new_ids),
        'prepared_and_notified': prepared,
        'ready_queue_before_run': ready_count,
    }, ensure_ascii=False))


def main():
    try:
        asyncio.run(search_and_prepare())
    except Exception as exc:
        message = str(exc)
        notify_error_once(message)
        print(
            json.dumps(
                {'status': 'error', 'error': message},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == '__main__':
    main()
