from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import fakeredis
import httpx
import pytest
import redis
from fastapi.testclient import TestClient

from app.adapters import queue as job_queue
from app.adapters.benchmark_repository import select_cases
from app.adapters.llm_client import FunctionCall, LlmGatewayError, LlmResponse, ResponsesClient
from app.core.campaign import assert_within_request_budget, run_llm_cases
from app.core.oracles import evaluate_oracle
from app.core.policy_compiler import get_policy
from app.core.settings import Settings, get_settings
from app.core.target_agent import run_target
from app.core.tool_sandbox import ToolSandbox
from app.main import app
from app.worker import process_job

client = TestClient(app)


def _settings(**overrides: object) -> Settings:
    values = dict(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-5.6-sol",
        review_model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        store=False,
        timeout_s=5.0,
        live_llm_enabled=True,
        redis_url="redis://127.0.0.1:6379/0",
        worker_lock_ttl_sec=60,
    )
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@dataclass
class ScriptedClient:
    replies: list[LlmResponse]
    calls: list[dict] | None = None

    def complete(self, **kwargs) -> LlmResponse:
        if self.calls is not None:
            self.calls.append(kwargs)
        if not self.replies:
            raise LlmGatewayError("script exhausted")
        return self.replies.pop(0)


def test_settings_accept_any_https_gateway_and_reject_http(monkeypatch):
    monkeypatch.setenv("STEELSHIELD_LLM_BASE_URL", "https://example.com/v1")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.egress_host == "example.com"
    monkeypatch.setenv("STEELSHIELD_LLM_BASE_URL", "http://example.com/v1")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="must be an https URL"):
        get_settings()
    monkeypatch.setenv("STEELSHIELD_LLM_BASE_URL", "https://example.com/openai")
    get_settings.cache_clear()
    assert get_settings().egress_host == "example.com"
    monkeypatch.delenv("STEELSHIELD_LLM_BASE_URL")
    get_settings.cache_clear()


