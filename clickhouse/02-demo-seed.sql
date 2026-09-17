-- ClickHouse's Docker entrypoint pipes this file through clickhouse-client
-- --multiquery, so INSERT ... VALUES statements must stay on one physical line.
INSERT INTO bionicpro.crm_customers_stage (customer_id, customer_name, customer_email, country_code, prosthesis_ids) VALUES (1, 'Pilot One', 'prothetic1@example.com', 'RU', ['arm-001']), (2, 'Pilot Two', 'prothetic2@example.com', 'RU', ['hand-002']), (3, 'Pilot Three', 'prothetic3@example.com', 'DE', ['leg-003']);

INSERT INTO bionicpro.emg_sensor_data (customer_id, prosthesis_id, prosthesis_type, muscle_group, signal_frequency, signal_duration, signal_amplitude, signal_time) VALUES (1, 'arm-001', 'arm', 'biceps', 180, 950, 2.450, now('UTC') - INTERVAL 47 HOUR), (1, 'arm-001', 'arm', 'triceps', 205, 870, 2.810, now('UTC') - INTERVAL 30 HOUR), (1, 'arm-001', 'arm', 'biceps', 198, 910, 2.670, now('UTC') - INTERVAL 20 HOUR), (2, 'hand-002', 'hand', 'forearm', 220, 740, 3.110, now('UTC') - INTERVAL 44 HOUR), (2, 'hand-002', 'hand', 'forearm', 215, 760, 3.050, now('UTC') - INTERVAL 18 HOUR), (3, 'leg-003', 'leg', 'quadriceps', 160, 1100, 2.220, now('UTC') - INTERVAL 28 HOUR);

INSERT INTO bionicpro.user_report_mart
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
FROM bionicpro.emg_sensor_data AS sensor
INNER JOIN bionicpro.crm_customers_stage AS customer FINAL
    ON customer.customer_id = sensor.customer_id
GROUP BY sensor.customer_id, report_date;

-- The demo UI requests the previous seven days by default and the API allows
-- up to 31 days. Mark the full allowed historical window as processed so a
-- clean checkout can download a report before the first scheduled DAG runs.
INSERT INTO bionicpro.reporting_state (pipeline, processed_from, processed_through) VALUES ('bionicpro_reporting', toStartOfDay(now('UTC') - INTERVAL 31 DAY, 'UTC'), toStartOfDay(now('UTC'), 'UTC'));

INSERT INTO bionicpro.reporting_processed_days
    (pipeline, report_date, processed_at)
SELECT
    'bionicpro_reporting',
    toDate(now('UTC'), 'UTC') - number - 1,
    now()
FROM numbers(31);
