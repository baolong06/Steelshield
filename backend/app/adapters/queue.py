"""Redis job queue for LLM campaigns. Fixture runs never touch Redis."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import redis

from app.core.models import RunRecord
from app.core.settings import get_settings

QUEUE_KEY = "steelshield:jobs"
PROCESSING_QUEUE_KEY = "steelshield:jobs:processing"
RUN_KEY = "steelshield:run:{run_id}"
WORKER_LOCK_KEY = "steelshield:worker:lock"
WORKER_LOCK_CONFLICT = "steelshield worker lock already held; only one worker instance is allowed"

_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

_RENEW_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_client_override: redis.Redis | None = None


class QueueUnavailable(RuntimeError):
    pass


def use_client(client: redis.Redis | None) -> None:
    """Test hook. Production code never calls this."""
    global _client_override
    _client_override = client


def _client(url: str | None = None) -> redis.Redis:
    if _client_override is not None:
        return _client_override
    settings = get_settings()
    try:
        client = redis.Redis.from_url(url or settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except redis.RedisError as exc:
        raise QueueUnavailable(f"Redis is required for LLM campaigns: {exc}") from exc


def enqueue(record: RunRecord, job: dict[str, Any]) -> None:
    client = _client()
    payload = record.to_dict()
    payload["job"] = job
    client.set(RUN_KEY.format(run_id=record.id), json.dumps(payload, ensure_ascii=False))
    client.lpush(QUEUE_KEY, record.id)


def save(record: RunRecord) -> None:
    client = _client()
    raw = client.get(RUN_KEY.format(run_id=record.id))
    job = None
    if raw:
        try:
            job = json.loads(raw).get("job")
        except json.JSONDecodeError:
            job = None
    payload = record.to_dict()
    if job is not None:
        payload["job"] = job
    client.set(RUN_KEY.format(run_id=record.id), json.dumps(payload, ensure_ascii=False))


def load(run_id: str) -> RunRecord | None:
    try:
        client = _client()
    except QueueUnavailable:
        return None
    raw = client.get(RUN_KEY.format(run_id=run_id))
    if not raw:
        return None
    payload = json.loads(raw)
    payload.pop("job", None)
    return RunRecord.from_dict(payload)


def pop_job(timeout: int = 5) -> tuple[str, dict[str, Any]] | None:
    client = _client()
    run_id = client.brpoplpush(QUEUE_KEY, PROCESSING_QUEUE_KEY, timeout=timeout)
    if not run_id:
        return None
    raw = client.get(RUN_KEY.format(run_id=run_id))
    if not raw:
        client.lrem(PROCESSING_QUEUE_KEY, 1, run_id)
        return None
    payload = json.loads(raw)
    job = payload.pop("job", {})
    return run_id, job


def ack_job(run_id: str) -> None:
    _client().lrem(PROCESSING_QUEUE_KEY, 1, run_id)


def recover_inflight() -> int:
    """Requeue jobs left in processing after a worker crash. Call only at worker start."""
    client = _client()
    recovered = 0
    inflight = client.lrange(PROCESSING_QUEUE_KEY, 0, -1)
    for run_id in inflight:
        record = load(run_id)
        client.lrem(PROCESSING_QUEUE_KEY, 1, run_id)
        if record is None or record.status in {"completed", "failed"}:
            continue
        if record.status == "running":
            record.status = "queued"
            record.error = None
            save(record)
        client.lpush(QUEUE_KEY, run_id)
        recovered += 1
    return recovered


def acquire_worker_lock(ttl_sec: int | None = None) -> tuple[bool, str]:
    """Acquire the single-worker lock. Returns (acquired, token)."""
    client = _client()
    token = uuid4().hex
    ttl = int(ttl_sec if ttl_sec is not None else get_settings().worker_lock_ttl_sec)
    acquired = bool(client.set(WORKER_LOCK_KEY, token, nx=True, ex=ttl))
    return acquired, token


def renew_worker_lock(token: str, ttl_sec: int | None = None) -> bool:
    """Extend the lock TTL if this process still owns it."""
    client = _client()
    ttl = int(ttl_sec if ttl_sec is not None else get_settings().worker_lock_ttl_sec)
    return bool(client.eval(_RENEW_LOCK_LUA, 1, WORKER_LOCK_KEY, token, ttl))


def release_worker_lock(token: str) -> bool:
    """Release the lock only if the token still matches (CAS)."""
    client = _client()
    return bool(client.eval(_RELEASE_LOCK_LUA, 1, WORKER_LOCK_KEY, token))