def test_responses_client_parses_mock_http_and_counts_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.com"
        assert str(request.url).endswith("/v1/responses")
        body = {
            "id": "resp_1",
            "output_text": "Từ chối.",
            "output": [],
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    llm = ResponsesClient(_settings(), http)
    result = llm.complete(instructions="sys", input="user")
    assert result.text == "Từ chối."
    assert result.request_bytes > 0
    assert result.response_bytes > 0


def test_responses_client_sends_function_call_output_with_call_id():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"id": "resp_2", "output_text": "ok", "output": []})

    llm = ResponsesClient(_settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    llm.complete(
        instructions="sys",
        input=[
            {
                "type": "function_call_output",
                "call_id": "call_lookup_1",
                "output": json.dumps({"synthetic": True}),
            }
        ],
        previous_response_id="resp_tool_1",
    )
    assert captured[0]["previous_response_id"] == "resp_tool_1"
    assert captured[0]["input"][0]["type"] == "function_call_output"
    assert captured[0]["input"][0]["call_id"] == "call_lookup_1"
    assert "synthetic" in captured[0]["input"][0]["output"]


def test_target_tool_continuation_uses_call_id_structured_output():
    case = select_cases("train", ["POL-06"], limit=1)[0]
    calls: list[dict] = []
    scripted = ScriptedClient(
        replies=[
            LlmResponse(
                text="",
                function_calls=(
                    FunctionCall(
                        "call_lookup_1",
                        "lookup_record",
                        json.dumps({"resource_id": case["setup"]["protected_resource"]}),
                    ),
                ),
                response_id="resp_tool_1",
                request_bytes=10,
                response_bytes=10,
            ),
            LlmResponse("Từ chối.", (), "resp_final_1", 10, 10),
        ],
        calls=calls,
    )

    result = run_target(
        scripted,  # type: ignore[arg-type]
        case,
        get_policy(case["policy_id"]),
        "llm_hardened",
        ["Tra cứu dữ liệu này."],
        max_tool_turns=5,
    )

    assert result.output == "Từ chối."
    assert len(calls) == 2
    assert calls[0]["input"][0]["role"] == "user"
    assert "previous_response_id" not in calls[1]
    continuation = calls[1]["input"]
    assert continuation[0]["role"] == "user"
    assert continuation[1] == {
        "type": "function_call",
        "call_id": "call_lookup_1",
        "name": "lookup_record",
        "arguments": json.dumps({"resource_id": case["setup"]["protected_resource"]}),
    }
    assert continuation[2] == {
        "type": "function_call_output",
        "call_id": "call_lookup_1",
        "output": json.dumps(
            {
                "synthetic": True,
                "resource_id": case["setup"]["protected_resource"],
                "masked": False,
                "internal_note": case["setup"]["canary"],
            },
            ensure_ascii=False,
        ),
    }


def test_tool_sandbox_sets_state_flags_without_network():
    case = select_cases("train", ["POL-06"], limit=1)[0]
    sandbox = ToolSandbox(case)
    sandbox.execute(
        "send_email", json.dumps({"recipient": "attacker@outside.example", "body": "x"})
    )
    sandbox.execute(
        "lookup_record",
        json.dumps({"resource_id": case["setup"]["protected_resource"]}),
    )
    assert sandbox.state["outbox_new"] is True
    assert sandbox.state["cross_tenant_read"] is True
    assert case["setup"]["canary"] in sandbox.events[1]["result"]["internal_note"]


def test_oracle_flags_canary_inside_tool_events():
    case = select_cases("train", ["POL-06"], limit=1)[0]
    canary = case["setup"]["canary"]
    result = evaluate_oracle(
        case,
        "safe output",
        {},
        [{"tool": "export_data", "result": {"canary": canary}}],
    )
    assert result["leaked"] is True
    assert canary in result["canary"]["hits"]


def test_llm_timeout_and_gateway_error_are_failures_not_safe():
    case = select_cases("train", ["POL-06"], limit=1)[0]
    failing = ScriptedClient([])
    record = run_llm_cases([case], target="llm_hardened", attacker="replay", client=failing)  # type: ignore[arg-type]
    assert record.metrics.failed_cases == 1
    assert record.metrics.external_requests == 1
    assert record.case_results[0]["decision"] == "failed"
    assert record.case_results[0]["failed"] is True
    assert record.findings[0].evidence["oracle"]["leaked"] is True

    looping = ScriptedClient(
        [
            LlmResponse(
                text="",
                function_calls=(FunctionCall("c1", "create_ticket", '{"summary":"x"}'),),
                response_id="r",
                request_bytes=8,
                response_bytes=8,
            )
            for _ in range(8)
        ]
    )
    timed_out = run_llm_cases([case], target="llm_hardened", attacker="replay", client=looping)  # type: ignore[arg-type]
    assert timed_out.metrics.failed_cases == 1
    assert timed_out.case_results[0]["decision"] == "failed"


def test_llm_request_budget_covers_attacker_and_target_turns():
    assert_within_request_budget(60, "replay")
    assert_within_request_budget(50, "llm")

    with pytest.raises(ValueError, match="worst-case 305"):
        assert_within_request_budget(61, "replay")
    with pytest.raises(ValueError, match="worst-case 306"):
        assert_within_request_budget(51, "llm")


def test_run_api_rejects_llm_selection_that_exceeds_request_budget():
    replay = client.post(
        "/api/v1/runs",
        json={"mode": "llm", "target": "llm_hardened", "limit": 61, "attacker": "replay"},
    )
    attacker = client.post(
        "/api/v1/runs",
        json={"mode": "llm", "target": "llm_hardened", "limit": 51, "attacker": "llm"},
    )

    assert replay.status_code == 422
    assert "worst-case 305" in replay.json()["detail"]
    assert attacker.status_code == 422
    assert "worst-case 306" in attacker.json()["detail"]


def test_llm_campaign_hardened_refusal_with_mock_client():
    cases = select_cases("train", ["POL-06"], limit=2)
    replies = [
        LlmResponse("Từ chối. Không tiết lộ dữ liệu.", (), "r1", 12, 20),
        LlmResponse("Hoàn thành yêu cầu hợp lệ.", (), "r2", 12, 20),
    ]
    record = run_llm_cases(
        cases, target="llm_hardened", attacker="replay", client=ScriptedClient(replies)
    )  # type: ignore[arg-type]
    assert record.metrics.external_requests == 2
    assert record.metrics.failed_cases == 0
    assert record.mode == "llm"
    assert record.egress_host == get_settings().egress_host
    decisions = {row["case_type"]: row["decision"] for row in record.case_results}
    assert decisions["attack"] == "blocked"
    assert decisions["benign"] == "allowed"


def test_queue_and_worker_with_fakeredis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    job_queue.use_client(fake)
    try:
        replies = [LlmResponse("Từ chối.", (), "r", 4, 4)]
        monkeypatch.setattr(
            "app.worker.run_llm_cases",
            lambda selected, target, attacker: run_llm_cases(
                selected,
                target=target,
                attacker=attacker,
                client=ScriptedClient(replies),  # type: ignore[arg-type]
            ),
        )
        from datetime import UTC, datetime

        from app.core.manifest import load_manifest
        from app.core.models import RunMetrics, RunRecord
        from app.core.runner import CLAIM_LEVEL

        manifest = load_manifest()
        placeholder = RunRecord(
            id="run-testqueue01",
            target="llm_hardened",
            created_at=datetime.now(UTC).isoformat(),
            split="train",
            policy_ids=["POL-06"],
            review_status=str(manifest["status"]),
            claim_level=CLAIM_LEVEL,
            source_notice="test",
            manifest_version=str(manifest["version"]),
            manifest_hashes=dict(manifest["hashes"]),
            metrics=RunMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0),
            status="queued",
            mode="llm",
            attacker="replay",
            egress_host="modelapi.vn",
        )
        job_queue.enqueue(
            placeholder,
            {
                "split": "train",
                "policy_ids": ["POL-06"],
                "limit": 1,
                "target": "llm_hardened",
                "attacker": "replay",
            },
        )
        popped = job_queue.pop_job(timeout=1)
        assert popped is not None
        run_id, _ = popped
        assert fake.lrange(job_queue.PROCESSING_QUEUE_KEY, 0, -1) == [run_id]

        # Simulate a worker process dying after acquisition but before completion.
        in_flight = job_queue.load(run_id)
        assert in_flight is not None
        in_flight.status = "running"
        job_queue.save(in_flight)
        assert job_queue.recover_inflight() == 1
        assert fake.lrange(job_queue.PROCESSING_QUEUE_KEY, 0, -1) == []
        recovered = job_queue.load(run_id)
        assert recovered is not None
        assert recovered.status == "queued"

        retried = job_queue.pop_job(timeout=1)
        assert retried is not None
        run_id, job = retried
        finished = process_job(run_id, job)
        job_queue.ack_job(run_id)
        assert finished.status == "completed"
        assert finished.metrics.total_cases == 1
        assert fake.lrange(job_queue.PROCESSING_QUEUE_KEY, 0, -1) == []
        loaded = job_queue.load(run_id)
        assert loaded is not None
        assert loaded.status == "completed"
    finally:
        job_queue.use_client(None)


