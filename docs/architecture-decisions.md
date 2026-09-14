# Архитектурные решения

## ADR-001: BFF вместо токенов в SPA

Frontend не является OAuth-клиентом и не хранит токены в JavaScript, localStorage или sessionStorage. Confidential BFF выполняет Authorization Code + PKCE, хранит токены в Redis и связывает браузер с ними через случайный идентификатор в `HttpOnly` cookie.

Это уменьшает последствия XSS: вредоносный скрипт не может прочитать access/refresh token. PKCE защищает перехваченный authorization code, `state` защищает login callback, короткий access token и refresh rotation сокращают окно компрометации.

## ADR-002: Identity broker в каждом регионе

Keycloak выступает единым протоколом для BionicPRO и подключает региональные OIDC/SAML IdP через broker adapters. Сам Keycloak, связка внешней учётной записи с `customer_id`, CRM и медицинские данные разворачиваются внутри соответствующей юрисдикции.

Глобально распространяется только конфигурация realm/providers без PII. Добавление новой страны означает новый региональный deployment и новый adapter, но не изменение frontend/API-контракта.

## ADR-003: Дневная витрина в ClickHouse

Airflow заранее объединяет CRM и телеметрию в `user_report_mart`, отсортированную по `(customer_id, report_date)`. API выполняет простую фильтрацию по идентификатору из SSO и датам, поэтому пользовательский запрос не запускает тяжёлый join или агрегацию.

Последний шаг DAG записывает успешно обработанный день в `reporting_processed_days` и обновляет общий watermark в `reporting_state`. API проверяет наличие каждого дня запрошенного диапазона. Любой пробел возвращает `409`, поэтому простой сдвиг watermark после пропущенного запуска не выдаст формально успешный, но неполный отчёт.

## ADR-004: Авторизация по субъекту, а не параметру запроса

Keycloak добавляет `customer_id` из локального атрибута пользователя в UserInfo. BFF получает его по серверному access token. Endpoint `/reports` не принимает `customer_id`, а репозиторий вызывается только с идентификатором текущего principal.

Это обеспечивает object-level authorization по умолчанию и исключает классическую IDOR-уязвимость вида `/users/{other_user}/reports`.
