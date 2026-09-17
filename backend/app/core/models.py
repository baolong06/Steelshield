"""Domain models kept independent from FastAPI and file adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CompiledPolicy:
    """A Vietnamese policy compiled into a deterministic local rule."""

    id: str
    name: str
    statement_vi: str
    oracle_type: str
    allowed_examples: tuple[str, ...]
    forbidden_examples: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationFinding:
    """A risk detected in a synthetic benchmark case before target execution."""

    case_id: str
    family_id: str
    policy_id: str
    suite: str
    language_variant: str
    severity: str
    decision: str
    title: str
    explanation: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunMetrics:
    total_cases: int
    attack_cases: int
    benign_cases: int
    risk_detected: int
    blocked: int
    allowed: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    false_positive_rate: float
    external_requests: int = 0
    external_bytes: int = 0
    failed_cases: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunRecord:
    id: str
    target: str
    created_at: str
    split: str
    policy_ids: list[str]
    review_status: str
    claim_level: str
    source_notice: str
    manifest_version: str
    manifest_hashes: dict[str, str]
    metrics: RunMetrics
    status: str = "completed"
    mode: str = "fixture"
    attacker: str = "replay"
    egress_host: str | None = None
    error: str | None = None
    findings: list[EvaluationFinding] = field(default_factory=list)
    case_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, include_findings: bool = True) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "target": self.target,
            "created_at": self.created_at,
            "split": self.split,
            "policy_ids": self.policy_ids,
            "review_status": self.review_status,
            "claim_level": self.claim_level,
            "source_notice": self.source_notice,
            "status": self.status,
            "mode": self.mode,
            "attacker": self.attacker,
            "egress_host": self.egress_host,
            "error": self.error,
            "manifest_version": self.manifest_version,
            "manifest_hashes": self.manifest_hashes,
            "metrics": self.metrics.to_dict(),
            "case_results": self.case_results,
        }
        if include_findings:
            payload["findings"] = [finding.to_dict() for finding in self.findings]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        metrics = RunMetrics(**payload["metrics"])
        findings = [EvaluationFinding(**item) for item in payload.get("findings", [])]
        return cls(
            id=payload["id"],
            target=payload["target"],
            created_at=payload["created_at"],
            split=payload["split"],
            policy_ids=list(payload["policy_ids"]),
            review_status=payload["review_status"],
            claim_level=payload["claim_level"],
            source_notice=payload["source_notice"],
            manifest_version=payload["manifest_version"],
            manifest_hashes=dict(payload["manifest_hashes"]),
            metrics=metrics,
            status=payload.get("status", "completed"),
            mode=payload.get("mode", "fixture"),
            attacker=payload.get("attacker", "replay"),
            egress_host=payload.get("egress_host"),
            error=payload.get("error"),
            findings=findings,
            case_results=list(payload.get("case_results", [])),
        )
