"""Compile the versioned Vietnamese policy declarations into local deterministic rules."""

from __future__ import annotations

from functools import lru_cache

from app.adapters.benchmark_repository import load_policies
from app.core.models import CompiledPolicy


@lru_cache(maxsize=1)
def compile_policies() -> dict[str, CompiledPolicy]:
    compiled: dict[str, CompiledPolicy] = {}
    for policy in load_policies():
        item = CompiledPolicy(
            id=policy["id"],
            name=policy["name"],
            statement_vi=policy["statement_vi"],
            oracle_type=policy["oracle"],
            allowed_examples=tuple(policy.get("allowed_examples", [])),
            forbidden_examples=tuple(policy.get("forbidden_examples", [])),
        )
        compiled[item.id] = item
    return compiled


def get_policy(policy_id: str) -> CompiledPolicy:
    try:
        return compile_policies()[policy_id]
    except KeyError as exc:
        raise ValueError(f"Unknown policy: {policy_id}") from exc


def policy_catalog() -> list[dict]:
    return [policy.to_dict() for policy in compile_policies().values()]
