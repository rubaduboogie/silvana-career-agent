import getpass
import json
import secrets
from pathlib import Path
from urllib import error, request


ENV_PATH = Path('.env')


def api(token, method, payload=None):
    url = f'https://api.telegram.org/bot{token}/{method}'
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = request.Request(url, data=data, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'Telegram HTTP {exc.code}: {body}') from exc

    if not result.get('ok'):
        raise RuntimeError(result.get('description', 'Telegram API error'))
    return result['result']


def latest_private_chat_id(token):
    updates = api(token, 'getUpdates', {'timeout': 0, 'limit': 100})
    for update in reversed(updates):
        message = (
            update.get('message')
            or update.get('edited_message')
            or update.get('callback_query', {}).get('message')
        )
        if not message:
            continue
        chat = message.get('chat') or {}
        if chat.get('type') == 'private' and chat.get('id'):
            return str(chat['id'])
    return None


def read_env():
    result = {}
    if not ENV_PATH.exists():
        return result
    for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def update_env(values):
    existing = ENV_PATH.read_text(encoding='utf-8').splitlines() \
        if ENV_PATH.exists() else []
    keys = set(values)
    kept = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            kept.append(line)
            continue
        key = line.split('=', 1)[0].strip()
        if key not in keys:
            kept.append(line)
    kept.extend(f'{key}={value}' for key, value in values.items())
    ENV_PATH.write_text('\n'.join(kept).rstrip() + '\n', encoding='utf-8')


def main():
    current = read_env()
    token = current.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = current.get('TELEGRAM_CHAT_ID', '')

    print('Настройка Telegram для Silvana Career Agent')
    if not token:
        token = getpass.getpass(
            'Вставь токен BotFather (ввод скрыт): '
        ).strip()
    if not token:
        raise SystemExit('Токен не введён.')

    me = api(token, 'getMe')
    if not chat_id:
        chat_id = latest_private_chat_id(token)
    if not chat_id:
        raise SystemExit(
            'Не найден личный чат. Отправь боту /start и повтори.'
        )

    review_token = current.get('CAREER_REVIEW_TOKEN') \
        or secrets.token_urlsafe(32)

    update_env({
        'TELEGRAM_BOT_TOKEN': token,
        'TELEGRAM_CHAT_ID': chat_id,
        'NOTIFICATION_MIN_SCORE': '70',
        'AUTO_PREPARE_MIN_SCORE': '80',
        'MAX_READY_TO_REVIEW': '5',
        'MAX_PREPARE_PER_RUN': '2',
        'CAREER_AGENT_URL': 'https://career.silvanaxrai.online',
        'CAREER_BROWSER_URL': (
            'https://browser.silvanaxrai.online/vnc.html'
        ),
        'CAREER_REVIEW_TOKEN': review_token,
    })

    api(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': (
            '✅ Silvana Career Agent v0.6 подключён.\n'
            'Бот напишет только после подготовки формы отклика.'
        ),
    })

    print(f"Готово. Бот @{me.get('username')} подключён.")
    print('Chat ID и защищённая ссылка проверки сохранены в .env.')


if __name__ == '__main__':
    main()
