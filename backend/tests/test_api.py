from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metadata_endpoints_expose_offline_provenance_and_hash_gate():
    health = client.get("/api/v1/health")
    policies = client.get("/api/v1/policies")
    datasets = client.get("/api/v1/datasets")

    assert health.status_code == 200
    assert health.json()["external_requests"] == 0
    from app.core.settings import get_settings

    assert health.json()["declared_egress_host"] == get_settings().egress_host
    assert policies.status_code == 200
    assert policies.json()["count"] == 10
    assert datasets.status_code == 200
    assert all(status == "ok" for status in datasets.json()["integrity"].values())
    assert datasets.json()["status"] == "generated_unreviewed"


def test_run_findings_and_reports_are_available_for_local_synthetic_run():
    response = client.post(
        "/api/v1/runs",
        json={"split": "train", "policy_ids": ["POL-06"], "limit": 2, "target": "hardened"},
    )

    assert response.status_code == 201
    run = response.json()
    assert run["metrics"]["total_cases"] == 2
    assert run["metrics"]["external_requests"] == 0
    assert "not competition evidence" in run["claim_level"]

    findings = client.get("/api/v1/findings", params={"run_id": run["id"]})
    csv = client.get(f"/api/v1/reports/{run['id']}/csv")
    xlsx = client.get(f"/api/v1/reports/{run['id']}/xlsx")

    assert findings.status_code == 200
    assert csv.status_code == 200
    assert "Steelshield" in csv.text
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"


def test_run_request_rejects_unknown_fields_and_unknown_policy():
    extra = client.post("/api/v1/runs", json={"split": "train", "endpoint": "https://example.com"})
    unknown_policy = client.post("/api/v1/runs", json={"policy_ids": ["POL-99"], "limit": 1})
    over_budget = client.post("/api/v1/runs", json={"limit": 301})

    assert extra.status_code == 422
    assert unknown_policy.status_code == 422
    assert over_budget.status_code == 422
