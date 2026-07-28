#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/opt/career-agent-src"
cd "$PROJECT"

echo "1/7 Проверяю Telegram и защищённую ссылку..."
"$PROJECT/.venv/bin/python" -m app.telegram_setup

echo "2/7 Защищаю настройки..."
chown root:career-agent "$PROJECT/.env"
chmod 640 "$PROJECT/.env"

echo "3/7 Даю сервису доступ к рабочим файлам и базе..."
chown -R career-agent:career-agent "$PROJECT/app" "$PROJECT/data" "$PROJECT/config"
chmod -R u+rwX,go-rwx "$PROJECT/data"

echo "4/7 Устанавливаю systemd worker..."
cp deploy/career-agent-worker.service /etc/systemd/system/
cp deploy/career-agent-worker.timer /etc/systemd/system/
systemctl daemon-reload

echo "5/7 Обновляю базу и перезапускаю панель..."
sudo -u career-agent \
  "$PROJECT/.venv/bin/python" -c \
  "from app.database import init_db; init_db()"
systemctl restart career-agent

echo "6/7 Включаю фоновый поиск..."
systemctl enable --now career-agent-worker.timer

echo "7/7 Запускаю первый цикл сейчас..."
systemctl start career-agent-worker.service

echo
systemctl status career-agent-worker.service --no-pager -l || true
systemctl list-timers career-agent-worker.timer --no-pager
echo
echo "ГОТОВО"
echo "Бот пишет только после подготовки формы."
echo "Финальная кнопка HH никогда не нажимается автоматически."