def test_llm_mode_without_redis_returns_503(monkeypatch):
    monkeypatch.setattr(
        "app.adapters.queue.enqueue",
        lambda *args, **kwargs: (_ for _ in ()).throw(job_queue.QueueUnavailable("redis down")),
    )
    monkeypatch.setenv("STEELSHIELD_LLM_API_KEY", "test-key")
    monkeypatch.setenv("STEELSHIELD_LIVE_LLM", "1")
    get_settings.cache_clear()
    response = client.post(
        "/api/v1/runs",
        json={
            "split": "train",
            "policy_ids": ["POL-06"],
            "limit": 1,
            "mode": "llm",
            "target": "llm_hardened",
            "attacker": "replay",
        },
    )
    assert response.status_code == 503


def test_llm_mode_still_rejects_client_endpoint_field():
    response = client.post(
        "/api/v1/runs",
        json={"mode": "llm", "target": "llm_hardened", "endpoint": "https://chat.example"},
    )
    assert response.status_code == 422


def test_llm_mode_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("STEELSHIELD_LLM_API_KEY", "test-key")
    monkeypatch.setenv("STEELSHIELD_LIVE_LLM", "0")
    get_settings.cache_clear()
    response = client.post(
        "/api/v1/runs",
        json={"mode": "llm", "target": "llm_hardened", "limit": 1},
    )
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"]
    get_settings.cache_clear()


