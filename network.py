"""
IEOTBSMAgenticNetwork
=====================
Top-level class that assembles the full agentic network:
  - Organizations with internal agents and boundary spanners
  - Inter-org trust ledger (Equations 5, 6, 7)
  - Agent-level trust states (Definition 10)
  - Trust gate (Definition 14)
  - TPM handler (Definition 24 + TPM4 extension)
  - Human review queue
  - LangGraph execution engine
"""

from __future__ import annotations

import random
import math
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field

from ieotbsm_core import (
    AgentIdentity,
    AgentRole,
    AgentTrustState,
    AgenticTPM,
    InterOrgTrustLedger,
    QueryProvenance,
    SensitivityLevel,
    TrustGate,
    TrustMetrics,
    TrustViolation,
)


# ─────────────────────────────────────────────────────────────
# Network configuration
# ─────────────────────────────────────────────────────────────

ORG_CONFIGS = [
    {"id": "org_0", "name": "Acme Corp",          "domain": "market_intelligence"},
    {"id": "org_1", "name": "Nexus Labs",         "domain": "threat_intelligence"},
    {"id": "org_2", "name": "Sentinel AI",        "domain": "regulatory_compliance"},
    {"id": "org_3", "name": "Vertex Systems",     "domain": "supply_chain"},
    {"id": "org_4", "name": "Orionis Data",       "domain": "benchmarks_pricing"},
    {"id": "org_5", "name": "Caldwell Group",     "domain": "workforce_analytics"},
]

CAPABILITIES_BY_DOMAIN = {
    "market_intelligence":   ["market_analysis", "competitor_intel", "trend_forecasting"],
    "threat_intelligence":   ["threat_hunting", "ioc_analysis", "vulnerability_mgmt"],
    "regulatory_compliance": ["policy_analysis", "audit_support", "risk_assessment"],
    "supply_chain":          ["vendor_analysis", "risk_mapping", "procurement"],
    "benchmarks_pricing":    ["benchmark_eval", "cost_modeling", "capacity_planning"],
    "workforce_analytics":   ["talent_analysis", "compensation_bench", "org_design"],
}


