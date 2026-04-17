"""Serialize TrustViolation for JSON storage."""

from __future__ import annotations

from typing import Any

from ieotbsm_core.enums import SensitivityLevel, ViolationType
from ieotbsm_core.models import TrustViolation


def violation_to_dict(v: TrustViolation) -> dict[str, Any]:
    return {
        "violation_id": v.violation_id,
        "violation_type": v.violation_type.name,
        "query_id": v.query_id,
        "requesting_org": v.requesting_org,
        "target_org": v.target_org,
        "requesting_agent": v.requesting_agent,
        "trust_value": v.trust_value,
        "required_threshold": v.required_threshold,
        "sensitivity": v.sensitivity.value,
        "query_text": v.query_text,
        "agent_chain_at_violation": list(v.agent_chain_at_violation),
        "timestamp": v.timestamp,
        "status": v.status,
        "reviewer_notes": v.reviewer_notes,
    }


def violation_from_dict(d: dict[str, Any]) -> TrustViolation:
    return TrustViolation(
        violation_id=str(d.get("violation_id", "")),
        violation_type=ViolationType[d.get("violation_type", "INSUFFICIENT_INTER_ORG_TRUST")],
        query_id=str(d.get("query_id", "")),
        requesting_org=str(d.get("requesting_org", "")),
        target_org=str(d.get("target_org", "")),
        requesting_agent=str(d.get("requesting_agent", "")),
        trust_value=float(d.get("trust_value", 0.0)),
        required_threshold=float(d.get("required_threshold", 0.0)),
        sensitivity=SensitivityLevel(int(d.get("sensitivity", 1))),
        query_text=str(d.get("query_text", "")),
        agent_chain_at_violation=list(d.get("agent_chain_at_violation") or []),
        timestamp=float(d.get("timestamp", 0.0)),
        status=str(d.get("status", "pending")),
        reviewer_notes=str(d.get("reviewer_notes", "")),
    )
