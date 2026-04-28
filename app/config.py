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

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    LOG_BUFFER_SIZE: int = 500

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


settings = Settings()
