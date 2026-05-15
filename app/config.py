"""환경 변수 로드 (.env). pydantic-settings 기반."""
from typing import ClassVar
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

    # ---- LLM UI 사용 이력 (PostgreSQL) ----
    # 사이드바 'UI Client > LLM UI 사용 이력' 페이지가 조회하는 PostgreSQL DB.
    # MariaDB(VNAND/DRAM) 와 별도 인스턴스이며 드라이버도 다르다 (psycopg2).
    # 운영에서는 .env 로 실제 호스트/계정 값을 주입한다.
    LLM_PG_HOST: str = "localhost"
    LLM_PG_PORT: int = 5432
    LLM_PG_USER: str = "readonly"
    LLM_PG_PASSWORD: str = ""
    LLM_PG_NAME: str = "llm_ui"

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

    # ---- ES "종합 처리 이력" 페이지 (/es/history) ----
    # · ES_HISTORY_INDEX1 / ES_HISTORY_INDEX2 :
    #   각각 parsing-index-1, parsing-index-2 의 인덱스 패턴.
    # · ES_HISTORY_DAYS :
    #   집계 대상 기간. 오늘을 포함한 최근 N일.  (기본 7일)
    # · ES_HISTORY_STATE_KEYS :
    #   parsing-index-2 의 current_state 값을 어떤 키만, 어떤 순서로,
    #   어떤 라벨로, 어떤 그룹 속성(attr)으로 묶어 보여줄지 정의.
    #
    #   포맷:  ``"KEY[:label[:attr]],KEY[:label[:attr]],..."``
    #     - 콤마(,) 로 항목 구분, 콜론(:) 으로 key:label:attr 구분
    #     - label / attr 둘 다 생략 가능
    #         · ``KEY``                 → label=KEY, attr=""(미지정)
    #         · ``KEY:라벨``            → attr=""(미지정)
    #         · ``KEY:라벨:속성``       → 전부 지정
    #         · ``KEY::속성``           → label=KEY, attr=속성 (label 생략 표기)
    #     - attr 값 (보조 테이블 셀 강조용):
    #         · ``stage``    → 옅은 노랑
    #         · ``normal``   → 강조 없음 (정상 상태이므로 굳이 색 없음)
    #         · ``complete`` → 옅은 파랑
    #         · ``check``    → 옅은 붉은색
    #         · 그 외 / 빈 값 → 미지정 그룹 (옅은 초록으로 강조 — "기타 처리량")
    #
    #   예) "WAITING:대기:stage,RUNNING:실행 중:normal,DONE:완료:complete,FAILED:실패:check"
    ES_HISTORY_INDEX1: str = "parsing-index-1-*"
    ES_HISTORY_INDEX2: str = "parsing-index-2-*"
    ES_HISTORY_DAYS: int = 7
    ES_HISTORY_STATE_KEYS: str = (
        "WAITING:대기:stage,"
        "RUNNING:실행 중:normal,"
        "STUCK:정체:check,"
        "RETRY:재시도:check,"
        "FAILED:실패:check"
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

    def llm_pg_db_url(self) -> str:
        # SQLAlchemy URL for the LLM UI PostgreSQL DB (psycopg2 driver).
        return (
            f"postgresql+psycopg2://{self.LLM_PG_USER}:{self.LLM_PG_PASSWORD}"
            f"@{self.LLM_PG_HOST}:{self.LLM_PG_PORT}/{self.LLM_PG_NAME}"
        )

    def es_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ES_HOSTS.split(",") if h.strip()]

    @staticmethod
    def _parse_key_label_csv(raw: str) -> list[tuple[str, str]]:
        """``"KEY1[:label1],KEY2[:label2],..."`` 형식 문자열을 [(key, label)] 로 파싱.

        - 콤마(,)로 항목 구분, 콜론(:)으로 key:label 구분.
        - label 생략 시 key 가 label.
        - 빈 항목/빈 key 는 무시.
        - 중복 key 는 처음 등장한 것만 유지 (선언 순서 보존).
        """
        raw = (raw or "").strip()
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

    def es_pending_delay_display_keys(self) -> list[tuple[str, str]]:
        """``ES_PENDING_DELAY_DISPLAY_KEYS`` 를 [(key, label)] 로 파싱."""
        return self._parse_key_label_csv(self.ES_PENDING_DELAY_DISPLAY_KEYS)

    # 종합 처리 이력 페이지에서만 사용되는 attr 그룹 속성 허용값.
    # 표/차트에서 셀 강조 색을 결정하며, 그 외 값은 미지정(강조 없음)으로 처리.
    HISTORY_STATE_ATTR_VALUES: ClassVar[frozenset[str]] = frozenset({
        "stage",     # 옅은 노랑
        "normal",    # 강조 없음 (정상)
        "complete",  # 옅은 파랑
        "check",     # 옅은 붉은색
    })

    @classmethod
    def _parse_key_label_attr_csv(cls, raw: str) -> list[tuple[str, str, str]]:
        """``"KEY[:label[:attr]],..."`` 형식 문자열을 [(key, label, attr)] 로 파싱.

        - 콤마(,)로 항목 구분, 콜론(:)으로 key/label/attr 구분 (3토큰까지).
        - label 생략 시 key 가 label.
        - attr 생략 또는 허용값 외이면 빈 문자열로 정규화 (미지정 그룹).
        - 빈 항목/빈 key 는 무시.
        - 중복 key 는 처음 등장한 것만 유지 (선언 순서 보존).
        """
        raw = (raw or "").strip()
        if not raw:
            return []
        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            # 최대 3 토큰까지만 사용 (그 이후 콜론은 라벨에 포함되지 않음 — 무시)
            parts = [p.strip() for p in item.split(":", 2)]
            key = parts[0] if len(parts) >= 1 else ""
            label = parts[1] if len(parts) >= 2 else ""
            attr = parts[2] if len(parts) >= 3 else ""
            if not key or key in seen:
                continue
            if not label:
                label = key
            # 허용 attr 만 통과시키고, 그 외는 미지정으로 정규화
            attr_norm = attr if attr in cls.HISTORY_STATE_ATTR_VALUES else ""
            seen.add(key)
            out.append((key, label, attr_norm))
        return out

    def es_history_state_keys(self) -> list[tuple[str, str, str]]:
        """``ES_HISTORY_STATE_KEYS`` 를 [(key, label, attr)] 로 파싱.

        attr 는 ``HISTORY_STATE_ATTR_VALUES`` 의 값 중 하나이거나 빈 문자열(미지정).
        """
        return self._parse_key_label_attr_csv(self.ES_HISTORY_STATE_KEYS)


settings = Settings()
