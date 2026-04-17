"""Serialize QueryProvenance for JSON storage."""

from __future__ import annotations

from typing import Any

from ieotbsm_core.enums import SensitivityLevel
from ieotbsm_core.models import QueryProvenance


def provenance_to_dict(p: QueryProvenance) -> dict[str, Any]:
    return {
        "query_id": p.query_id,
        "query_text": p.query_text,
        "sensitivity": p.sensitivity.value,
        "originating_org": p.originating_org,
        "originating_agent": p.originating_agent,
        "created_at": p.created_at,
        "ttl_seconds": p.ttl_seconds,
        "agent_chain": list(p.agent_chain),
        "retrieved_contexts": list(p.retrieved_contexts),
        "final_answer": p.final_answer,
        "trust_checks": list(p.trust_checks),
        "violations": list(p.violations),
    }


def provenance_from_dict(d: dict[str, Any]) -> QueryProvenance:
    p = QueryProvenance(
        query_id=str(d.get("query_id", "")),
        query_text=str(d.get("query_text", "")),
        sensitivity=SensitivityLevel(int(d.get("sensitivity", 1))),
        originating_org=str(d.get("originating_org", "")),
        originating_agent=str(d.get("originating_agent", "")),
        created_at=float(d.get("created_at", 0.0)),
        ttl_seconds=float(d.get("ttl_seconds", 300.0)),
    )
    p.agent_chain = list(d.get("agent_chain") or [])
    p.retrieved_contexts = list(d.get("retrieved_contexts") or [])
    p.final_answer = str(d.get("final_answer", ""))
    p.trust_checks = list(d.get("trust_checks") or [])
    p.violations = list(d.get("violations") or [])
    return p
