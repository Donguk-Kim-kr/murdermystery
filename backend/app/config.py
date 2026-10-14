"""환경 설정. 접속 정보는 libpq 표준 환경변수(PGHOST, PGPORT, PGUSER, PGPASSWORD)를 따른다."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MM_")

    # MM_DATABASE_URL 로 바꿀 수 있다. 호스트·계정 등 생략된 값은 PG* 환경변수에서 채워진다.
    database_url: str = "dbname=murder_mystery"
    db_pool_min: int = 1
    db_pool_max: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
