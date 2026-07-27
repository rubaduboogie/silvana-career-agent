import sqlite3
from pathlib import Path
from app.settings import get_settings

def connect():
    path = Path(get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS vacancies (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          employer TEXT,
          salary_from INTEGER,
          salary_to INTEGER,
          currency TEXT,
          area TEXT,
          url TEXT,
          published_at TEXT,
          match_score INTEGER DEFAULT 0,
          raw_json TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()
