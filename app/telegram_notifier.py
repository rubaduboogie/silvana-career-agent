import html
import json
from urllib import error, request

from app.settings import get_settings


class TelegramError(RuntimeError):
    pass


def _api(method, payload):
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise TelegramError('TELEGRAM_BOT_TOKEN не задан')
    if not settings.telegram_chat_id:
        raise TelegramError('TELEGRAM_CHAT_ID не задан')

    url = (
        f'https://api.telegram.org/'
        f'bot{settings.telegram_bot_token}/{method}'
    )
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise TelegramError(f'Telegram HTTP {exc.code}: {body}') from exc
    except Exception as exc:
        raise TelegramError(f'Telegram недоступен: {exc}') from exc

    if not result.get('ok'):
        raise TelegramError(result.get('description', 'Telegram API error'))
    return result['result']


def send_message(text, buttons=None):
    settings = get_settings()
    payload = {
        'chat_id': settings.telegram_chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_notification': False,
        'link_preview_options': {'is_disabled': True},
    }
    if buttons:
        payload['reply_markup'] = {'inline_keyboard': buttons}
    return _api('sendMessage', payload)


def escape(value):
    return html.escape(str(value or ''), quote=True)
