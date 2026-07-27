from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8010
    database_path: str = "data/career.db"
    hh_user_agent: str = "SilvanaCareerAgent/0.1"
    hh_client_id: str = ""
    hh_client_secret: str = ""
    hh_redirect_uri: str = "https://career.silvanaxrai.online/auth/hh/callback"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
