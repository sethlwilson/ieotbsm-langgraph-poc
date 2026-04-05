"""
LangGraph Graph Definition — IEOTBSM Agentic Extension
=======================================================
Implements the hierarchical agent pattern:
  OrgOrchestrator → BoundarySpannerAgent → InternalAgent(s)

LangGraph nodes map to IEOTBSM entities:
  org_orchestrator_node   → Organization (supervisor)
  boundary_spanner_node   → Boundary Spanner Agent (Definition 5)
  internal_agent_node     → Constituent Agent (Definition 4)
  trust_gate_node         → ISP enforcement (Definition 14)
  human_review_node       → TPM4 (agentic extension)
  synthesizer_node        → Final answer assembly

State flows through a TypedDict that carries:
  - The QueryProvenance (pedigree + retrieved contexts)
  - Current trust gate results
  - Human review queue
  - Accumulated answers from all orgs

Requires: langgraph, langchain-core
LLM (pick one): langchain-anthropic (Claude) and/or langchain-ollama (local Ollama)
Install:  pip install -r requirements.txt

LangSmith (optional): trace runs and inspect the graph execution in the LangSmith UI.
  export LANGSMITH_TRACING=true
  export LANGSMITH_API_KEY=...
  # optional: export LANGSMITH_PROJECT=ieotbsm-poc
Then run the PoC with --langgraph --langsmith (see run_poc.py).
"""

from __future__ import annotations

import os
import json
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    from network import IEOTBSMAgenticNetwork
from dataclasses import dataclass, field

# LangGraph + message types (required for graph mode)
try:
    from langgraph.graph import StateGraph, END
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    HumanMessage = SystemMessage = AIMessage = None  # type: ignore[misc, assignment]
    print("⚠  LangGraph not installed. Run: pip install -r requirements.txt")

try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    ChatAnthropic = None  # type: ignore[misc, assignment]

try:
    from langchain_ollama import ChatOllama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ChatOllama = None  # type: ignore[misc, assignment]

from trust_engine import (
    AgentIdentity, AgentRole, AgentTrustState, QueryProvenance,
    TrustViolation, ViolationType, SensitivityLevel,
    InterOrgTrustLedger, AgenticTPM, TrustGate, TrustMetrics
)


# ─────────────────────────────────────────────────────────────
# LangGraph State
# ─────────────────────────────────────────────────────────────

class GraphState(dict):
    """
    Typed state dict flowing through the LangGraph.
    Carries provenance, trust results, and accumulated answers.
    """
    # Query
    query_id: str
    query_text: str
    sensitivity: SensitivityLevel
    requesting_org_id: str
    requesting_agent_id: str

    # Provenance (Definition 19)
    provenance: QueryProvenance

    # Trust results from gate checks
    trust_passed: bool
    trust_value: float
    target_org_ids: list[str]          # orgs to query
    current_target_org: str

    # Retrieved answers per org
    org_answers: dict[str, str]        # org_id → answer text

    # Human review
    human_review_queue: list[TrustViolation]
    pending_violation: TrustViolation | None

    # Final output
    final_answer: str
    metrics: dict


# ─────────────────────────────────────────────────────────────
# Knowledge base (simulated RAG per org)
# ─────────────────────────────────────────────────────────────

