import unittest
from datetime import UTC, date, datetime, time, timedelta

from backend.app.models import ReportRow
from backend.app.reporting import InvalidReportPeriod, ReportNotReady, ReportService


class FakeRepository:
    def __init__(self) -> None:
        self.requested_customer_id: int | None = None
        self.is_processed = True

    async def processed_through(self, start_date: date,
                                end_date: date) -> datetime | None:
        del start_date
        if not self.is_processed:
            return None
        return datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)

    async def daily_rows(self, customer_id: int, start_date: date,
                         end_date: date) -> list[ReportRow]:
        self.requested_customer_id = customer_id
        return [
            ReportRow(
                report_date=start_date,
                customer_name="Pilot One",
                customer_email="pilot1@example.com",
                prosthesis_count=1,
                measurement_count=4,
                avg_signal_frequency=100.0,
                avg_signal_duration=25.0,
                avg_signal_amplitude=2.0,
                last_signal_at=datetime(2026, 8, 2, 12, 0),
            )
        ]


class ReportServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_uses_authenticated_customer_id_for_query(self) -> None:
        repository = FakeRepository()
        service = ReportService(repository)

        report = await service.build(17, date(2026, 8, 2), date(2026, 8, 3))

        self.assertEqual(repository.requested_customer_id, 17)
        self.assertEqual(report["customerId"], 17)
        self.assertEqual(report["summary"]["measurementCount"], 4)

    async def test_rejects_period_not_processed_by_airflow(self) -> None:
        repository = FakeRepository()
        repository.is_processed = False
        service = ReportService(repository)

        with self.assertRaises(ReportNotReady):
            await service.build(1, date(2026, 8, 10), date(2026, 8, 11))

    async def test_rejects_too_long_period(self) -> None:
        service = ReportService(FakeRepository(), max_report_days=7)

        with self.assertRaises(InvalidReportPeriod):
            await service.build(1, date(2026, 8, 1), date(2026, 8, 8))


if __name__ == "__main__":
    unittest.main()
