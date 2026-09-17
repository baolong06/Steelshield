"""Application service for fixture runs (sync) and queued LLM campaigns."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.adapters import queue as job_queue
from app.adapters.benchmark_repository import select_cases
from app.core.campaign import LLM_SOURCE_NOTICE, LLM_TARGETS, assert_within_request_budget
from app.core.manifest import dataset_integrity, load_manifest
from app.core.models import RunMetrics, RunRecord
from app.core.policy_compiler import get_policy
from app.core.runner import CLAIM_LEVEL, VALID_TARGETS, run_cases
from app.core.settings import get_settings


def _empty_metrics() -> RunMetrics:
    return RunMetrics(
        total_cases=0,
        attack_cases=0,
        benign_cases=0,
        risk_detected=0,
        blocked=0,
        allowed=0,
        false_positives=0,
        false_negatives=0,
        precision=0.0,
        recall=0.0,
        false_positive_rate=0.0,
    )


class RunStore:
    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}

    def create(
        self,
        split: str,
        policy_ids: list[str] | None = None,
        limit: int | None = None,
        target: str = "hardened",
        mode: str = "fixture",
        attacker: str = "replay",
    ) -> RunRecord:
        integrity = dataset_integrity()
        failures = [name for name, status in integrity.items() if status != "ok"]
        if failures:
            raise RuntimeError(f"Dataset integrity gate failed: {', '.join(failures)}")
        for policy_id in policy_ids or []:
            get_policy(policy_id)
        effective_limit = limit if limit is not None else (4 if mode == "llm" else 20)
        cases = select_cases(split, policy_ids, effective_limit)
        manifest = load_manifest()
        max_requests = int(manifest["budget_lock"]["max_requests"])
        if mode == "llm":
            assert_within_request_budget(len(cases), attacker)
        elif len(cases) > max_requests:
            raise ValueError(f"Selection exceeds benchmark budget_lock.max_requests={max_requests}")

        if mode == "fixture":
            if target not in VALID_TARGETS:
                raise ValueError(f"Unknown fixture target: {target}")
            record = run_cases(cases, target)
            record.split = split
            record.mode = "fixture"
            record.attacker = "replay"
            record.status = "completed"
            self._records[record.id] = record
            return record

        if mode != "llm":
            raise ValueError(f"Unknown mode: {mode}")
        if target not in LLM_TARGETS:
            raise ValueError(f"Unknown LLM target: {target}")
        if attacker not in {"replay", "llm"}:
            raise ValueError(f"Unknown attacker: {attacker}")

        settings = get_settings()
        if not settings.live_llm_enabled:
            raise job_queue.QueueUnavailable(
                "LLM campaigns are disabled; set STEELSHIELD_LIVE_LLM=1 explicitly"
            )
        if not settings.api_key:
            raise job_queue.QueueUnavailable("STEELSHIELD_LLM_API_KEY is not configured")

        manifest = load_manifest()
        record = RunRecord(
            id=f"run-{uuid4().hex[:12]}",
            target=target,
            created_at=datetime.now(UTC).isoformat(),
            split=split,
            policy_ids=sorted({case["policy_id"] for case in cases}),
            review_status=str(manifest["status"]),
            claim_level=CLAIM_LEVEL,
            source_notice=LLM_SOURCE_NOTICE,
            manifest_version=str(manifest["version"]),
            manifest_hashes=dict(manifest["hashes"]),
            metrics=_empty_metrics(),
            status="queued",
            mode="llm",
            attacker=attacker,
            egress_host=settings.egress_host,
        )
        job_queue.enqueue(
            record,
            {
                "split": split,
                "policy_ids": list(policy_ids or []),
                "limit": effective_limit,
                "target": target,
                "attacker": attacker,
            },
        )
        self._records[record.id] = record
        return record

    def get(self, run_id: str) -> RunRecord:
        local = self._records.get(run_id)
        if local is not None and local.mode != "llm":
            return local
        remote = job_queue.load(run_id)
        if remote is not None:
            self._records[run_id] = remote
            return remote
        if local is not None:
            return local
        raise KeyError(f"Run not found: {run_id}")


run_store = RunStore()
