import json
import os
from typing import Any

import pendulum
import requests

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.providers.postgres.hooks.postgres import PostgresHook

CLICKHOUSE_URL = os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "bionicpro")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")


def execute_clickhouse(query: str, parameters: dict[str, str] | None = None) -> str:
    response = requests.post(
        CLICKHOUSE_URL,
        params={"database": CLICKHOUSE_DATABASE, **(parameters or {})},
        data=query.encode("utf-8"),
        auth=(CLICKHOUSE_USER, CLICKHOUSE_PASSWORD),
        timeout=60,
    )
    response.raise_for_status()
    return response.text


def insert_json_each_row(table: str, rows: list[dict[str, Any]]) -> None:
    payload = "\n".join(json.dumps(row) for row in rows)
    execute_clickhouse(f"INSERT INTO {table} FORMAT JSONEachRow\n{payload}")


@dag(
    dag_id="bionicpro_reporting",
    description="CRM and telemetry ETL into the per-user reporting mart",
    schedule="0 0 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "bionicpro", "retries": 2},
    tags=["bionicpro", "reporting", "etl"],
)
def bionicpro_reporting():
    @task
    def sync_crm_customers() -> int:
        records = PostgresHook(postgres_conn_id="crm_db").get_records(
            """
            SELECT id, name, email, country_code, prosthesis_ids
            FROM customers
            ORDER BY id
            """
        )
        rows = [
            {
                "customer_id": record[0],
                "customer_name": record[1],
                "customer_email": record[2],
                "country_code": record[3],
                "prosthesis_ids": record[4],
            }
            for record in records
        ]
        execute_clickhouse("TRUNCATE TABLE crm_customers_stage")
        if rows:
            insert_json_each_row("crm_customers_stage", rows)
        return len(rows)

    @task
    def build_daily_report_mart(customer_count: int) -> None:
        if customer_count == 0:
            raise ValueError(
                "CRM returned no customers; refusing to advance the watermark"
            )

        context = get_current_context()
        window_start = context["data_interval_start"].in_timezone("UTC")
        window_end = context["data_interval_end"].in_timezone("UTC")
        parameters = {
            "param_window_start": window_start.format("YYYY-MM-DD HH:mm:ss"),
            "param_window_end": window_end.format("YYYY-MM-DD HH:mm:ss"),
        }

        execute_clickhouse(
            """
            ALTER TABLE user_report_mart DELETE
            WHERE report_date >= toDate({window_start:DateTime})
              AND report_date < toDate({window_end:DateTime})
            SETTINGS mutations_sync = 1
            """,
            parameters,
        )
        execute_clickhouse(
            """
            INSERT INTO user_report_mart
            SELECT
                sensor.customer_id,
                toDate(sensor.signal_time) AS report_date,
                any(customer.customer_name) AS customer_name,
                any(customer.customer_email) AS customer_email,
                uniqExact(sensor.prosthesis_id) AS prosthesis_count,
                count() AS measurement_count,
                avg(sensor.signal_frequency) AS avg_signal_frequency,
                avg(sensor.signal_duration) AS avg_signal_duration,
                avg(toFloat64(sensor.signal_amplitude)) AS avg_signal_amplitude,
                max(sensor.signal_time) AS last_signal_at,
                now() AS processed_at
            FROM emg_sensor_data AS sensor
            INNER JOIN crm_customers_stage AS customer FINAL
                ON customer.customer_id = sensor.customer_id
            WHERE sensor.signal_time >= {window_start:DateTime}
              AND sensor.signal_time < {window_end:DateTime}
            GROUP BY sensor.customer_id, report_date
            """,
            parameters,
        )
        execute_clickhouse(
            """
            INSERT INTO reporting_processed_days
                (pipeline, report_date, processed_at)
            VALUES (
                'bionicpro_reporting',
                toDate({window_start:DateTime}),
                now()
            )
            """,
            parameters,
        )
        execute_clickhouse(
            """
            INSERT INTO reporting_state
                (pipeline, processed_from, processed_through, updated_at)
            SELECT
                'bionicpro_reporting',
                if(
                    count() = 0,
                    {window_start:DateTime},
                    least(
                        argMax(processed_from, updated_at),
                        {window_start:DateTime}
                    )
                ),
                if(
                    count() = 0,
                    {window_end:DateTime},
                    greatest(
                        argMax(processed_through, updated_at),
                        {window_end:DateTime}
                    )
                ),
                now()
            FROM reporting_state
            WHERE pipeline = 'bionicpro_reporting'
            """,
            parameters,
        )

    build_daily_report_mart(sync_crm_customers())


bionicpro_reporting()
