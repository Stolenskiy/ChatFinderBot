from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    telegram_api_id: int = Field(alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(alias="TELEGRAM_API_HASH")
    telegram_session_name: str = Field(default="findchats_user", alias="TELEGRAM_SESSION_NAME")
    search_limit_per_query: int = Field(default=20, alias="SEARCH_LIMIT_PER_QUERY")
    page_size: int = Field(default=100, alias="PAGE_SIZE")
    page_state_ttl_minutes: int = Field(default=30, alias="PAGE_STATE_TTL_MINUTES")
    bot_log_level: str = Field(default="INFO", alias="BOT_LOG_LEVEL")
    bot_log_dir: str = Field(default="logs", alias="BOT_LOG_DIR")
    analytics_dir: str = Field(default="analytics", alias="ANALYTICS_DIR")


settings = Settings()
