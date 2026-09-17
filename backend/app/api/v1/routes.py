"""HTTP boundary for the Steelshield policy-first control plane."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.adapters.benchmark_repository import VALID_SPLITS, dataset_summary
from app.adapters.llm_client import LlmGatewayError, ResponsesClient
from app.adapters.queue import QueueUnavailable
from app.core.manifest import dataset_integrity, load_manifest
from app.core.policy_compiler import policy_catalog
from app.core.settings import get_settings
from app.services.report_service import build_csv, build_xlsx
from app.services.run_service import run_store

router = APIRouter(prefix="/api/v1", tags=["offline-evaluator"])


class RunRequest(BaseModel):
    """A deliberately narrow request: no URLs, uploads, or client-provided data."""

    model_config = ConfigDict(extra="forbid")

    split: Literal["train", "calibration", "evaluation_candidate"] = "train"
    policy_ids: list[str] = Field(default_factory=list, max_length=10)
    limit: int | None = Field(default=None, ge=1, le=300)
    target: Literal["hardened", "vulnerable", "llm_hardened", "llm_vulnerable"] = "hardened"
    mode: Literal["fixture", "llm"] = "fixture"
    attacker: Literal["replay", "llm"] = "replay"

    @field_validator("policy_ids")
    @classmethod
    def unique_policy_ids(cls, policy_ids: list[str]) -> list[str]:
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("policy_ids must not contain duplicates")
        if any(not policy_id.startswith("POL-") for policy_id in policy_ids):
            raise ValueError("policy_ids must use the POL-XX form")
        return policy_ids

    @model_validator(mode="after")
    def mode_matches_target(self) -> "RunRequest":
        fixture_targets = {"hardened", "vulnerable"}
        llm_targets = {"llm_hardened", "llm_vulnerable"}
        if self.mode == "fixture" and self.target not in fixture_targets:
            raise ValueError("fixture mode only accepts hardened or vulnerable")
        if self.mode == "llm" and self.target not in llm_targets:
            raise ValueError("llm mode only accepts llm_hardened or llm_vulnerable")
        if self.mode == "fixture" and self.attacker == "llm":
            raise ValueError("fixture mode cannot use an llm attacker")
        return self


def _record_or_404(run_id: str):
    try:
        return run_store.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": "control_plane",
        "fixture_external_requests": 0,
        "external_requests": 0,
        "external_bytes": 0,
        "declared_egress_host": get_settings().egress_host,
    }


@router.get("/llm/health")
def llm_health() -> dict:
    try:
        settings = get_settings()
        if not settings.live_llm_enabled:
            raise HTTPException(
                status_code=503,
                detail="LLM gateway health is disabled; set STEELSHIELD_LIVE_LLM=1 explicitly",
            )
        if not settings.api_key:
            raise HTTPException(status_code=503, detail="STEELSHIELD_LLM_API_KEY is not configured")
        info = ResponsesClient(settings).health()
    except HTTPException:
        raise
    except (LlmGatewayError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "key_configured": True, **info}


@router.get("/policies")
def policies() -> dict:
    return {"items": policy_catalog(), "count": len(policy_catalog())}


@router.get("/datasets")
def datasets() -> dict:
    return {**dataset_summary(), "integrity": dataset_integrity()}


@router.post("/runs", status_code=201)
def create_run(request: RunRequest) -> dict:
    try:
        record = run_store.create(
            split=request.split,
            policy_ids=request.policy_ids,
            limit=request.limit,
            target=request.target,
            mode=request.mode,
            attacker=request.attacker,
        )
    except QueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record.to_dict()


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _record_or_404(run_id).to_dict()


@router.get("/findings")
def findings(run_id: str = Query(min_length=5)) -> dict:
    record = _record_or_404(run_id)
    return {
        "run_id": record.id,
        "claim_level": record.claim_level,
        "items": [finding.to_dict() for finding in record.findings],
        "count": len(record.findings),
    }


@router.get("/reports/{run_id}/csv", response_class=PlainTextResponse)
def export_csv(run_id: str) -> Response:
    record = _record_or_404(run_id)
    return Response(
        content=build_csv(record),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{record.id}.csv"'},
    )


@router.get("/reports/{run_id}/xlsx")
def export_xlsx(run_id: str) -> Response:
    record = _record_or_404(run_id)
    return Response(
        content=build_xlsx(record),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{record.id}.xlsx"'},
    )


@router.get("/manifest")
def manifest() -> dict:
    manifest_data = load_manifest()
    return {
        "version": manifest_data["version"],
        "status": manifest_data["status"],
        "hashes": manifest_data["hashes"],
        "evaluation_candidate_notice": manifest_data["evaluation_candidate_policy"],
        "valid_splits": sorted(VALID_SPLITS),
    }
