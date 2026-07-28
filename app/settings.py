from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = '127.0.0.1'
    app_port: int = 8010
    database_path: str = 'data/career.db'
    hh_user_agent: str = 'SilvanaCareerAgent/0.6'

    telegram_bot_token: str = ''
    telegram_chat_id: str = ''
    notification_min_score: int = 70
    auto_prepare_min_score: int = 80
    max_ready_to_review: int = 5
    max_prepare_per_run: int = 2

    career_agent_url: str = 'https://career.silvanaxrai.online'
    career_browser_url: str = 'https://browser.silvanaxrai.online/vnc.html'
    career_review_token: str = ''
    hh_resume_title: str = ''

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


@lru_cache
def get_settings():
    return Settings()
