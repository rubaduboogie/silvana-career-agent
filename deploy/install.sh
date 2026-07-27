#!/usr/bin/env bash
set -euo pipefail
cd /opt/career-agent
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
sudo cp deploy/career-agent.service /etc/systemd/system/career-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now career-agent
sudo systemctl status career-agent --no-pager
