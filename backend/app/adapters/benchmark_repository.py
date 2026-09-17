"""Read-only access to the versioned synthetic benchmark files."""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

import yaml

from app.core.manifest import BENCHMARK_ROOT, load_manifest

VALID_SPLITS = frozenset({"train", "calibration", "evaluation_candidate"})


@lru_cache(maxsize=1)
def load_policies() -> list[dict[str, Any]]:
    data = yaml.safe_load(
        (BENCHMARK_ROOT / "policies_vi" / "policies.yaml").read_text(encoding="utf-8")
    )
    policies = data.get("policies", [])
    if not policies:
        raise RuntimeError("No policies found in policies_vi/policies.yaml")
    return policies


def load_cases(split: str) -> list[dict[str, Any]]:
    if split not in VALID_SPLITS:
        raise ValueError(f"Unknown split: {split}")
    path = BENCHMARK_ROOT / "splits" / f"{split}.jsonl"
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def select_cases(
    split: str,
    policy_ids: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cases = load_cases(split)
    selected_policy_ids = set(policy_ids or [])
    if selected_policy_ids:
        cases = [case for case in cases if case["policy_id"] in selected_policy_ids]
    if limit is not None:
        cases = cases[:limit]
    return cases


def dataset_summary() -> dict[str, Any]:
    manifest = load_manifest()
    split_counts = manifest.get("split", {})
    return {
        "version": str(manifest["version"]),
        "status": manifest["status"],
        "total_cases": manifest["total_cases"],
        "total_families": manifest["total_families"],
        "splits": [
            {
                "id": name,
                "case_count": count,
                "purpose": {
                    "train": "Canonical synthetic development cases.",
                    "calibration": "Paraphrased synthetic calibration cases.",
                    "evaluation_candidate": (
                        "Generated in-repo candidates — not a secret holdout "
                        "or competition evidence."
                    ),
                }[name],
            }
            for name, count in split_counts.items()
        ],
        "hashes": manifest["hashes"],
        "notice": (
            "All records are synthetic. Every case remains generated_unreviewed "
            "pending human R0 review."
        ),
        "egress": {"external_requests": 0, "external_bytes": 0},
    }
