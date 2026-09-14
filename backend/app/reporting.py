import json
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol

import httpx

from .config import Settings
from .models import ReportRow


class ReportNotReady(Exception):
    pass


class InvalidReportPeriod(Exception):
    pass


class ReportRepository(Protocol):
    async def processed_through(self, start_date: date,
                                end_date: date) -> datetime | None: ...

    async def daily_rows(self, customer_id: int, start_date: date,
                         end_date: date) -> list[ReportRow]: ...


class ClickHouseReportRepository:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._auth = httpx.BasicAuth(
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
        )

    async def healthcheck(self) -> bool:
        response = await self._query("SELECT 1 AS ok FORMAT JSONEachRow")
        return bool(response and int(response[0]["ok"]) == 1)

    async def processed_through(self, start_date: date,
                                end_date: date) -> datetime | None:
        rows = await self._query(
            """
            SELECT
                max(report_date) AS latest_date,
                countDistinct(report_date) AS processed_days
            FROM reporting_processed_days FINAL
            WHERE pipeline = 'bionicpro_reporting'
              AND report_date BETWEEN {start_date:Date} AND {end_date:Date}
            HAVING processed_days = dateDiff(
                'day', {start_date:Date}, {end_date:Date}
            ) + 1
            FORMAT JSONEachRow
            """,
            {
                "param_start_date": start_date.isoformat(),
                "param_end_date": end_date.isoformat(),
            },
        )
        if not rows:
            return None
        latest_date = date.fromisoformat(str(rows[0]["latest_date"]))
        return datetime.combine(
            latest_date + timedelta(days=1), time.min, tzinfo=UTC
        )

    async def daily_rows(self, customer_id: int, start_date: date,
                         end_date: date) -> list[ReportRow]:
        rows = await self._query(
            """
            SELECT
                report_date,
                customer_name,
                customer_email,
                prosthesis_count,
                measurement_count,
                avg_signal_frequency,
                avg_signal_duration,
                avg_signal_amplitude,
                last_signal_at
            FROM user_report_mart FINAL
            WHERE customer_id = {customer_id:UInt64}
              AND report_date BETWEEN {start_date:Date} AND {end_date:Date}
            ORDER BY report_date
            FORMAT JSONEachRow
            """,
            {
                "param_customer_id": str(customer_id),
                "param_start_date": start_date.isoformat(),
                "param_end_date": end_date.isoformat(),
            },
        )
        return [ReportRow.from_dict(row) for row in rows]

    async def _query(self, query: str,
                     parameters: dict[str, str] | None = None) -> list[dict[str, Any]]:
        response = await self._http.post(
            self._settings.clickhouse_url,
            params={
                "database": self._settings.clickhouse_database,
                **(parameters or {}),
            },
            content=query.strip(),
            auth=self._auth,
        )
        response.raise_for_status()
        return [json.loads(line) for line in _non_empty_lines(response.text)]


class ReportService:
    def __init__(self, repository: ReportRepository, max_report_days: int = 31) -> None:
        self._repository = repository
        self._max_report_days = max_report_days

    async def build(self, customer_id: int, start_date: date,
                    end_date: date) -> dict[str, Any]:
        self._validate_period(start_date, end_date)
        processed_through = await self._repository.processed_through(
            start_date, end_date
        )
        if processed_through is None:
            raise ReportNotReady(
                "The requested period has not been fully processed by Airflow"
            )

        rows = await self._repository.daily_rows(customer_id, start_date, end_date)
        return {
            "customerId": customer_id,
            "period": {"from": start_date.isoformat(), "to": end_date.isoformat()},
            "processedThrough": processed_through.isoformat(),
            "daily": [_serialize_row(row) for row in rows],
            "summary": _summary(rows),
        }

    def _validate_period(self, start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise InvalidReportPeriod("start_date must not be after end_date")
        if (end_date - start_date).days + 1 > self._max_report_days:
            raise InvalidReportPeriod(
                f"The report period must not exceed {self._max_report_days} days"
            )


def _non_empty_lines(value: str) -> list[str]:
    return [line for line in value.splitlines() if line.strip()]


def _serialize_row(row: ReportRow) -> dict[str, Any]:
    value = asdict(row)
    value["report_date"] = row.report_date.isoformat()
    value["last_signal_at"] = row.last_signal_at.isoformat()
    return value


def _summary(rows: list[ReportRow]) -> dict[str, float | int]:
    measurement_count = sum(row.measurement_count for row in rows)
    if measurement_count == 0:
        return {
            "days": len(rows),
            "measurementCount": 0,
            "prosthesisCount": 0,
            "avgSignalFrequency": 0.0,
            "avgSignalDuration": 0.0,
            "avgSignalAmplitude": 0.0,
        }

    def weighted(attribute: str) -> float:
        total = sum(
            float(getattr(row, attribute)) * row.measurement_count for row in rows
        )
        return round(total / measurement_count, 2)

    return {
        "days": len(rows),
        "measurementCount": measurement_count,
        "prosthesisCount": max((row.prosthesis_count for row in rows), default=0),
        "avgSignalFrequency": weighted("avg_signal_frequency"),
        "avgSignalDuration": weighted("avg_signal_duration"),
        "avgSignalAmplitude": weighted("avg_signal_amplitude"),
    }
