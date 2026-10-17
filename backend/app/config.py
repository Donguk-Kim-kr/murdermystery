"""환경 설정. 접속 정보는 libpq 표준 환경변수(PGHOST, PGPORT, PGUSER, PGPASSWORD)를 따른다."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MM_")

    # MM_DATABASE_URL 로 바꿀 수 있다. 호스트·계정 등 생략된 값은 PG* 환경변수에서 채워진다.
    database_url: str = "dbname=murder_mystery"
    # 빌드된 프론트엔드 폴더. 지정하면 백엔드가 화면도 함께 서비스한다 (Docker 실행용). 비어 있으면 서비스하지 않는다.
    static_dir: str = ""
    db_pool_min: int = 1
    db_pool_max: int = 10

    # 대기실 (docs/DB_RULES.md B38)
    # 폴링(2~3초)이 이 시간 동안 끊기면 대기실에서 나간 것으로 본다. 사용자가 Discord 음성 때문에 다른 창으로 옮기면
    # 브라우저가 백그라운드 탭의 타이머를 늦추므로 너무 짧게 잡으면 쫓겨난다. (오래 숨겨 두면 그래도 끊길 수 있다 — B38 한계)
    room_member_timeout_seconds: float = 45.0
    # 입장코드를 연속으로 틀릴 수 있는 횟수와 그 기간
    room_join_fail_limit: int = 5
    room_join_fail_window_seconds: float = 60.0
    # 게임 중 이탈 유예(docs/ENGINE_DESIGN.md 1-8): 상태 조회가 이 시간 동안 끊기면 이탈로 본다. 대기실과 같은 이유로 길게 잡는다.
    game_away_seconds: float = 45.0
    # 시간이 끝난 게임을 자동 진행으로 넘길지 확인하는 주기(초)
    game_tick_seconds: float = 1.0
    # 만료된 방을 정리하는 주기
    room_sweep_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