class IEOTBSMAgenticNetwork:
    """
    Full IEOTBSM agentic network.
    Manages the multi-org agent hierarchy, trust ledger, and LangGraph engine.
    """

    def __init__(self,
                 org_configs: list[dict] = None,
                 alpha: float = 0.65,
                 tpm_mode: int = 4,
                 decrement: float = 0.06,
                 seed: int = 42):

        random.seed(seed)
        self.org_configs = org_configs or ORG_CONFIGS
        self.alpha = alpha
        self.tpm_mode = tpm_mode

        # Core registries
        self.orgs: dict[str, dict] = {}               # org_id → config
        self.org_names: dict[str, str] = {}           # org_id → name
        self.internal_agents: dict[str, list[AgentIdentity]] = defaultdict(list)
        self.boundary_spanners: dict[str, list[AgentIdentity]] = defaultdict(list)

        # Trust infrastructure
        self.ledger = InterOrgTrustLedger(alpha=alpha)
        self.agent_trust: dict[tuple, AgentTrustState] = {}
        self.tpm = AgenticTPM(mode=tpm_mode, decrement=decrement)
        self.human_review_queue: list[TrustViolation] = []

        # Metrics
        self.metrics_history: list[TrustMetrics] = []
        self.cycle = 0

        self._rng_seed = seed
        self._build_network()
        self.gate = TrustGate(self.ledger, self.agent_trust)

    def export_trust_snapshot(self) -> dict:
        """Serializable trust state for persistence (API / DB)."""
        from ieotbsm_core.agent_trust_persist import agent_trust_to_list
        from ieotbsm_core.violation_persist import violation_to_dict

        return {
            "rng_seed": self._rng_seed,
            "org_configs": self.org_configs,
            "alpha": self.alpha,
            "tpm_mode": self.tpm_mode,
            "decrement": self.tpm.decrement,
            "cycle": self.cycle,
            "ledger": self.ledger.to_persistence(),
            "agent_trust": agent_trust_to_list(self.agent_trust),
            "tpm": self.tpm.to_persistence(),
            "human_queue": [violation_to_dict(v) for v in self.human_review_queue],
        }

    def import_trust_snapshot(self, snap: dict) -> None:
        """Restore trust state from :meth:`export_trust_snapshot`."""
        from ieotbsm_core.agent_trust_persist import agent_trust_from_list
        from ieotbsm_core.violation_persist import violation_from_dict

        self.org_configs = snap.get("org_configs", self.org_configs)
        self.alpha = float(snap.get("alpha", self.alpha))
        self.tpm_mode = int(snap.get("tpm_mode", self.tpm_mode))
        self.cycle = int(snap.get("cycle", 0))
        self.ledger = InterOrgTrustLedger.from_persistence(snap["ledger"])
        self.agent_trust = agent_trust_from_list(snap.get("agent_trust", []))
        self.tpm = AgenticTPM.from_persistence(snap.get("tpm", {}))
        self.tpm.decrement = float(snap.get("decrement", self.tpm.decrement))
        self.tpm.mode = self.tpm_mode
        self.human_review_queue = [
            violation_from_dict(v) for v in snap.get("human_queue", [])
        ]
        self.gate = TrustGate(self.ledger, self.agent_trust)

    # ─────────────────────────────────────────────────────────
    # Network construction
    # ─────────────────────────────────────────────────────────

    def _build_network(self):
        """Construct the full inter-organizational agent network."""
        for cfg in self.org_configs:
            oid = cfg["id"]
            self.orgs[oid] = cfg
            self.org_names[oid] = cfg["name"]
            domain = cfg["domain"]
            caps = CAPABILITIES_BY_DOMAIN.get(domain, ["general"])

            # Create 3 internal agents per org
            for i in range(3):
                agent = AgentIdentity(
                    agent_id=f"{oid}_agent_{i}",
                    org_id=oid,
                    role=AgentRole.INTERNAL,
                    name=f"{cfg['name']} Agent {i}",
                    capabilities=caps,
                    reliability_score=random.uniform(0.4, 0.9),
                )
                self.internal_agents[oid].append(agent)

            # Create 1 boundary spanner per org (highest reliability)
            bs = AgentIdentity(
                agent_id=f"{oid}_bs",
                org_id=oid,
                role=AgentRole.BOUNDARY_SPANNER,
                name=f"{cfg['name']} BS",
                capabilities=caps + ["inter_org_negotiation"],
                reliability_score=random.uniform(0.65, 0.95),
            )
            self.boundary_spanners[oid].append(bs)

        # Initialize inter-org trust (τ_0) — Definition 10 / Equation 5
        org_ids = list(self.orgs.keys())
        for om_id in org_ids:
            for on_id in org_ids:
                if om_id != on_id:
                    # Initial trust varies: some orgs have pre-existing relationships
                    tau_0 = random.uniform(0.15, 0.55)
                    self.ledger.initialize(om_id, on_id, tau_0)

        # Initialize inter-agent trust states
        self._init_agent_trust()

    def _init_agent_trust(self):
        """
        Initialize ITR (Definition 10) for all agent pairs:
          - Intra-org: agent ↔ agent, agent ↔ BS
          - Inter-org: BS ↔ BS across organizations
        """
        org_ids = list(self.orgs.keys())

        for oid in org_ids:
            all_local = (self.internal_agents[oid] +
                         self.boundary_spanners[oid])

            # Intra-org trust (ITR1, ITR2, ITR3)
            for a in all_local:
                for b in all_local:
                    if a.agent_id != b.agent_id:
                        key = (a.agent_id, b.agent_id)
                        self.agent_trust[key] = AgentTrustState(
                            trustor_id=a.agent_id,
                            trustee_id=b.agent_id,
                            base_trust=random.uniform(0.4, 0.9),
                        )

        # Inter-org BS trust (ITR4) — fully connected BS mesh
        for om_id in org_ids:
            for on_id in org_ids:
                if om_id == on_id:
                    continue
                bs_m_list = self.boundary_spanners[om_id]
                bs_n_list = self.boundary_spanners[on_id]
                for bs_m in bs_m_list:
                    for bs_n in bs_n_list:
                        key = (bs_m.agent_id, bs_n.agent_id)
                        # Inter-org BS trust starts lower (strangers)
                        self.agent_trust[key] = AgentTrustState(
                            trustor_id=bs_m.agent_id,
                            trustee_id=bs_n.agent_id,
                            base_trust=random.uniform(0.2, 0.6),
                        )

    # ─────────────────────────────────────────────────────────
    # Accessors
    # ─────────────────────────────────────────────────────────

    def get_boundary_spanner(self, org_id: str) -> AgentIdentity | None:
        bss = self.boundary_spanners.get(org_id, [])
        return bss[0] if bss else None

    def get_trust_matrix(self) -> dict:
        org_ids = list(self.orgs.keys())
        labels = [self.org_names[oid] for oid in org_ids]
        matrix = self.ledger.matrix(org_ids)
        return {"labels": labels, "org_ids": org_ids, "matrix": matrix}

    def get_agent_trust_summary(self, org_id: str) -> list[dict]:
        """Return BS-level trust summary for an org."""
        bs = self.get_boundary_spanner(org_id)
        if not bs:
            return []
        results = []
        for (tid, eid), state in self.agent_trust.items():
            if tid == bs.agent_id and eid.endswith("_bs"):
                target_org = eid.replace("_bs", "")
                results.append({
                    "target_org": self.org_names.get(target_org, target_org),
                    "bs_trust": round(state.effective_trust, 3),
                    "io_trust": round(self.ledger.get(org_id, target_org), 3),
                    "interactions": state.interaction_count,
                })
        return results

    # ─────────────────────────────────────────────────────────
    # Query execution (without LangGraph — simulation mode)
    # ─────────────────────────────────────────────────────────

    def iter_query_simulation_events(
        self,
        query_text: str,
        requesting_org_id: str,
        sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL,
        *,
        throttle_ms: int = 0,
        description: str | None = None,
    ) -> Iterator[dict]:
        """
        Run the same logic as execute_query_simulation but yield JSON-serializable
        event dicts for live dashboards (SSE). Ends with type ``query_complete``.
        """
        from ieotbsm_core.knowledge import retrieve_from_org

        def _throttle() -> None:
            if throttle_ms > 0:
                time.sleep(throttle_ms / 1000.0)

        self.cycle += 1
        prov = QueryProvenance(
            query_text=query_text,
            sensitivity=sensitivity,
            originating_org=requesting_org_id,
            originating_agent=f"orchestrator_{requesting_org_id}",
        )

        yield {
            "type": "query_started",
            "description": description,
            "query_id": prov.query_id,
            "query_text": query_text,
            "requesting_org_id": requesting_org_id,
            "requesting_org": self.org_names[requesting_org_id],
            "sensitivity": sensitivity.name,
            "sensitivity_value": sensitivity.value,
            "cycle": self.cycle,
        }
        _throttle()

        prov.sign(
            agent_id=f"orchestrator_{requesting_org_id}",
            org_id=requesting_org_id,
            role=AgentRole.ORG_ORCHESTRATOR,
            action="query_initiated",
        )
        yield {
            "type": "orchestrator",
            "action": "query_initiated",
            "agent_id": f"orchestrator_{requesting_org_id}",
        }
        _throttle()

        results: dict = {
            "query_id": prov.query_id,
            "query_text": query_text,
            "requesting_org": self.org_names[requesting_org_id],
            "sensitivity": sensitivity.value,
            "org_results": [],
            "trust_checks": [],
            "violations": [],
            "human_reviews": [],
            "final_answer": "",
            "pedigree": [],
        }

        metrics = TrustMetrics(cycle=self.cycle)
        collected_answers: dict[str, str] = {}

        for target_org_id in self.orgs:
            if target_org_id == requesting_org_id:
                continue

            req_bs = self.get_boundary_spanner(requesting_org_id)
            tgt_bs = self.get_boundary_spanner(target_org_id)

            if req_bs and tgt_bs:
                passed, effective_trust = self.gate.check_inter_org(
                    trustor_agent_id=req_bs.agent_id,
                    trustee_agent_id=tgt_bs.agent_id,
                    org_id=requesting_org_id,
                    partner_org_id=target_org_id,
                    sensitivity=sensitivity,
                    provenance=prov,
                )
            else:
                passed, effective_trust, _ = self.ledger.check(
                    requesting_org_id, target_org_id, sensitivity
                )

            threshold = self.ledger.threshold_for(sensitivity)
            check_rec = {
                "target_org": self.org_names[target_org_id],
                "target_org_id": target_org_id,
                "trust": round(effective_trust, 3),
                "threshold": threshold,
                "passed": passed,
            }
            results["trust_checks"].append(
                {k: v for k, v in check_rec.items() if k != "target_org_id"}
            )
            yield {"type": "trust_check", **check_rec}
            _throttle()

            if passed:
                if tgt_bs:
                    prov.sign(
                        tgt_bs.agent_id,
                        target_org_id,
                        AgentRole.BOUNDARY_SPANNER,
                        "cross_org_relay",
                    )
                    self.ledger.update(
                        requesting_org_id,
                        target_org_id,
                        [effective_trust],
                        len(self.boundary_spanners[requesting_org_id]),
                    )
                yield {
                    "type": "boundary_spanner",
                    "target_org": self.org_names[target_org_id],
                    "target_org_id": target_org_id,
                    "action": "cross_org_relay",
                }
                _throttle()

                agents = self.internal_agents.get(target_org_id, [])
                if agents:
                    prov.sign(
                        agents[0].agent_id,
                        target_org_id,
                        AgentRole.INTERNAL,
                        "rag_retrieval",
                    )

                docs = retrieve_from_org(target_org_id, query_text, sensitivity)
                if docs:
                    context = " | ".join([d["content"][:120] for d in docs])
                    prov.add_context(
                        target_org_id,
                        agents[0].agent_id if agents else "unknown",
                        context,
                        sensitivity,
                    )
                    collected_answers[target_org_id] = context
                    org_res = {
                        "org": self.org_names[target_org_id],
                        "status": "retrieved",
                        "doc_count": len(docs),
                        "preview": context[:200],
                    }
                    results["org_results"].append(org_res)
                    yield {
                        "type": "retrieval",
                        **org_res,
                        "target_org_id": target_org_id,
                    }
                else:
                    org_res = {
                        "org": self.org_names[target_org_id],
                        "status": "no_match",
                        "doc_count": 0,
                        "preview": "",
                    }
                    results["org_results"].append(org_res)
                    yield {
                        "type": "retrieval",
                        **org_res,
                        "target_org_id": target_org_id,
                    }
                _throttle()

                self.gate.record_outcome(
                    req_bs.agent_id if req_bs else "",
                    tgt_bs.agent_id if tgt_bs else "",
                    True,
                )
                metrics.intended_queries += 1

            else:
                violation = TrustViolation(
                    query_id=prov.query_id,
                    requesting_org=requesting_org_id,
                    target_org=target_org_id,
                    requesting_agent=req_bs.agent_id if req_bs else "",
                    trust_value=effective_trust,
                    required_threshold=threshold,
                    sensitivity=sensitivity,
                    query_text=query_text,
                    agent_chain_at_violation=list(prov.agent_chain),
                )

                self.tpm.apply(
                    prov,
                    self.agent_trust,
                    self.ledger,
                    violation,
                    self.human_review_queue,
                )

                yield {
                    "type": "violation",
                    "violation_id": violation.violation_id,
                    "target_org": self.org_names[target_org_id],
                    "target_org_id": target_org_id,
                    "trust": round(effective_trust, 3),
                    "threshold": threshold,
                }
                _throttle()

                if sensitivity in (SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL):
                    violation.status = "approved"
                    violation.reviewer_notes = (
                        f"Approved by human reviewer: trust {effective_trust:.2f} "
                        f"acceptable for {sensitivity.value} data. Monitor."
                    )
                    hr = {
                        "violation_id": violation.violation_id,
                        "target_org": self.org_names[target_org_id],
                        "decision": "approved",
                        "notes": violation.reviewer_notes,
                    }
                    results["human_reviews"].append(hr)
                    metrics.approved_by_human += 1
                else:
                    violation.status = "denied"
                    violation.reviewer_notes = (
                        f"Denied: insufficient trust for {sensitivity.value} data."
                    )
                    hr = {
                        "violation_id": violation.violation_id,
                        "target_org": self.org_names[target_org_id],
                        "decision": "denied",
                        "notes": violation.reviewer_notes,
                    }
                    results["human_reviews"].append(hr)
                    metrics.denied_by_human += 1

                yield {"type": "human_review", **hr}
                _throttle()

                prov.violations.append(violation.violation_id)
                metrics.unintended_queries += 1
                metrics.human_review_count += 1

            yield {
                "type": "matrix_updated",
                "trust_matrix": self.get_trust_matrix(),
            }
            _throttle()

        metrics.total_queries = metrics.intended_queries + metrics.unintended_queries
        self.metrics_history.append(metrics)

        if collected_answers:
            parts = [
                f"[{self.org_names[oid]}]: {ans[:250]}"
                for oid, ans in collected_answers.items()
            ]
            prov.final_answer = "\n\n".join(parts)
        else:
            prov.final_answer = (
                "No data retrieved — all cross-org queries blocked by trust gates."
            )

        results["final_answer"] = prov.final_answer
        results["pedigree"] = list(prov.agent_chain)
        results["ia_pct"] = metrics.ia_pct
        results["sm_pct"] = metrics.sm_pct
        results["human_review_count"] = metrics.human_review_count

        yield {
            "type": "synthesize",
            "preview": prov.final_answer[:400],
            "answer_length": len(prov.final_answer),
        }
        _throttle()

        yield {"type": "query_complete", "results": results}

    def execute_query_simulation(
        self,
        query_text: str,
        requesting_org_id: str,
        sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL,
    ) -> dict:
        """
        Execute a cross-org RAG query using the IEOTBSM trust engine,
        without requiring LangGraph installation.
        Simulates the full graph flow: orchestrator → gate → BS → agent → synthesizer.
        """
        final: dict | None = None
        for event in self.iter_query_simulation_events(
            query_text, requesting_org_id, sensitivity
        ):
            if event["type"] == "query_complete":
                final = event["results"]
        if final is None:
            raise RuntimeError("simulation produced no result")
        return final
