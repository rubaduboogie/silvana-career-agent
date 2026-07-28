Silvana Career Agent v0.4

Обновлены:
- app/browser_agent.js
- app/main.py

Поиск теперь идёт через авторизованный Chromium, а не через HH API.

После загрузки в GitHub:
cd /opt/career-agent-src
git pull
systemctl restart career-agent
sleep 3
curl http://127.0.0.1:8010/health
