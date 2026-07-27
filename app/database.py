import sqlite3
from pathlib import Path
from app.settings import get_settings

VALID_STATUSES={'new','shortlisted','applied','interview','test_task','offer','rejected','ignored'}

def connect():
    path=Path(get_settings().database_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path)
    c.row_factory=sqlite3.Row
    return c

def init_db():
    with connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS vacancies(
        id TEXT PRIMARY KEY,name TEXT NOT NULL,employer TEXT,salary_from INTEGER,salary_to INTEGER,currency TEXT,
        area TEXT,schedule TEXT,employment TEXT,url TEXT,published_at TEXT,match_score INTEGER DEFAULT 0,
        match_reasons TEXT DEFAULT '[]',red_flags TEXT DEFAULT '[]',recommended_projects TEXT DEFAULT '[]',
        status TEXT DEFAULT 'new',raw_json TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        c.commit()
