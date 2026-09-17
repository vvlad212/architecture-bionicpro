import base64
import hashlib
import unittest
from urllib.parse import parse_qs, urlparse

import httpx

from backend.app.config import Settings
from backend.app.oauth import OAuthClient, create_pkce_pair


class FakeSessions:
    def __init__(self) -> None:
        self.state: str | None = None
        self.value: dict[str, str] | None = None

    async def create_transaction(self, state: str, value: dict[str, str]) -> None:
        self.state = state
        self.value = value


def settings() -> Settings:
    return Settings(
        frontend_url="http://localhost:3000",
        redis_url="redis://localhost",
        session_cookie_name="session",
        oauth_state_cookie_name="state",
        cookie_secure=False,
        session_ttl_seconds=1800,
        oauth_transaction_ttl_seconds=300,
        oidc_public_url="https://identity.example",
        oidc_internal_url="https://identity-internal.example",
        oidc_realm="reports",
        oidc_client_id="reports-bff",
        oidc_client_secret="secret",
        oidc_redirect_uri="https://reports.example/auth/callback",
        clickhouse_url="http://clickhouse:8123",
        clickhouse_database="bionicpro",
        clickhouse_user="default",
        clickhouse_password="",
        max_report_days=31,
    )


class PkceTest(unittest.TestCase):
    def test_challenge_is_sha256_of_verifier(self) -> None:
        verifier, challenge = create_pkce_pair()

        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")

        self.assertEqual(challenge, expected)
        self.assertGreaterEqual(len(verifier), 43)


class OAuthClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_login_uses_s256_and_keeps_verifier_server_side(self) -> None:
        sessions = FakeSessions()
        async with httpx.AsyncClient() as http_client:
            client = OAuthClient(settings(), http_client)
            url, state = await client.build_login_url(sessions)  # type: ignore[arg-type]

        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("code_verifier", query)
        self.assertEqual(sessions.state, state)
        self.assertIsNotNone(sessions.value)
        self.assertIn("code_verifier", sessions.value or {})


if __name__ == "__main__":
    unittest.main()
