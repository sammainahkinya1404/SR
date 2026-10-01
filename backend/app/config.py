from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite for now; the spec targets PostgreSQL (see CLAUDE.md for what changes on the move).
    database_url: str = "sqlite:///./retail.db"
    # "dev" trusts X-Business-Id / X-User-Id headers. Replace with OTP/PIN + JWT (spec Part B §9).
    auth_mode: Literal["dev"] = "dev"
    # One retail shop per installation: the shop is set up once and POST /businesses refuses a
    # second. (Records still carry business_id internally; tests turn this off to check isolation.)
    single_shop: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
