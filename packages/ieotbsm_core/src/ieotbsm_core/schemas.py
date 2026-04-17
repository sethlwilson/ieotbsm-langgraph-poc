"""Versioned DTOs for service boundaries (HTTP/MCP). Schema version 1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ieotbsm_core.enums import SensitivityLevel


SCHEMA_VERSION = 1


class PedigreeEntryV1(BaseModel):
    agent_id: str
    org_id: str
    role: str
    action: str
    timestamp: float


class ProvenanceSnapshotV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    query_id: str
    query_text: str = ""
    sensitivity: int
    originating_org: str = ""
    originating_agent: str = ""
    created_at: float = 0.0
    ttl_seconds: float = 300.0
    agent_chain: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_contexts: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: str = ""
    trust_checks: list[dict[str, Any]] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


class RunCreateRequestV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    query_text: str = ""
    requesting_org_id: str
    requesting_agent_id: str = ""
    sensitivity: int = SensitivityLevel.INTERNAL.value


class RunCreateResponseV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    run_id: str
    query_id: str


class GateEvaluateRequestV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    trustor_org_id: str
    trustee_org_id: str
    trustor_agent_id: str | None = None
    trustee_agent_id: str | None = None
    sensitivity: int


class GateDecisionV1(BaseModel):
    decision: Literal["allow", "deny", "human_required"]
    trust_value: float
    threshold: float
    effective_kind: Literal["inter_org_blend", "ledger_only"] = "inter_org_blend"


class GateEvaluateResponseV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    decision: GateDecisionV1
    violation_id: str | None = None


class RunEventAppendRequestV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    event_type: Literal["pedigree_sign", "context", "custom"]
    payload: dict[str, Any] = Field(default_factory=dict)


class ViolationPatchRequestV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    status: Literal["pending", "approved", "denied"]
    reviewer_notes: str = ""


class LedgerMatrixResponseV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    org_ids: list[str]
    labels: list[str]
    matrix: list[list[float]]


class StateResponseV1(BaseModel):
    schema_version: int = SCHEMA_VERSION
    cycle: int = 0
    human_review_queue_size: int = 0
    trust_matrix: dict[str, Any]
    orgs: list[dict[str, str]]
