import json
from typing import Any

from redis.asyncio import Redis


class RedisSessionStore:
    def __init__(self, redis_url: str, session_ttl: int, transaction_ttl: int) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._session_ttl = session_ttl
        self._transaction_ttl = transaction_ttl

    async def close(self) -> None:
        await self._redis.aclose()

    async def healthcheck(self) -> bool:
        return bool(await self._redis.ping())

    async def create_transaction(self, state: str, value: dict[str, Any]) -> None:
        await self._redis.setex(
            f"oauth-transaction:{state}",
            self._transaction_ttl,
            json.dumps(value),
        )

    async def pop_transaction(self, state: str) -> dict[str, Any] | None:
        key = f"oauth-transaction:{state}"
        raw = await self._redis.getdel(key)
        return json.loads(raw) if raw else None

    async def create_session(self, session_id: str, value: dict[str, Any]) -> None:
        await self._redis.setex(
            f"session:{session_id}",
            self._session_ttl,
            json.dumps(value),
        )

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        key = f"session:{session_id}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        await self._redis.expire(key, self._session_ttl)
        return json.loads(raw)

    async def update_session(self, session_id: str, value: dict[str, Any]) -> None:
        await self.create_session(session_id, value)

    async def delete_session(self, session_id: str) -> None:
        await self._redis.delete(f"session:{session_id}")

