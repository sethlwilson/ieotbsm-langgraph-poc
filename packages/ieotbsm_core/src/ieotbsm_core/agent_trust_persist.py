"""Serialize / deserialize agent-level trust state maps."""

from __future__ import annotations

from typing import Any

from ieotbsm_core.models import AgentTrustState


def agent_trust_to_list(
    agent_trust: dict[tuple[str, str], AgentTrustState],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for (a, b), st in agent_trust.items():
        out.append(
            {
                "trustor_id": a,
                "trustee_id": b,
                "base_trust": st.base_trust,
                "interaction_count": st.interaction_count,
                "last_interaction": st.last_interaction,
                "good_interactions": st.good_interactions,
                "bad_interactions": st.bad_interactions,
                "recency_decay": st.recency_decay,
            }
        )
    return out


def agent_trust_from_list(rows: list[dict[str, Any]]) -> dict[tuple[str, str], AgentTrustState]:
    out: dict[tuple[str, str], AgentTrustState] = {}
    for r in rows or []:
        a, b = r["trustor_id"], r["trustee_id"]
        out[(a, b)] = AgentTrustState(
            trustor_id=a,
            trustee_id=b,
            base_trust=float(r.get("base_trust", 0.5)),
            interaction_count=int(r.get("interaction_count", 0)),
            last_interaction=float(r.get("last_interaction", 0.0)),
            good_interactions=int(r.get("good_interactions", 0)),
            bad_interactions=int(r.get("bad_interactions", 0)),
            recency_decay=float(r.get("recency_decay", 0.995)),
        )
    return out
