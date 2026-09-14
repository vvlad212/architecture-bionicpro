CREATE TABLE IF NOT EXISTS customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    country_code CHAR(2) NOT NULL,
    prosthesis_ids TEXT[] NOT NULL DEFAULT '{}'
);

INSERT INTO customers (id, name, email, country_code, prosthesis_ids)
VALUES
    (1, 'Pilot One', 'prothetic1@example.com', 'RU', ARRAY['arm-001']),
    (2, 'Pilot Two', 'prothetic2@example.com', 'RU', ARRAY['hand-002']),
    (3, 'Pilot Three', 'prothetic3@example.com', 'DE', ARRAY['leg-003'])
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    country_code = EXCLUDED.country_code,
    prosthesis_ids = EXCLUDED.prosthesis_ids;

