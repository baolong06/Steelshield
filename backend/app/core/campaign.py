"""Campaign orchestration: attacker → target → deterministic oracle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.adapters.llm_client import LlmGatewayError, ResponsesClient
from app.core.attacker_agent import generate_turn, replay_turns
from app.core.manifest import load_manifest
from app.core.models import EvaluationFinding, RunMetrics, RunRecord
from app.core.oracles import evaluate_oracle
from app.core.policy_compiler import get_policy
from app.core.prompt_screen import screen_prompt
from app.core.runner import CLAIM_LEVEL, _decision, _expectation_met, _finding, _prompt
from app.core.settings import get_settings
from app.core.target_agent import run_target

LLM_TARGETS = frozenset({"llm_hardened", "llm_vulnerable"})
LLM_SOURCE_NOTICE = (
    "LLM attacker/target run against synthetic evaluation cases. "
    "Egress is the operator-configured LLM gateway. Tools are local mocks. "
    "Deterministic oracles remain the pass/fail authority. "
    "evaluation_candidate is generated in-repo and is not a secret holdout."
)


def assert_within_request_budget(case_count: int, attacker: str) -> None:
    """Reject LLM selections that could exceed the manifest request lock."""
    if attacker not in {"replay", "llm"}:
        raise ValueError(f"Unknown attacker: {attacker}")
    budget = load_manifest()["budget_lock"]
    max_requests = int(budget["max_requests"])
    max_turns = int(budget["max_turns_per_case"])
    per_case = max_turns + (1 if attacker == "llm" else 0)
    worst = case_count * per_case
    if worst > max_requests:
        raise ValueError(
            f"Selection exceeds benchmark budget_lock.max_requests={max_requests} "
            f"(worst-case {worst} = {case_count} cases x {per_case} req/case, "
            f"max_turns={max_turns}, attacker={attacker})"
        )


def _fixture_target(llm_target: str) -> str:
    return "hardened" if llm_target.endswith("hardened") else "vulnerable"


def run_llm_cases(
    cases: list[dict[str, Any]],
    *,
    target: str,
    attacker: str,
    client: ResponsesClient | None = None,
) -> RunRecord:
    if target not in LLM_TARGETS:
        raise ValueError(f"Unknown LLM target: {target}")
    if attacker not in {"replay", "llm"}:
        raise ValueError(f"Unknown attacker: {attacker}")
    if not cases:
        raise ValueError("No benchmark cases selected")

    settings = get_settings()
    llm = client or ResponsesClient(settings)
    manifest = load_manifest()
    assert_within_request_budget(len(cases), attacker)
    max_turns = int(manifest["budget_lock"]["max_turns_per_case"])
    findings: list[EvaluationFinding] = []
    case_results: list[dict[str, Any]] = []
    attack_cases = benign_cases = risk_detected = blocked = allowed = 0
    false_positives = false_negatives = failed_cases = 0
    external_requests = external_bytes = 0
    fixture_key = _fixture_target(target)

    for case in cases:
        policy = get_policy(case["policy_id"])
        screen = screen_prompt(_prompt(case), policy)
        result = None
        try:
            if attacker == "replay":
                turns = replay_turns(case)
            else:
                text, req_b, res_b = generate_turn(llm, case, policy, "")
                external_requests += 1
                external_bytes += req_b + res_b
                if not text:
                    raise LlmGatewayError("Attacker produced no user turn")
                turns = [text]
            if not turns:
                raise LlmGatewayError("Attacker produced no user turn")
            result = run_target(llm, case, policy, target, turns, max_turns)
            if result.error:
                raise LlmGatewayError(result.error)
            oracle = evaluate_oracle(case, result.output, result.state_after, result.tool_events)
            if result.state_after.get("agent_timeout"):
                raise LlmGatewayError("Target agent exceeded max tool turns")
            decision = _decision(case, bool(oracle["leaked"]))
            expectation_met = _expectation_met(case, fixture_key, decision)
            failed = False
        except Exception as exc:  # timeout / gateway / not-run count as FAIL, never safe
            failed = True
            failed_cases += 1
            oracle = {
                "oracle_type": case.get("oracle", {}).get("type", "deterministic_canary"),
                "leaked": True,
                "canary": {"leaked": False, "hits": []},
                "state": {"violations": ["not_run"]},
                "error": str(exc),
            }
            decision = "failed"
            expectation_met = False

        if result is not None:
            external_requests += result.external_requests
            external_bytes += result.external_bytes

        if case["case_type"] == "attack":
            attack_cases += 1
            risk_detected += int(screen.flagged)
            false_negatives += int(not screen.flagged)
            blocked += int(decision == "blocked")
        else:
            benign_cases += 1
            false_positives += int(screen.flagged)
            allowed += int(decision == "allowed")

        if screen.flagged or oracle["leaked"] or failed:
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
                "expected": case["ground_truth"][f"{fixture_key}_target"],
                "expectation_met": expectation_met,
                "prompt_flagged": screen.flagged,
                "oracle_leaked": oracle["leaked"],
                "failed": failed,
                "tool_events": list(result.tool_events) if result else [],
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
        external_requests=external_requests,
        external_bytes=external_bytes,
        failed_cases=failed_cases,
    )
    return RunRecord(
        id=f"run-{uuid4().hex[:12]}",
        target=target,
        created_at=datetime.now(UTC).isoformat(),
        split="",
        policy_ids=sorted({case["policy_id"] for case in cases}),
        review_status=str(manifest["status"]),
        claim_level=CLAIM_LEVEL,
        source_notice=LLM_SOURCE_NOTICE,
        manifest_version=str(manifest["version"]),
        manifest_hashes=dict(manifest["hashes"]),
        metrics=metrics,
        status="completed",
        mode="llm",
        attacker=attacker,
        egress_host=settings.egress_host,
        findings=findings,
        case_results=case_results,
    )
