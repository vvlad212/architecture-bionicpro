import unittest
from datetime import date

import httpx

from backend.app.config import Settings
from backend.app.reporting import ClickHouseReportRepository


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


class ClickHouseReportRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_reads_json_each_row_and_binds_customer_id(self) -> None:
        captured_request: httpx.Request | None = None

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                text=(
                    '{"report_date":"2026-08-02","customer_name":"Pilot One",'
                    '"customer_email":"pilot1@example.com","prosthesis_count":1,'
                    '"measurement_count":2,"avg_signal_frequency":100.5,'
                    '"avg_signal_duration":20.0,"avg_signal_amplitude":2.5,'
                    '"last_signal_at":"2026-08-02 12:00:00"}\n'
                ),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            repository = ClickHouseReportRepository(settings(), client)
            rows = await repository.daily_rows(
                17, date(2026, 8, 2), date(2026, 8, 3)
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].measurement_count, 2)
        self.assertIsNotNone(captured_request)
        assert captured_request is not None
        self.assertEqual(captured_request.url.params["param_customer_id"], "17")
        self.assertIn(b"customer_id = {customer_id:UInt64}", captured_request.content)


if __name__ == "__main__":
    unittest.main()
