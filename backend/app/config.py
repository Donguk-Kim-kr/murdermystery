"""환경 설정. 접속 정보는 libpq 표준 환경변수(PGHOST, PGPORT, PGUSER, PGPASSWORD)를 따른다."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MM_")

    # MM_DATABASE_URL 로 바꿀 수 있다. 호스트·계정 등 생략된 값은 PG* 환경변수에서 채워진다.
    database_url: str = "dbname=murder_mystery"
    # 빌드된 프론트엔드 폴더. 지정하면 백엔드가 화면도 함께 서비스한다 (Docker 실행용). 비어 있으면 서비스하지 않는다.
    static_dir: str = ""
    # 가입할 때 패스워드의 최소 글자 수(기본 8). 여러 계정을 만들어 시험할 때만 MM_PASSWORD_MIN_LENGTH 로 낮춘다(1 이상).
    password_min_length: int = Field(default=8, ge=1)
    # 같은 아이디로 패스워드를 연속으로 틀릴 수 있는 횟수와, 넘으면 로그인을 막는 시간(사용자 결정 2026-10-18: 10회, 5분)
    login_fail_limit: int = Field(default=10, ge=1)
    login_lock_seconds: float = Field(default=300.0, ge=1)
    db_pool_min: int = 1
    db_pool_max: int = 10

    # 업로드한 이미지·영상을 저장하는 폴더(MM_MEDIA_DIR). 도커는 /app/media 볼륨. 크기 제한은 사용자 결정 2026-10-20 의 가정값이다.
    media_dir: str = "media"
    media_max_image_bytes: int = 5 * 1024 * 1024
    media_max_video_bytes: int = 100 * 1024 * 1024

    # 대기실에서 방장이 "AI 추가"를 눌러 AI 플레이어를 부를 수 있게 한다(MM_AI_ENABLED). 서버가 AI 러너(scripts/ai_players.py)를 자식 프로세스로 띄운다.
    # 끄면(기본) 버튼이 보이지 않고 API 도 거절한다. 모델을 쓰는 AI 는 서버의 ANTHROPIC_API_KEY 로 비용이 나가므로, 인터넷에 공개하는 서버에서는 켜지 않는다.
    ai_enabled: bool = False
    # AI 러너가 서버에 접속하는 주소. 비우면 이 서버 자신(http://127.0.0.1:PORT)이다.
    ai_url: str = ""
    # 서버가 동시에 돌릴 수 있는 AI 프로세스 수(한 프로세스가 AI 한 명)
    ai_max_processes: int = Field(default=12, ge=1)

    # 대기실 (docs/DB_RULES.md B38)
    # 폴링(2~3초)이 이 시간 동안 끊기면 대기실에서 나간 것으로 본다. 사용자가 Discord 음성 때문에 다른 창으로 옮기면
    # 브라우저가 백그라운드 탭의 타이머를 늦추므로 너무 짧게 잡으면 쫓겨난다. (오래 숨겨 두면 그래도 끊길 수 있다 — B38 한계)
    room_member_timeout_seconds: float = 45.0
    # 입장코드를 연속으로 틀릴 수 있는 횟수와 그 기간
    room_join_fail_limit: int = 5
    room_join_fail_window_seconds: float = 60.0
    # 게임 중 이탈 유예(docs/ENGINE_DESIGN.md 1-8): 상태 조회가 이 시간 동안 끊기면 이탈로 본다. 이탈은 대개 네트워크 문제이고
    # 지인끼리 하는 게임에서는 10분 정도 기다릴 수 있다는 사용자 결정(2026-10-17)으로 600초이다.
    game_away_seconds: float = 600.0
    # 시간이 끝난 게임을 자동 진행으로 넘길지 확인하는 주기(초)
    game_tick_seconds: float = 1.0
    # 만료된 방을 정리하는 주기
    room_sweep_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
