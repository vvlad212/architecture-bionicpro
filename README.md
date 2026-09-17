# BionicPRO — проектная работа 9 спринта

Решение закрывает две части задания: безопасное SSO с PKCE и сервис пользовательских отчётов на подготовленной OLAP-витрине.

## Что реализовано

### 1. Безопасность и SSO

- Authorization Code + PKCE (`S256`) обязателен для клиента `reports-bff` в Keycloak.
- Использован паттерн BFF: frontend не получает access- и refresh-токены IdP. Они хранятся в Redis на стороне backend, а браузеру выдаётся только непрозрачная `HttpOnly` cookie.
- Access token живёт пять минут. Refresh token ротируется (`refreshTokenMaxReuse = 0`) и отзывается при выходе.
- `state` и одноразовый PKCE verifier хранятся на сервере и удаляются атомарно после callback.
- В realm добавлены отключённые шаблоны региональных OIDC-провайдеров RU и EU. В production каждый регион включает только свой IdP и хранит связку внешнего `subject` с локальным `customer_id` внутри страны.
- Endpoint `/reports` не принимает идентификатор пользователя: `customer_id` извлекается только из подтверждённой SSO-сессии. Поэтому подменить пользователя в URL невозможно.

Диаграмма: [`diagrams/01-sso-bff.drawio`](diagrams/01-sso-bff.drawio).

### 2. Отчёты и ETL

- CRM хранится в PostgreSQL, телеметрия и отчётная витрина — в ClickHouse.
- Airflow DAG `bionicpro_reporting` ежедневно:
  1. извлекает клиентов из CRM;
  2. загружает их в `crm_customers_stage`;
  3. объединяет клиентов с телеметрией;
  4. пересобирает дневные строки `user_report_mart`;
  5. отмечает обработанный календарный день только после успешной подготовки витрины.
- `GET /reports` читает готовые строки по `(customer_id, report_date)` без тяжёлой агрегации в запросе.
- API проверяет конец выбранного периода по watermark `processed_through`. Если Airflow ещё не дошёл до него, возвращается `409 Conflict`; дни без измерений остаются пустыми и не блокируют готовый отчёт.
- React UI позволяет выбрать период и скачать CSV.

Диаграмма: [`diagrams/02-reporting-platform.drawio`](diagrams/02-reporting-platform.drawio).

## Структура

```text
airflow/      DAG и отдельный Docker-образ Airflow
backend/      FastAPI BFF, OAuth/PKCE, sessions, Reports API
clickhouse/   raw telemetry, отчётная витрина и demo seed
crm-db/       схема и demo-клиенты CRM
diagrams/     две C4-подобные диаграммы draw.io
frontend/     React UI без OAuth-токенов
keycloak/     realm с PKCE, ролями и regional IdP templates
```

## Запуск

Требуются Docker и Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Сервисы:

| Сервис | URL |
|---|---|
| UI | <http://localhost:3000> |
| Reports API / Swagger | <http://localhost:8000/docs> |
| Keycloak | <http://localhost:8080> |
| Airflow | <http://localhost:8081> |
| ClickHouse HTTP | <http://localhost:8123> |

Demo-пользователи Keycloak:

| Логин | Пароль | Локальный клиент |
|---|---|---|
| `prothetic1` | `prothetic123` | `customer_id=1` |
| `prothetic2` | `prothetic123` | `customer_id=2` |
| `prothetic3` | `prothetic123` | `customer_id=3` |

Локальные пароли предназначены только для демонстрации. Перед production-развёртыванием секрет клиента Keycloak, пароли БД, Fernet key и webserver secret нужно вынести в secret manager и ротировать. Для HTTPS установить `COOKIE_SECURE=true`.

## Проверка сценария

1. Откройте <http://localhost:3000> и нажмите «Войти через SSO».
2. Войдите одним из demo-пользователей.
3. Выберите полностью обработанный период и скачайте CSV.
4. Запросите период с сегодняшним или будущим днём — UI покажет, что Airflow ещё не подготовил его.
5. В Airflow откройте DAG `bionicpro_reporting`; расписание — ежедневно в `00:00 UTC`. DAG также можно запустить вручную.

Demo seed заранее отмечает обработанными 31 завершённый день, чтобы стандартный
семидневный период и весь разрешённый диапазон можно было скачать до первого
планового запуска DAG.

## API

```http
GET /auth/login
GET /auth/callback
GET /auth/me
POST /auth/logout
GET /reports?start_date=2026-09-01&end_date=2026-09-07&format=json|csv
```

Для `/auth/me`, `/auth/logout` и `/reports` нужна серверная сессия. Произвольного `user_id` в контракте нет.

## Локальные проверки

```bash
python -m pytest
python -m compileall backend airflow/dags
docker compose config --quiet
cd frontend && npm ci && npm run build
```

## Production-ограничения

- Внешние IdP в realm намеренно отключены и содержат шаблонные URL. Их включают отдельно в каждом региональном окружении после настройки client secret в secret manager.
- Региональные CRM, медицинская БД, ClickHouse, Keycloak и session store не должны пересекать границу юрисдикции. Между регионами можно распространять только версионированную конфигурацию без PII и медицинских данных.
- Все публичные URL должны работать только по TLS. Cookies должны иметь `Secure`, инфраструктура — сетевые политики, шифрование дисков, аудит и резервное копирование.
- Для нескольких экземпляров Airflow staging-таблицу следует обновлять через версионированную таблицу/атомарный `EXCHANGE TABLES`; в demo используется один активный DAG run.