ORG_KNOWLEDGE_BASE: dict[str, list[dict]] = {
    "org_0": [  # Acme Corp — market intelligence
        {"topic": "market", "content": "Q3 semiconductor demand up 18% YoY. DRAM spot prices stabilizing at $3.20/GB. Key driver: AI accelerator procurement by hyperscalers.", "sensitivity": SensitivityLevel.INTERNAL},
        {"topic": "competitor", "content": "Competitor X launching new edge AI chip Q1 next year. Performance claims: 45 TOPS at 8W. Supply chain: TSMC 3nm.", "sensitivity": SensitivityLevel.CONFIDENTIAL},
    ],
    "org_1": [  # Nexus Labs — threat intelligence
        {"topic": "threat", "content": "APT-41 campaign targeting supply chain APIs. IOCs: 203.0.113.42, malware hash a3f2c1d9. Affected sectors: semiconductor, defense.", "sensitivity": SensitivityLevel.RESTRICTED},
        {"topic": "vulnerability", "content": "CVE-2024-38112 actively exploited in enterprise VPN appliances. Patch available. CVSS 9.8. Recommend immediate patching.", "sensitivity": SensitivityLevel.CONFIDENTIAL},
    ],
    "org_2": [  # Sentinel AI — regulatory
        {"topic": "regulatory", "content": "EU AI Act enforcement begins August 2026. High-risk AI systems require conformity assessment. Fines up to 3% global revenue.", "sensitivity": SensitivityLevel.INTERNAL},
        {"topic": "compliance", "content": "SOC 2 Type II audit findings: 2 minor exceptions in access control logging. Remediation deadline: 30 days.", "sensitivity": SensitivityLevel.CONFIDENTIAL},
    ],
    "org_3": [  # Vertex Systems — supply chain
        {"topic": "supply_chain", "content": "TSMC CoWoS packaging capacity constrained through Q2 2026. Lead times extending to 52 weeks for advanced packaging.", "sensitivity": SensitivityLevel.INTERNAL},
        {"topic": "vendor", "content": "Tier-2 supplier risk: 3 vendors flagged for single-source dependency. Recommended: dual-source qualification for capacitors.", "sensitivity": SensitivityLevel.CONFIDENTIAL},
    ],
    "org_4": [  # Orionis Data — pricing/benchmarks
        {"topic": "pricing", "content": "Cloud GPU pricing: H100 $2.80/hr spot, $3.40/hr on-demand. Utilization rates: 94% across top-3 hyperscalers.", "sensitivity": SensitivityLevel.INTERNAL},
        {"topic": "benchmark", "content": "Internal LLM benchmark: Model A scores 87.3 on MMLU, 72.1 on HumanEval. Inference latency: 43ms p50, 210ms p99.", "sensitivity": SensitivityLevel.INTERNAL},
    ],
    "org_5": [  # Caldwell Group — workforce
        {"topic": "workforce", "content": "AI talent attrition rate: 23% annually at director level. Compensation benchmarks: ML Engineer median $195k TC in SF.", "sensitivity": SensitivityLevel.CONFIDENTIAL},
        {"topic": "hiring", "content": "Pipeline analysis: 340 active ML roles across portfolio. Time-to-fill averaging 94 days. Top source: university partnerships.", "sensitivity": SensitivityLevel.INTERNAL},
    ],
}


def retrieve_from_org(org_id: str, query: str,
                      max_sensitivity: SensitivityLevel) -> list[dict]:
    """
    Simulated RAG retrieval from an org's knowledge base.
    Filters results by sensitivity level (trust-gated access).
    In production: replace with vector DB retrieval (FAISS, Chroma, etc.)
    """
    kb = ORG_KNOWLEDGE_BASE.get(org_id, [])
    results = []
    for doc in kb:
        # Only return docs at or below the permitted sensitivity level
        if doc["sensitivity"].value <= max_sensitivity.value:
            # Simple keyword match (replace with embedding similarity in production)
            query_lower = query.lower()
            if any(word in doc["content"].lower()
                   for word in query_lower.split() if len(word) > 3):
                results.append(doc)
    return results


# ─────────────────────────────────────────────────────────────
# IEOTBSM LangGraph — Node implementations
# ─────────────────────────────────────────────────────────────

