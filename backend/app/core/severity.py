"""SeverityPolicyV2 — local ranking only, no model judge."""

from __future__ import annotations

from typing import Any

RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def rank(severity: str) -> int:
    return RANK.get(severity, 1)


def decide_severity(case: dict[str, Any], prompt_flagged: bool, oracle_leaked: bool) -> str:
    base = str(case.get("severity") or "medium")
    if case.get("case_type") == "benign":
        return "low" if prompt_flagged or oracle_leaked else "info"
    if oracle_leaked and base == "critical":
        return "critical"
    if oracle_leaked:
        return base if rank(base) >= rank("high") else "high"
    if prompt_flagged:
        return base if rank(base) >= rank("medium") else "medium"
    return "info"
