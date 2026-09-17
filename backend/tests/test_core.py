from __future__ import annotations

import base64

from app.adapters.benchmark_repository import select_cases
from app.core.oracles import evaluate_oracle
from app.core.policy_compiler import compile_policies, get_policy
from app.core.runner import run_cases
from app.core.severity import decide_severity


def test_policy_compiler_loads_the_ten_versioned_policies():
    policies = compile_policies()

    assert len(policies) == 10
    assert get_policy("POL-05").oracle_type == "deterministic_canary"
    assert get_policy("POL-07").statement_vi.startswith("Không gửi")


def test_oracle_detects_raw_and_base64_canaries_and_state_violations():
    case = select_cases("train", ["POL-06"], limit=1)[0]
    canary = case["setup"]["canary"]

    raw = evaluate_oracle(case, f"leak {canary}", {})
    encoded = evaluate_oracle(case, base64.b64encode(canary.encode()).decode(), {})
    state = evaluate_oracle(
        {
            **case,
            "oracle": {"type": "state_oracle", "state_checks": [{"check": "no_external_send"}]},
        },
        "safe",
        {"outbox_new": True},
    )

    assert raw["leaked"] is True
    assert encoded["canary"]["hits"] == [canary]
    assert state["state"]["violations"] == ["external_send"]


def test_severity_preserves_high_impact_and_downgrades_clean_benign_case():
    attack = {"case_type": "attack", "severity": "critical"}
    benign = {"case_type": "benign", "severity": "low"}

    assert decide_severity(attack, prompt_flagged=True, oracle_leaked=True) == "critical"
    assert decide_severity(benign, prompt_flagged=False, oracle_leaked=False) == "info"


def test_runner_scores_hardened_and_vulnerable_twin_simulations_differently():
    cases = select_cases("train", ["POL-06"], limit=2)

    hardened = run_cases(cases, target="hardened")
    vulnerable = run_cases(cases, target="vulnerable")

    assert hardened.metrics.total_cases == 2
    assert hardened.metrics.blocked == 1
    assert hardened.metrics.allowed == 1
    assert hardened.metrics.external_requests == 0
    assert vulnerable.case_results[0]["decision"] == "succeeded"
    assert vulnerable.findings[0].evidence["oracle"]["leaked"] is True
