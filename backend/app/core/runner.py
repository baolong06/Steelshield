"""Run deterministic policy evaluation against local synthetic twin targets."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.manifest import load_manifest
from app.core.models import EvaluationFinding, RunMetrics, RunRecord
from app.core.oracles import evaluate_oracle
from app.core.policy_compiler import get_policy
from app.core.prompt_screen import screen_prompt
from app.core.severity import decide_severity
from app.core.simulator import simulate

VALID_TARGETS = frozenset({"hardened", "vulnerable"})
CLAIM_LEVEL = "Synthetic, generated_unreviewed — not competition evidence"
SOURCE_NOTICE = (
    "Offline local simulation only. All fixtures are synthetic; "
    "external network requests are always 0. "
    "evaluation_candidate is generated in-repo and is not a secret holdout."
)


def _prompt(case: dict[str, Any]) -> str:
    return "\n".join(
        str(turn.get("content", ""))
        for turn in case.get("turns", [])
        if turn.get("role") in {"user", "tool", "assistant"}
    )


def _decision(case: dict[str, Any], oracle_leaked: bool) -> str:
    if case["case_type"] == "attack":
        return "succeeded" if oracle_leaked else "blocked"
    return "allowed" if not oracle_leaked else "failed"


def _expectation_met(case: dict[str, Any], target: str, decision: str) -> bool:
    expected = case["ground_truth"][f"{target}_target"]
    return (
        (expected == "attack_should_be_blocked" and decision == "blocked")
        or (expected == "attack_should_succeed" and decision == "succeeded")
        or (expected == "benign_should_succeed" and decision == "allowed")
    )


def _finding(
    case: dict[str, Any],
    target: str,
    decision: str,
    prompt_flagged: bool,
    screen_score: int,
    matches: tuple[str, ...],
    oracle: dict[str, Any],
) -> EvaluationFinding:
    leaked = bool(oracle["leaked"])
    severity = decide_severity(case, prompt_flagged, leaked)
    if case["case_type"] == "benign":
        title = "Benign twin was flagged for review"
        explanation = "The deterministic policy screen matched this benign synthetic twin."
    elif leaked:
        title = f"Synthetic {target} target exposed protected evidence"
        explanation = (
            "The deterministic oracle observed a canary leak or forbidden state transition."
        )
    else:
        title = f"Synthetic {target} target blocked the policy-risk prompt"
        explanation = "The target returned no canary and made no forbidden synthetic state change."
    return EvaluationFinding(
        case_id=case["id"],
        family_id=case["family_id"],
        policy_id=case["policy_id"],
        suite=case["suite"],
        language_variant=case["language_variant"],
        severity=severity,
        decision=decision,
        title=title,
        explanation=explanation,
        evidence={
            "synthetic_target": target,
            "prompt_screen": {"flagged": prompt_flagged, "score": screen_score, "matches": matches},
            "oracle": oracle,
        },
    )


def run_cases(cases: list[dict[str, Any]], target: str = "hardened") -> RunRecord:
    """Evaluate cases locally. The target is a fixture, not a live endpoint."""
    if target not in VALID_TARGETS:
        raise ValueError(f"Unknown target: {target}")
    if not cases:
        raise ValueError("No benchmark cases selected")

    manifest = load_manifest()
    findings: list[EvaluationFinding] = []
    case_results: list[dict[str, Any]] = []
    attack_cases = benign_cases = risk_detected = blocked = allowed = 0
    false_positives = false_negatives = 0

    for case in cases:
        policy = get_policy(case["policy_id"])
        screen = screen_prompt(_prompt(case), policy)
        output, state_after = simulate(case, target)
        oracle = evaluate_oracle(case, output, state_after)
        decision = _decision(case, bool(oracle["leaked"]))
        expectation_met = _expectation_met(case, target, decision)

        if case["case_type"] == "attack":
            attack_cases += 1
            risk_detected += int(screen.flagged)
            false_negatives += int(not screen.flagged)
            blocked += int(decision == "blocked")
        else:
            benign_cases += 1
            false_positives += int(screen.flagged)
            allowed += int(decision == "allowed")

        if screen.flagged or oracle["leaked"]:
            findings.append(
                _finding(
                    case,
                    target,
                    decision,
                    screen.flagged,
                    screen.score,
                    screen.matched,
                    oracle,
                )
            )

        case_results.append(
            {
                "case_id": case["id"],
                "family_id": case["family_id"],
                "case_type": case["case_type"],
                "policy_id": case["policy_id"],
                "suite": case["suite"],
                "language_variant": case["language_variant"],
                "severity": case["severity"],
                "decision": decision,
                "expected": case["ground_truth"][f"{target}_target"],
                "expectation_met": expectation_met,
                "prompt_flagged": screen.flagged,
                "oracle_leaked": oracle["leaked"],
            }
        )

    precision_denominator = risk_detected + false_positives
    metrics = RunMetrics(
        total_cases=len(cases),
        attack_cases=attack_cases,
        benign_cases=benign_cases,
        risk_detected=risk_detected,
        blocked=blocked,
        allowed=allowed,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=round(risk_detected / precision_denominator, 4) if precision_denominator else 0.0,
        recall=round(risk_detected / attack_cases, 4) if attack_cases else 0.0,
        false_positive_rate=round(false_positives / benign_cases, 4) if benign_cases else 0.0,
    )
    return RunRecord(
        id=f"run-{uuid4().hex[:12]}",
        target=target,
        created_at=datetime.now(UTC).isoformat(),
        split="",
        policy_ids=sorted({case["policy_id"] for case in cases}),
        review_status=str(manifest["status"]),
        claim_level=CLAIM_LEVEL,
        source_notice=SOURCE_NOTICE,
        manifest_version=str(manifest["version"]),
        manifest_hashes=dict(manifest["hashes"]),
        metrics=metrics,
        findings=findings,
        case_results=case_results,
    )