class IEOTBSMLangGraph:
    """
    LangGraph implementation of the IEOTBSM hierarchical agent architecture.

    Graph structure:
      START
        ↓
      org_orchestrator          (supervisor: validates query, identifies target orgs)
        ↓
      trust_gate                (ISP3/ISP4: inter-org trust check per target org)
        ↓ (pass)              ↓ (fail)
      boundary_spanner    human_review_node
        ↓
      internal_agent            (RAG retrieval within target org)
        ↓
      synthesizer               (aggregate answers, final response)
        ↓
      END
    """

    def __init__(
        self,
        network: IEOTBSMAgenticNetwork,
        llm_backend: str = "claude",
        llm_model: str | None = None,
        ollama_base_url: str | None = None,
    ):
        self.network = network
        self.llm_backend = (llm_backend or "claude").lower().strip()
        self.llm: Any = None
        self.ollama_base_url = (
            ollama_base_url
            or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        )

        if self.llm_backend == "ollama":
            default_model = os.getenv("OLLAMA_MODEL", "llama3.2")
            self.llm_model = llm_model or default_model
            if LANGGRAPH_AVAILABLE and OLLAMA_AVAILABLE and ChatOllama is not None:
                self.llm = ChatOllama(
                    model=self.llm_model,
                    base_url=self.ollama_base_url,
                )
        else:
            self.llm_model = llm_model or "claude-sonnet-4-20250514"
            if LANGGRAPH_AVAILABLE and ANTHROPIC_AVAILABLE and ChatAnthropic is not None:
                self.llm = ChatAnthropic(model=self.llm_model, max_tokens=1024)

        self.graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

    def _use_llm(self) -> bool:
        """True when an LLM client is configured and credentials/server allow use."""
        if not LANGGRAPH_AVAILABLE or self.llm is None:
            return False
        if self.llm_backend == "ollama":
            return OLLAMA_AVAILABLE
        return ANTHROPIC_AVAILABLE and bool(os.getenv("ANTHROPIC_API_KEY"))

    def _build_graph(self):
        """Construct the LangGraph StateGraph."""
        g = StateGraph(dict)

        # Register nodes
        g.add_node("org_orchestrator", self._org_orchestrator_node)
        g.add_node("trust_gate", self._trust_gate_node)
        g.add_node("boundary_spanner", self._boundary_spanner_node)
        g.add_node("internal_agent", self._internal_agent_node)
        g.add_node("human_review", self._human_review_node)
        g.add_node("synthesizer", self._synthesizer_node)

        # Entry
        g.set_entry_point("org_orchestrator")

        # Edges
        g.add_edge("org_orchestrator", "trust_gate")
        g.add_conditional_edges(
            "trust_gate",
            self._trust_gate_router,
            {
                "approved": "boundary_spanner",
                "human_review": "human_review",
                "denied": "synthesizer",
            }
        )
        g.add_edge("boundary_spanner", "internal_agent")
        g.add_edge("internal_agent", "synthesizer")
        g.add_conditional_edges(
            "human_review",
            self._human_review_router,
            {
                "approved": "boundary_spanner",
                "denied": "synthesizer",
            }
        )
        g.add_edge("synthesizer", END)

        return g.compile()

    # ── Node: Org Orchestrator ────────────────────────────────

    def _org_orchestrator_node(self, state: dict) -> dict:
        """
        AgentRole.ORG_ORCHESTRATOR — top-level supervisor.
        Determines which partner orgs to query and signs provenance.
        Maps to: Organization as agent society supervisor (§4.1)
        """
        prov: QueryProvenance = state["provenance"]
        requesting_org = state["requesting_org_id"]
        org = self.network.orgs[requesting_org]

        prov.sign(
            agent_id=f"orchestrator_{requesting_org}",
            org_id=requesting_org,
            role=AgentRole.ORG_ORCHESTRATOR,
            action="query_initiated"
        )

        # Identify target orgs (all partners with any trust established)
        target_orgs = [
            oid for oid in self.network.orgs
            if oid != requesting_org
            and self.network.ledger.get(requesting_org, oid) > 0
        ]

        # Use LLM to classify query and determine sensitivity if not set
        if self._use_llm():
            try:
                resp = self.llm.invoke([
                    SystemMessage(content=(
                        "You are an enterprise AI orchestrator. Classify this query's "
                        "data sensitivity: PUBLIC, INTERNAL, CONFIDENTIAL, or RESTRICTED. "
                        "Reply with just the single word."
                    )),
                    HumanMessage(content=state["query_text"])
                ])
                sensitivity_str = resp.content.strip().upper()
                sensitivity_map = {
                    "PUBLIC": SensitivityLevel.PUBLIC,
                    "INTERNAL": SensitivityLevel.INTERNAL,
                    "CONFIDENTIAL": SensitivityLevel.CONFIDENTIAL,
                    "RESTRICTED": SensitivityLevel.RESTRICTED,
                }
                prov.sensitivity = sensitivity_map.get(
                    sensitivity_str, state["sensitivity"])
            except Exception:
                pass

        return {
            **state,
            "target_org_ids": target_orgs,
            "current_target_org": target_orgs[0] if target_orgs else "",
            "org_answers": {},
            "provenance": prov,
        }

    # ── Node: Trust Gate ─────────────────────────────────────

    def _trust_gate_node(self, state: dict) -> dict:
        """
        TrustGate — ISP3/ISP4 enforcement at inter-org boundary.
        Definition 14: checks trust before any cross-org query proceeds.
        """
        prov: QueryProvenance = state["provenance"]
        requesting_org = state["requesting_org_id"]
        target_org = state["current_target_org"]
        sensitivity = prov.sensitivity

        if not target_org:
            return {**state, "trust_passed": False, "trust_value": 0.0,
                    "pending_violation": None}

        # Get boundary spanner pair
        req_bs = self.network.get_boundary_spanner(requesting_org)
        tgt_bs = self.network.get_boundary_spanner(target_org)

        if req_bs and tgt_bs:
            passed, effective_trust = self.network.gate.check_inter_org(
                trustor_agent_id=req_bs.agent_id,
                trustee_agent_id=tgt_bs.agent_id,
                org_id=requesting_org,
                partner_org_id=target_org,
                sensitivity=sensitivity,
                provenance=prov
            )
        else:
            # Fall back to pure inter-org trust
            passed, effective_trust, threshold = self.network.ledger.check(
                requesting_org, target_org, sensitivity)

        violation = None
        if not passed:
            threshold = self.network.ledger.threshold_for(sensitivity)
            violation = TrustViolation(
                query_id=prov.query_id,
                violation_type=ViolationType.INSUFFICIENT_INTER_ORG_TRUST,
                requesting_org=requesting_org,
                target_org=target_org,
                requesting_agent=state["requesting_agent_id"],
                trust_value=effective_trust,
                required_threshold=threshold,
                sensitivity=sensitivity,
                query_text=state["query_text"],
                agent_chain_at_violation=list(prov.agent_chain),
            )
            prov.violations.append(violation.violation_id)

        return {
            **state,
            "trust_passed": passed,
            "trust_value": effective_trust,
            "pending_violation": violation,
            "provenance": prov,
        }

    def _trust_gate_router(self, state: dict) -> str:
        """Conditional edge: route based on trust gate result."""
        if state["trust_passed"]:
            return "approved"
        violation = state.get("pending_violation")
        if violation and violation.sensitivity in (
                SensitivityLevel.CONFIDENTIAL, SensitivityLevel.RESTRICTED):
            return "human_review"
        return "denied"

    # ── Node: Human Review ───────────────────────────────────

    def _human_review_node(self, state: dict) -> dict:
        """
        TPM4: Routes trust violation to human review queue.
        Agentic extension of IEOTBSM — violation is not silently dropped
        but queued for human adjudication with full provenance context.
        In production: integrates with ticketing system (Jira, ServiceNow).
        """
        violation: TrustViolation = state["pending_violation"]
        prov: QueryProvenance = state["provenance"]

        # Add to network-level human review queue
        self.network.human_review_queue.append(violation)
        self.network.tpm.apply(
            provenance=prov,
            trust_states=self.network.agent_trust,
            ledger=self.network.ledger,
            violation=violation,
            human_queue=self.network.human_review_queue
        )

        # Simulate human review decision (in production: async wait)
        # Auto-approve INTERNAL sensitivity violations for PoC demonstration
        if violation.sensitivity == SensitivityLevel.INTERNAL:
            violation.status = "approved"
            violation.reviewer_notes = (
                f"Auto-approved: trust {violation.trust_value:.2f} near threshold "
                f"{violation.required_threshold:.2f}. Monitor for recurrence."
            )
        else:
            violation.status = "denied"
            violation.reviewer_notes = (
                f"Denied: {violation.sensitivity.value} data requires trust ≥ "
                f"{violation.required_threshold:.2f}. Current: {violation.trust_value:.2f}."
            )

        return {
            **state,
            "trust_passed": violation.status == "approved",
            "human_review_queue": self.network.human_review_queue,
        }

    def _human_review_router(self, state: dict) -> str:
        violation: TrustViolation = state.get("pending_violation")
        if violation and violation.status == "approved":
            return "approved"
        return "denied"

    # ── Node: Boundary Spanner ───────────────────────────────

    def _boundary_spanner_node(self, state: dict) -> dict:
        """
        BoundarySpannerAgent — inter-org representative (Definition 5).
        Signs the pedigree, determines what sensitivity level to expose,
        and passes the query to the target org's internal agents.
        """
        prov: QueryProvenance = state["provenance"]
        target_org = state["current_target_org"]

        bs = self.network.get_boundary_spanner(target_org)
        if bs:
            prov.sign(
                agent_id=bs.agent_id,
                org_id=target_org,
                role=AgentRole.BOUNDARY_SPANNER,
                action="query_received_cross_org"
            )

        # Update inter-org interaction count for trust calculus
        requesting_org = state["requesting_org_id"]
        req_bs = self.network.get_boundary_spanner(requesting_org)
        tgt_bs = bs
        bs_trust_vals = []
        if req_bs and tgt_bs:
            key = (req_bs.agent_id, tgt_bs.agent_id)
            if key in self.network.agent_trust:
                bs_trust_vals = [self.network.agent_trust[key].effective_trust]

        self.network.ledger.update(
            requesting_org, target_org,
            bs_trust_vals,
            len(self.network.boundary_spanners.get(requesting_org, []))
        )

        return {**state, "provenance": prov}

    # ── Node: Internal Agent ─────────────────────────────────

    def _internal_agent_node(self, state: dict) -> dict:
        """
        InternalAgent — constituent agent performing RAG retrieval (Definition 4).
        Retrieves relevant documents from the org's knowledge base,
        filtered by the trust-approved sensitivity level.
        """
        prov: QueryProvenance = state["provenance"]
        target_org = state["current_target_org"]
        query = state["query_text"]
        org_answers = dict(state.get("org_answers", {}))

        # Find an internal agent for this org
        internal_agents = self.network.internal_agents.get(target_org, [])
        if internal_agents:
            agent = internal_agents[0]
            prov.sign(
                agent_id=agent.agent_id,
                org_id=target_org,
                role=AgentRole.INTERNAL,
                action="rag_retrieval"
            )

        # Retrieve documents (trust-gated by sensitivity)
        docs = retrieve_from_org(target_org, query, prov.sensitivity)

        answer = ""
        if docs:
            context = "\n".join([d["content"] for d in docs])
            prov.add_context(
                org_id=target_org,
                agent_id=internal_agents[0].agent_id if internal_agents else "unknown",
                content=context,
                sensitivity=prov.sensitivity
            )

            if self._use_llm():
                try:
                    org_name = self.network.org_names.get(target_org, target_org)
                    resp = self.llm.invoke([
                        SystemMessage(content=(
                            f"You are an internal AI agent for {org_name}. "
                            "Answer the query using only the provided context. "
                            "Be concise and factual. If context is insufficient, say so."
                        )),
                        HumanMessage(content=(
                            f"Query: {query}\n\nContext:\n{context}"
                        ))
                    ])
                    answer = resp.content
                except Exception as e:
                    answer = f"[LLM error: {e}] Context: {context[:200]}"
            else:
                # Fallback: return context directly (no LLM)
                answer = f"Retrieved from {target_org}: {context[:300]}"
        else:
            answer = f"No relevant documents found in {target_org} for this query at sensitivity level {prov.sensitivity.value}."

        org_answers[target_org] = answer

        # Record successful interaction in trust state
        req_bs = self.network.get_boundary_spanner(state["requesting_org_id"])
        tgt_bs = self.network.get_boundary_spanner(target_org)
        if req_bs and tgt_bs:
            self.network.gate.record_outcome(req_bs.agent_id, tgt_bs.agent_id, True)

        return {**state, "org_answers": org_answers, "provenance": prov}

    # ── Node: Synthesizer ────────────────────────────────────

    def _synthesizer_node(self, state: dict) -> dict:
        """
        Final synthesis: aggregates answers from all queried orgs
        into a coherent cross-org response with provenance summary.
        """
        prov: QueryProvenance = state["provenance"]
        org_answers = state.get("org_answers", {})
        query = state["query_text"]

        if not org_answers:
            final = (
                "No cross-organizational data could be retrieved. "
                "Trust thresholds were not met for any target organization."
            )
        elif self._use_llm():
            try:
                combined = "\n\n".join([
                    f"[{self.network.org_names.get(oid, oid)}]\n{ans}"
                    for oid, ans in org_answers.items()
                ])
                resp = self.llm.invoke([
                    SystemMessage(content=(
                        "You are an enterprise intelligence synthesizer. "
                        "Combine insights from multiple organizations into a "
                        "clear, structured answer. Cite which organization "
                        "provided each insight."
                    )),
                    HumanMessage(content=f"Query: {query}\n\nOrg answers:\n{combined}")
                ])
                final = resp.content
            except Exception as e:
                final = f"[Synthesis error: {e}]\n" + "\n".join(org_answers.values())
        else:
            final = "\n\n".join([
                f"**{self.network.org_names.get(oid, oid)}**: {ans}"
                for oid, ans in org_answers.items()
            ])

        prov.final_answer = final
        prov.sign(
            agent_id=f"synthesizer_{state['requesting_org_id']}",
            org_id=state["requesting_org_id"],
            role=AgentRole.ORG_ORCHESTRATOR,
            action="synthesis_complete"
        )

        # Update metrics
        metrics = state.get("metrics", {})
        metrics["orgs_answered"] = len(org_answers)
        metrics["trust_checks"] = len(prov.trust_checks)
        metrics["pedigree_length"] = len(prov.agent_chain)
        metrics["violations"] = len(prov.violations)
        metrics["human_reviews"] = len(self.network.human_review_queue)

        return {
            **state,
            "final_answer": final,
            "provenance": prov,
            "metrics": metrics,
        }

    def graph_mermaid(self) -> str:
        """Mermaid diagram of the workflow (matches _build_graph).

        LangGraph's ``get_graph().draw_mermaid()`` is unreliable with plain ``dict``
        state in some versions; this static diagram matches our nodes and edges.
        LangSmith traces still show the executed path per run.
        """
        if not LANGGRAPH_AVAILABLE or self.graph is None:
            raise RuntimeError("LangGraph not installed.")
        return (
            "graph TD\n"
            "  %% IEOTBSM LangGraph — structural view\n"
            "  __start__([START]) --> org_orchestrator[org_orchestrator]\n"
            "  org_orchestrator --> trust_gate[trust_gate]\n"
            "  trust_gate -->|approved| boundary_spanner[boundary_spanner]\n"
            "  trust_gate -->|human_review| human_review[human_review]\n"
            "  trust_gate -->|denied| synthesizer[synthesizer]\n"
            "  boundary_spanner --> internal_agent[internal_agent]\n"
            "  internal_agent --> synthesizer\n"
            "  human_review -->|approved| boundary_spanner\n"
            "  human_review -->|denied| synthesizer\n"
            "  synthesizer --> __end__([END])\n"
        )

    def run(
        self,
        state: dict,
        *,
        run_name: str | None = None,
        run_tags: list[str] | None = None,
        run_metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Execute the graph for a given initial state.

        When LangSmith tracing is enabled (LANGSMITH_TRACING + LANGSMITH_API_KEY),
        optional run_name / run_tags / run_metadata appear on the trace for filtering.
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph not installed.")
        config: dict[str, Any] = {}
        if run_name:
            config["run_name"] = run_name
        if run_tags:
            config["tags"] = run_tags
        if run_metadata:
            config["metadata"] = run_metadata
        if config:
            return self.graph.invoke(state, config=config)
        return self.graph.invoke(state)
