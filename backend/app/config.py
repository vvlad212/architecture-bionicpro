import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    frontend_url: str
    redis_url: str
    session_cookie_name: str
    oauth_state_cookie_name: str
    cookie_secure: bool
    session_ttl_seconds: int
    oauth_transaction_ttl_seconds: int
    oidc_public_url: str
    oidc_internal_url: str
    oidc_realm: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_uri: str
    clickhouse_url: str
    clickhouse_database: str
    clickhouse_user: str
    clickhouse_password: str
    max_report_days: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000"),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "bionicpro_session"),
            oauth_state_cookie_name=os.getenv(
                "OAUTH_STATE_COOKIE_NAME", "bionicpro_oauth_state"
            ),
            cookie_secure=_as_bool(os.getenv("COOKIE_SECURE", "false")),
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "1800")),
            oauth_transaction_ttl_seconds=int(
                os.getenv("OAUTH_TRANSACTION_TTL_SECONDS", "300")
            ),
            oidc_public_url=os.getenv("OIDC_PUBLIC_URL", "http://localhost:8080"),
            oidc_internal_url=os.getenv("OIDC_INTERNAL_URL", "http://keycloak:8080"),
            oidc_realm=os.getenv("OIDC_REALM", "reports-realm"),
            oidc_client_id=os.getenv("OIDC_CLIENT_ID", "reports-bff"),
            oidc_client_secret=os.getenv(
                "OIDC_CLIENT_SECRET", "bionicpro-local-secret-change-me"
            ),
            oidc_redirect_uri=os.getenv(
                "OIDC_REDIRECT_URI", "http://localhost:8000/auth/callback"
            ),
            clickhouse_url=os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123"),
            clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", "bionicpro"),
            clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
            clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            max_report_days=int(os.getenv("MAX_REPORT_DAYS", "31")),
        )

    @property
    def oidc_public_realm_url(self) -> str:
        return f"{self.oidc_public_url.rstrip('/')}/realms/{self.oidc_realm}"

    @property
    def oidc_internal_realm_url(self) -> str:
        return f"{self.oidc_internal_url.rstrip('/')}/realms/{self.oidc_realm}"


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
