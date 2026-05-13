"""환경 변수 로드 (.env). pydantic-settings 기반."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    QUERY_TIMEOUT_SECONDS: int = 600

    # VNAND DB
    VNAND_DB_HOST: str = "localhost"
    VNAND_DB_PORT: int = 3306
    VNAND_DB_USER: str = "readonly"
    VNAND_DB_PASSWORD: str = ""
    VNAND_DB_NAME: str = "vnand"

    # DRAM DB
    DRAM_DB_HOST: str = "localhost"
    DRAM_DB_PORT: int = 3306
    DRAM_DB_USER: str = "readonly"
    DRAM_DB_PASSWORD: str = ""
    DRAM_DB_NAME: str = "dram"

    # Elasticsearch
    ES_HOSTS: str = "http://localhost:9200"  # 콤마 구분
    ES_USERNAME: str = ""
    ES_PASSWORD: str = ""
    ES_VERIFY_CERTS: bool = False

    # ---- ES Document 조회 페이지 (/es/document) ----
    # 인덱스 이름 / 한도를 코드 상수 대신 환경 변수로 관리.
    # 운영에서 인덱스를 바꾸거나 한도를 조정해야 할 때 코드를 건드리지 않도록 .env 로 빼둠.
    # · ES_DOCUMENT_LOOKUP_INDEX : terms 쿼리를 보낼 ES 인덱스 (와일드카드 가능)
    # · ES_DOCUMENT_LOOKUP_MAX_IDS : 한 번의 조회에서 받을 수 있는 _id 최대 개수
    ES_DOCUMENT_LOOKUP_INDEX: str = "parsing-index-2-*"
    ES_DOCUMENT_LOOKUP_MAX_IDS: int = 1000

    # ---- ES "작업 대기 및 지연" 페이지 (/es/pending-delay) ----
    # ES 집계 응답(`current_state_distribution.buckets`)에는 모든 상태 키가
    # 들어있지만, 페이지에는 운영팀이 관심 있는 키만 골라 정해진 순서대로
    # 노출하고 싶다.  그 "필터 + 정렬" 정의를 빌드/배포 시점에만 손대도록
    # .env 환경 변수로 빼둔다.
    #
    # 형식:
    #   "KEY1[:label1],KEY2[:label2],..."   (콤마 = 항목 구분, 콜론 = key:label)
    #
    # 예:
    #   ES_PENDING_DELAY_DISPLAY_KEYS=WAITING:대기,RUNNING:실행 중,STUCK:정체
    #
    # 규칙:
    #   - `:label` 부분을 생략하면 key 가 그대로 label 로 사용된다.
    #   - 응답에 없는 key 는 doc_count 0 으로 표시된다.
    #   - 응답에 있지만 여기에 없는 key 는 화면에 표시되지 않는다.
    #   - 빈 문자열이면 응답 전체가 정의 순서대로 표시 (필터 X).
    ES_PENDING_DELAY_DISPLAY_KEYS: str = (
        "WAITING:대기,"
        "RUNNING:실행 중,"
        "STUCK:정체,"
        "RETRY:재시도,"
        "FAILED:실패"
    )

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    LOG_BUFFER_SIZE: int = 500

    # ---- Auth (단일 비밀번호 기반 로그인) ----
    # APP_PASSWORD: 로그인 페이지에서 입력받을 비밀번호 (.env 로 주입 권장)
    # SESSION_SECRET_KEY: 세션 쿠키 서명 키 — 운영에서는 반드시 .env 로 교체
    # SESSION_MAX_AGE: 세션 유효 시간(초). 기본 12시간.
    APP_PASSWORD: str = "changeme"
    SESSION_SECRET_KEY: str = "dev-only-secret-please-override-in-env"
    SESSION_MAX_AGE: int = 60 * 60 * 12
    SESSION_COOKIE_NAME: str = "rcpadv_session"

    # ---- EQP I/F Manager (외부 페이지 임베드) ----
    # 사이드바의 "EQP I/F Manager" 페이지가 iframe 으로 로드할 URL.
    # 운영 환경에서는 사내 EQP I/F Manager 의 실제 주소로 .env 에서 덮어쓴다.
    # (예: https://eqp-if.intra.example.com/  또는  http://10.0.0.50:8080/ )
    # 빈 문자열이면 페이지에서 안내 메시지를 띄운다.
    EQP_IF_MANAGER_URL: str = "https://www.google.com"
    EQP_IF_MANAGER_TITLE: str = "EQP I/F Manager"

    # ---- Helpers ----
    def vnand_db_url(self) -> str:
        return (
            f"mysql+pymysql://{self.VNAND_DB_USER}:{self.VNAND_DB_PASSWORD}"
            f"@{self.VNAND_DB_HOST}:{self.VNAND_DB_PORT}/{self.VNAND_DB_NAME}?charset=utf8mb4"
        )

    def dram_db_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DRAM_DB_USER}:{self.DRAM_DB_PASSWORD}"
            f"@{self.DRAM_DB_HOST}:{self.DRAM_DB_PORT}/{self.DRAM_DB_NAME}?charset=utf8mb4"
        )

    def es_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ES_HOSTS.split(",") if h.strip()]

    def es_pending_delay_display_keys(self) -> list[tuple[str, str]]:
        """``ES_PENDING_DELAY_DISPLAY_KEYS`` 문자열을 [(key, label)] 리스트로 파싱.

        - 콤마(,)로 항목 구분, 콜론(:)으로 key:label 구분.
        - label 생략 시 key 가 label.
        - 빈 항목/빈 key 는 무시.
        - 중복 key 는 처음 등장한 것만 유지 (선언 순서 보존).
        """
        raw = (self.ES_PENDING_DELAY_DISPLAY_KEYS or "").strip()
        if not raw:
            return []
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                k, _, lab = item.partition(":")
                key = k.strip()
                label = lab.strip() or key
            else:
                key = item
                label = item
            if not key or key in seen:
                continue
            seen.add(key)
            out.append((key, label))
        return out


settings = Settings()
