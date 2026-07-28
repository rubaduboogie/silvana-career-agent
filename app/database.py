import sqlite3
from pathlib import Path

from app.settings import get_settings


VALID_STATUSES = {
    'new', 'shortlisted', 'ready', 'applied', 'interview',
    'test_task', 'offer', 'rejected', 'ignored'
}


def connect():
    path = Path(get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _columns(connection, table):
    return {
        row['name']
        for row in connection.execute(f'PRAGMA table_info({table})').fetchall()
    }


def _ensure_column(connection, table, name, declaration):
    if name not in _columns(connection, table):
        connection.execute(
            f'ALTER TABLE {table} ADD COLUMN {name} {declaration}'
        )


def init_db():
    with connect() as connection:
        connection.execute(
            '''CREATE TABLE IF NOT EXISTS vacancies(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            employer TEXT,
            salary_from INTEGER,
            salary_to INTEGER,
            currency TEXT,
            area TEXT,
            schedule TEXT,
            employment TEXT,
            url TEXT,
            published_at TEXT,
            match_score INTEGER DEFAULT 0,
            match_reasons TEXT DEFAULT '[]',
            red_flags TEXT DEFAULT '[]',
            recommended_projects TEXT DEFAULT '[]',
            status TEXT DEFAULT 'new',
            raw_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )'''
        )

        migrations = {
            'status': "TEXT DEFAULT 'new'",
            'full_description': "TEXT DEFAULT ''",
            'cover_letter': "TEXT DEFAULT ''",
            'preparation_status': "TEXT DEFAULT ''",
            'preparation_note': "TEXT DEFAULT ''",
            'prepared_url': "TEXT DEFAULT ''",
            'prepared_at': 'TEXT',
            'telegram_notified_at': 'TEXT',
            'source_query': "TEXT DEFAULT ''",
        }
        for name, declaration in migrations.items():
            _ensure_column(connection, 'vacancies', name, declaration)

        connection.execute(
            '''CREATE TABLE IF NOT EXISTS agent_meta(
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )'''
        )
        connection.commit()


def get_meta(key, default=None):
    with connect() as connection:
        row = connection.execute(
            'SELECT value FROM agent_meta WHERE key=?', (key,)
        ).fetchone()
    return row['value'] if row else default


def set_meta(key, value):
    with connect() as connection:
        connection.execute(
            '''INSERT INTO agent_meta(key,value,updated_at)
            VALUES(?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=CURRENT_TIMESTAMP''',
            (key, value),
        )
        connection.commit()
