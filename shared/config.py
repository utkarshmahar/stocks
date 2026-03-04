from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Schwab
    schwab_api_key: str = ""
    schwab_app_secret: str = ""
    schwab_callback_url: str = "https://127.0.0.1"
    schwab_token_path: str = "/app/schwab_token.json"

    # InfluxDB
    influxdb_url: str = "http://host.docker.internal:8086"
    influxdb_token: str = ""
    influxdb_org: str = "options_trading"
    influxdb_bucket: str = "options_db"

    # PostgreSQL
    postgres_url: str = "postgresql+asyncpg://trading:changeme@postgres:5432/trading"

    # Redis
    redis_url: str = "redis://redis:6379"

    # Anthropic
    anthropic_api_key: str = ""

    # Ingestion
    query_interval: int = 10
    strike_count: int = 10
    default_symbols: str = "PANW,QCOM,CSCO"

    @property
    def symbols_list(self) -> list[str]:
        return [s.strip() for s in self.default_symbols.split(",") if s.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
