"""Redis worker: execute queued LLM campaigns and persist RunRecord."""

from __future__ import annotations

import atexit
import os
import signal
import sys
from threading import Event, Thread

from app.adapters import queue
from app.adapters.benchmark_repository import select_cases
from app.core.campaign import assert_within_request_budget, run_llm_cases
from app.core.models import RunRecord
from app.core.settings import get_settings


def process_job(run_id: str, job: dict) -> RunRecord:
    placeholder = queue.load(run_id)
    if placeholder is None:
        raise KeyError(run_id)
    placeholder.status = "running"
    queue.save(placeholder)
    cases = select_cases(job["split"], job.get("policy_ids"), job.get("limit"))
    assert_within_request_budget(len(cases), job["attacker"])
    record = run_llm_cases(cases, target=job["target"], attacker=job["attacker"])
    record.id = run_id
    record.split = job["split"]
    record.status = "completed"
    queue.save(record)
    return record


def _heartbeat(token: str, stop: Event) -> None:
    interval = max(1, get_settings().worker_lock_ttl_sec // 3)
    while not stop.wait(interval):
        if not queue.renew_worker_lock(token):
            print("steelshield worker lost lock; exiting", flush=True)
            os._exit(1)


def main() -> None:
    acquired, token = queue.acquire_worker_lock()
    if not acquired:
        print(f"steelshield worker lock conflict: {queue.WORKER_LOCK_CONFLICT}", flush=True)
        sys.exit(1)

    stop = Event()

    def _release() -> None:
        stop.set()
        try:
            queue.release_worker_lock(token)
        except Exception:
            pass

    atexit.register(_release)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda *_: sys.exit(0))
        except ValueError:
            pass

    Thread(target=_heartbeat, args=(token, stop), daemon=True).start()
    recovered = queue.recover_inflight()
    print(f"steelshield worker listening on Redis recovered={recovered}", flush=True)
    while True:
        popped = queue.pop_job(timeout=5)
        if not popped:
            continue
        run_id, job = popped
        try:
            process_job(run_id, job)
            print(f"completed {run_id}", flush=True)
        except Exception as exc:  # noqa: BLE001 — persist failure, keep worker alive
            record = queue.load(run_id)
            if record is not None:
                record.status = "failed"
                record.error = str(exc)
                queue.save(record)
            print(f"failed {run_id}: {exc}", flush=True)
            queue.ack_job(run_id)
        else:
            queue.ack_job(run_id)


if __name__ == "__main__":
    main()
