# Silvana Career Agent

Персональная система поиска вакансий, оценки совпадения, адаптации резюме и подготовки откликов.

Первая версия:
- поиск вакансий через публичный API HeadHunter;
- сохранение вакансий в SQLite;
- базовый скоринг;
- REST API;
- подготовка к OAuth HeadHunter;
- запуск на VPS через systemd.

Запуск:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main

Проверка:
curl http://127.0.0.1:8010/health

Секреты и .env нельзя коммитить.