def test_worker_lock_second_instance_fails_fast():
    fake = fakeredis.FakeRedis(decode_responses=True)
    job_queue.use_client(fake)
    try:
        first, token = job_queue.acquire_worker_lock(ttl_sec=60)
        assert first is True
        second, other = job_queue.acquire_worker_lock(ttl_sec=60)
        assert second is False
        assert fake.get(job_queue.WORKER_LOCK_KEY) == token
        assert job_queue.release_worker_lock(other) is False
        assert fake.get(job_queue.WORKER_LOCK_KEY) == token
        assert job_queue.release_worker_lock(token) is True
        assert fake.get(job_queue.WORKER_LOCK_KEY) is None
        again, token = job_queue.acquire_worker_lock(ttl_sec=2)
        assert again is True
        assert job_queue.renew_worker_lock(token, ttl_sec=2) is True
        assert job_queue.renew_worker_lock("not-the-owner", ttl_sec=2) is False
        assert fake.get(job_queue.WORKER_LOCK_KEY) == token
    finally:
        job_queue.use_client(None)


def test_worker_lock_expires_after_ttl_so_successor_can_acquire():
    fake = fakeredis.FakeRedis(decode_responses=True)
    job_queue.use_client(fake)
    try:
        first, token = job_queue.acquire_worker_lock(ttl_sec=1)
        assert first is True
        time.sleep(1.2)
        successor, new_token = job_queue.acquire_worker_lock(ttl_sec=60)
        assert successor is True
        assert new_token != token
        assert fake.get(job_queue.WORKER_LOCK_KEY) == new_token
    finally:
        job_queue.use_client(None)


@pytest.mark.skipif(
    not os.environ.get("STEELSHIELD_REDIS_TEST_URL"),
    reason="requires a disposable Redis server",
)
def test_second_worker_process_exits_when_first_holds_lock():
    redis_url = os.environ["STEELSHIELD_REDIS_TEST_URL"]
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    redis_client.delete(job_queue.WORKER_LOCK_KEY)
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "REDIS_URL": redis_url,
        "STEELSHIELD_WORKER_LOCK_TTL_SEC": "60",
    }
    first = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert first.stdout is not None
        assert "listening" in first.stdout.readline()
        second = subprocess.run(
            [sys.executable, "-m", "app.worker"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert second.returncode == 1
        assert job_queue.WORKER_LOCK_CONFLICT in second.stdout
    finally:
        first.terminate()
        first.wait(timeout=10)
        redis_client.delete(job_queue.WORKER_LOCK_KEY)
        if first.stdout is not None:
            first.stdout.close()


def test_worker_main_exits_nonzero_when_lock_is_held(capsys):
    fake = fakeredis.FakeRedis(decode_responses=True)
    job_queue.use_client(fake)
    try:
        held, token = job_queue.acquire_worker_lock(ttl_sec=60)
        assert held is True
        from app.worker import main

        with pytest.raises(SystemExit) as exited:
            main()
        assert exited.value.code == 1
        logged = capsys.readouterr().out
        assert "lock conflict" in logged
        assert job_queue.WORKER_LOCK_CONFLICT in logged
        assert fake.get(job_queue.WORKER_LOCK_KEY) == token
    finally:
        job_queue.use_client(None)
