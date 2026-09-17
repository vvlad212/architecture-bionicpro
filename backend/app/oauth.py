import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx

from .config import Settings
from .models import Principal, SessionRecord
from .sessions import RedisSessionStore


class AuthenticationError(Exception):
    pass


def create_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OAuthClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def build_login_url(self, sessions: RedisSessionStore) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        verifier, challenge = create_pkce_pair()
        await sessions.create_transaction(state, {"code_verifier": verifier})
        query = urlencode(
            {
                "client_id": self._settings.oidc_client_id,
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": self._settings.oidc_redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return (
            f"{self._settings.oidc_public_realm_url}/protocol/openid-connect/auth?{query}",
            state,
        )

    async def exchange_code(self, code: str, code_verifier: str) -> SessionRecord:
        response = await self._http.post(
            f"{self._settings.oidc_internal_realm_url}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self._settings.oidc_client_id,
                "client_secret": self._settings.oidc_client_secret,
                "redirect_uri": self._settings.oidc_redirect_uri,
                "code": code,
                "code_verifier": code_verifier,
            },
        )
        if response.status_code != 200:
            raise AuthenticationError(
                "Identity provider rejected the authorization code"
            )
        payload = response.json()
        return self._session_from_token_response(payload)

    async def principal(self, record: SessionRecord) -> tuple[Principal, SessionRecord]:
        if record.expires_at <= time.time() + 15:
            record = await self._refresh(record)

        response = await self._http.get(
            f"{self._settings.oidc_internal_realm_url}/protocol/openid-connect/userinfo",
            headers={"Authorization": f"Bearer {record.access_token}"},
        )
        if response.status_code == 401 and record.refresh_token:
            record = await self._refresh(record)
            response = await self._http.get(
                f"{self._settings.oidc_internal_realm_url}/protocol/openid-connect/userinfo",
                headers={"Authorization": f"Bearer {record.access_token}"},
            )
        if response.status_code != 200:
            raise AuthenticationError("Session is no longer valid")

        claims = response.json()
        try:
            customer_id = int(claims["customer_id"])
            subject = str(claims["sub"])
        except (KeyError, TypeError, ValueError) as error:
            raise AuthenticationError(
                "The account is not linked to a BionicPRO customer"
            ) from error

        return (
            Principal(
                subject=subject,
                customer_id=customer_id,
                username=str(claims.get("preferred_username", subject)),
            ),
            record,
        )

    async def revoke(self, refresh_token: str) -> None:
        if not refresh_token:
            return
        await self._http.post(
            f"{self._settings.oidc_internal_realm_url}/protocol/openid-connect/logout",
            data={
                "client_id": self._settings.oidc_client_id,
                "client_secret": self._settings.oidc_client_secret,
                "refresh_token": refresh_token,
            },
        )

    async def _refresh(self, record: SessionRecord) -> SessionRecord:
        if not record.refresh_token:
            raise AuthenticationError("Session cannot be refreshed")
        response = await self._http.post(
            f"{self._settings.oidc_internal_realm_url}/protocol/openid-connect/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self._settings.oidc_client_id,
                "client_secret": self._settings.oidc_client_secret,
                "refresh_token": record.refresh_token,
            },
        )
        if response.status_code != 200:
            raise AuthenticationError("Session refresh was rejected")
        return self._session_from_token_response(response.json())

    @staticmethod
    def _session_from_token_response(payload: dict[str, object]) -> SessionRecord:
        access_token = str(payload.get("access_token", ""))
        refresh_token = str(payload.get("refresh_token", ""))
        if not access_token:
            raise AuthenticationError("Identity provider returned no access token")
        expires_in = int(payload.get("expires_in", 300))
        return SessionRecord(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
        )
