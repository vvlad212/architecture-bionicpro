CREATE DATABASE IF NOT EXISTS bionicpro;

CREATE TABLE IF NOT EXISTS bionicpro.emg_sensor_data (
    customer_id UInt64,
    prosthesis_id String,
    prosthesis_type LowCardinality(String),
    muscle_group LowCardinality(String),
    signal_frequency UInt32,
    signal_duration UInt32,
    signal_amplitude Decimal(7, 3),
    signal_time DateTime('UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(signal_time)
ORDER BY (customer_id, prosthesis_id, signal_time);

CREATE TABLE IF NOT EXISTS bionicpro.crm_customers_stage (
    customer_id UInt64,
    customer_name String,
    customer_email String,
    country_code FixedString(2),
    prosthesis_ids Array(String),
    loaded_at DateTime('UTC') DEFAULT now()
)
ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY customer_id;

CREATE TABLE IF NOT EXISTS bionicpro.user_report_mart (
    customer_id UInt64,
    report_date Date,
    customer_name String,
    customer_email String,
    prosthesis_count UInt32,
    measurement_count UInt64,
    avg_signal_frequency Float64,
    avg_signal_duration Float64,
    avg_signal_amplitude Float64,
    last_signal_at DateTime('UTC'),
    processed_at DateTime('UTC') DEFAULT now()
)
ENGINE = ReplacingMergeTree(processed_at)
PARTITION BY toYYYYMM(report_date)
ORDER BY (customer_id, report_date);

CREATE TABLE IF NOT EXISTS bionicpro.reporting_state (
    pipeline LowCardinality(String),
    processed_from DateTime('UTC'),
    processed_through DateTime('UTC'),
    updated_at DateTime('UTC') DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY pipeline;

CREATE TABLE IF NOT EXISTS bionicpro.reporting_processed_days (
    pipeline LowCardinality(String),
    report_date Date,
    processed_at DateTime('UTC') DEFAULT now()
)
ENGINE = ReplacingMergeTree(processed_at)
ORDER BY (pipeline, report_date);
