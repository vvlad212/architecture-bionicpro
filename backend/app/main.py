import csv
import io
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .config import Settings, get_settings
from .models import Principal, SessionRecord
from .oauth import AuthenticationError, OAuthClient
from .reporting import (
    ClickHouseReportRepository,
    InvalidReportPeriod,
    ReportNotReady,
    ReportService,
)
from .sessions import RedisSessionStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    http_client = httpx.AsyncClient(timeout=10.0)
    sessions = RedisSessionStore(
        settings.redis_url,
        settings.session_ttl_seconds,
        settings.oauth_transaction_ttl_seconds,
    )
    repository = ClickHouseReportRepository(settings, http_client)
    app.state.settings = settings
    app.state.http_client = http_client
    app.state.sessions = sessions
    app.state.oauth = OAuthClient(settings, http_client)
    app.state.repository = repository
    app.state.report_service = ReportService(repository, settings.max_report_days)
    yield
    await sessions.close()
    await http_client.aclose()


app = FastAPI(title="BionicPRO Reports BFF", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def _principal(request: Request) -> Principal:
    settings = _settings(request)
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    raw_record = await request.app.state.sessions.get_session(session_id)
    if not raw_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )

    record = SessionRecord.from_dict(raw_record)
    try:
        principal, updated_record = await request.app.state.oauth.principal(record)
    except AuthenticationError as error:
        await request.app.state.sessions.delete_session(session_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)
        ) from error

    if updated_record != record:
        await request.app.state.sessions.update_session(
            session_id, updated_record.as_dict()
        )
    request.state.session_id = session_id
    request.state.session_record = updated_record
    return principal


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(request: Request) -> dict[str, str]:
    redis_ready = await request.app.state.sessions.healthcheck()
    clickhouse_ready = await request.app.state.repository.healthcheck()
    if not redis_ready or not clickhouse_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return {"status": "ready"}


@app.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    settings = _settings(request)
    authorization_url, state_value = await request.app.state.oauth.build_login_url(
        request.app.state.sessions
    )
    response = RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        settings.oauth_state_cookie_name,
        state_value,
        max_age=settings.oauth_transaction_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth/callback",
    )
    return response


@app.get("/auth/callback")
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    settings = _settings(request)
    cookie_state = request.cookies.get(settings.oauth_state_cookie_name)
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state"
        )

    transaction = await request.app.state.sessions.pop_transaction(state)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth transaction expired or was already used",
        )
    try:
        record = await request.app.state.oauth.exchange_code(
            code, str(transaction["code_verifier"])
        )
        await request.app.state.oauth.principal(record)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)
        ) from error

    session_id = secrets.token_urlsafe(32)
    await request.app.state.sessions.create_session(session_id, record.as_dict())
    response = RedirectResponse(
        settings.frontend_url, status_code=status.HTTP_302_FOUND
    )
    response.delete_cookie(settings.oauth_state_cookie_name, path="/auth/callback")
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@app.get("/auth/me")
async def me(principal: Principal = Depends(_principal)) -> dict[str, str | int]:
    return {
        "username": principal.username,
        "customerId": principal.customer_id,
    }


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request,
                 principal: Principal = Depends(_principal),
                 ) -> Response:
    del principal
    settings = _settings(request)
    record: SessionRecord = request.state.session_record
    await request.app.state.oauth.revoke(record.refresh_token)
    await request.app.state.sessions.delete_session(request.state.session_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@app.get("/reports")
async def reports(
    request: Request,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    report_format: Literal["json", "csv"] = Query(default="json", alias="format"),
    principal: Principal = Depends(_principal),
) -> Response:
    resolved_end = end_date or date.today() - timedelta(days=1)
    resolved_start = start_date or resolved_end - timedelta(days=6)
    try:
        report = await request.app.state.report_service.build(
            principal.customer_id, resolved_start, resolved_end
        )
    except InvalidReportPeriod as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except ReportNotReady as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error

    if report_format == "csv":
        return _csv_response(report)
    return JSONResponse(report)


def _csv_response(report: dict[str, object]) -> Response:
    output = io.StringIO()
    columns = [
        "report_date",
        "customer_name",
        "customer_email",
        "prosthesis_count",
        "measurement_count",
        "avg_signal_frequency",
        "avg_signal_duration",
        "avg_signal_amplitude",
        "last_signal_at",
    ]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(report["daily"])
    period = report["period"]
    filename = f"bionicpro-report-{period['from']}-{period['to']}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
