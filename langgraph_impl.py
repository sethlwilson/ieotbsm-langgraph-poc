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
    ViolationType,
)
from ieotbsm_core.knowledge import ORG_KNOWLEDGE_BASE, retrieve_from_org


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
    org_denials: dict[str, str]        # org_id → reason (trust / review skip)

    # Multi-org sequential fan-out (index into target_org_ids)
    fanout_org_idx: int

    # Human review
    human_review_queue: list[TrustViolation]
    pending_violation: TrustViolation | None

    # Final output
    final_answer: str
    metrics: dict


# Simulated RAG: ORG_KNOWLEDGE_BASE and retrieve_from_org live in ieotbsm_core.knowledge


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
        trust_api_client: Any | None = None,
    ):
        self.network = network
        self._trust_api = trust_api_client
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
        g.add_node("advance_org", self._advance_org_node)
        g.add_node("synthesizer", self._synthesizer_node)

        # Entry
        g.set_entry_point("org_orchestrator")

        # Edges
        g.add_conditional_edges(
            "org_orchestrator",
            self._orchestrator_fanout_router,
            {
                "query_partners": "trust_gate",
                "synthesize": "synthesizer",
            },
        )
        g.add_conditional_edges(
            "trust_gate",
            self._trust_gate_router,
            {
                "approved": "boundary_spanner",
                "human_review": "human_review",
                "denied": "advance_org",
            }
        )
        g.add_edge("boundary_spanner", "internal_agent")
        g.add_edge("internal_agent", "advance_org")
        g.add_conditional_edges(
            "human_review",
            self._human_review_router,
            {
                "approved": "boundary_spanner",
                "denied": "advance_org",
            }
        )
        g.add_conditional_edges(
            "advance_org",
            self._advance_org_router,
            {
                "next_org": "trust_gate",
                "synthesize": "synthesizer",
            },
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

        out = {
            **state,
            "target_org_ids": target_orgs,
            "current_target_org": target_orgs[0] if target_orgs else "",
            "org_answers": {},
            "org_denials": dict(state.get("org_denials", {})),
            "fanout_org_idx": 0,
            "provenance": prov,
        }
        if self._trust_api is not None:
            sens = prov.sensitivity
            s_val = sens.value if isinstance(sens, SensitivityLevel) else int(sens)
            cr = self._trust_api.create_run(
                state["query_text"],
                requesting_org,
                state["requesting_agent_id"],
                s_val,
            )
            out["trust_run_id"] = cr["run_id"]
        return out

    def _orchestrator_fanout_router(self, state: dict) -> str:
        """Skip the per-org loop when there are no partner orgs to query."""
        if not state.get("target_org_ids"):
            return "synthesize"
        return "query_partners"

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
            return {
                **state,
                "trust_passed": False,
                "trust_value": 0.0,
                "pending_violation": None,
                "trust_remote_decision": None,
            }

        req_bs = self.network.get_boundary_spanner(requesting_org)
        tgt_bs = self.network.get_boundary_spanner(target_org)
        remote_decision: str | None = None

        if self._trust_api is not None:
            run_id = state.get("trust_run_id") or ""
            if not run_id:
                raise RuntimeError("trust_run_id missing — orchestrator must create a run")
            sens_val = (
                sensitivity.value
                if isinstance(sensitivity, SensitivityLevel)
                else int(sensitivity)
            )
            resp = self._trust_api.evaluate_gate(
                run_id,
                requesting_org,
                target_org,
                req_bs.agent_id if req_bs else None,
                tgt_bs.agent_id if tgt_bs else None,
                sens_val,
                commit=True,
            )
            dec = resp["decision"]["decision"]
            remote_decision = dec
            passed = dec == "allow"
            effective_trust = float(resp["decision"]["trust_value"])
            threshold = float(resp["decision"]["threshold"])
            self._trust_api.sync_network(self.network)
        elif req_bs and tgt_bs:
            passed, effective_trust = self.network.gate.check_inter_org(
                trustor_agent_id=req_bs.agent_id,
                trustee_agent_id=tgt_bs.agent_id,
                org_id=requesting_org,
                partner_org_id=target_org,
                sensitivity=sensitivity,
                provenance=prov,
            )
            threshold = self.network.ledger.threshold_for(sensitivity)
        else:
            passed, effective_trust, threshold = self.network.ledger.check(
                requesting_org, target_org, sensitivity
            )

        violation = None
        if not passed:
            vid = None
            if self._trust_api is not None:
                vid = resp.get("violation_id")
                if vid:
                    violation = next(
                        (
                            v
                            for v in self.network.human_review_queue
                            if v.violation_id == vid
                        ),
                        None,
                    )
            if violation is None:
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

        org_denials = dict(state.get("org_denials", {}))
        # Record immediate denials only when we will not route to human_review
        if (
            not passed
            and target_org
            and violation is not None
            and remote_decision != "human_required"
            and sensitivity
            not in (SensitivityLevel.CONFIDENTIAL, SensitivityLevel.RESTRICTED)
        ):
            org_denials[target_org] = (
                f"Inter-org trust check failed (effective trust {effective_trust:.2f}, "
                f"required ≥ {threshold:.2f} for {sensitivity.value})."
            )

        return {
            **state,
            "trust_passed": passed,
            "trust_value": effective_trust,
            "pending_violation": violation,
            "org_denials": org_denials,
            "provenance": prov,
            "trust_remote_decision": remote_decision,
        }

    def _trust_gate_router(self, state: dict) -> str:
        """Conditional edge: route based on trust gate result."""
        if state["trust_passed"]:
            return "approved"
        if state.get("trust_remote_decision") == "human_required":
            return "human_review"
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

        if self._trust_api is None:
            self.network.human_review_queue.append(violation)
            self.network.tpm.apply(
                provenance=prov,
                trust_states=self.network.agent_trust,
                ledger=self.network.ledger,
                violation=violation,
                human_queue=self.network.human_review_queue,
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

        org_denials = dict(state.get("org_denials", {}))
        if violation.status == "denied":
            org_denials[violation.target_org] = (
                violation.reviewer_notes or "Human review denied."
            )

        return {
            **state,
            "trust_passed": violation.status == "approved",
            "human_review_queue": self.network.human_review_queue,
            "org_denials": org_denials,
        }

    def _human_review_router(self, state: dict) -> str:
        violation: TrustViolation = state.get("pending_violation")
        if violation and violation.status == "approved":
            return "approved"
        return "denied"

    # ── Node: Advance multi-org fan-out ─────────────────────

    def _advance_org_node(self, state: dict) -> dict:
        """After finishing one partner org, move to the next or end the fan-out."""
        targets: list[str] = list(state.get("target_org_ids", []))
        idx = int(state.get("fanout_org_idx", 0)) + 1
        if idx < len(targets):
            return {
                **state,
                "fanout_org_idx": idx,
                "current_target_org": targets[idx],
                "trust_passed": False,
                "pending_violation": None,
                "trust_remote_decision": None,
            }
        return {**state, "fanout_org_idx": idx, "trust_remote_decision": None}

    def _advance_org_router(self, state: dict) -> str:
        targets: list[str] = list(state.get("target_org_ids", []))
        idx = int(state.get("fanout_org_idx", 0))
        if idx >= len(targets):
            return "synthesize"
        return "next_org"

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
        org_denials = state.get("org_denials") or {}
        query = state["query_text"]

        if not org_answers and not org_denials:
            final = (
                "No cross-organizational data could be retrieved. "
                "Trust thresholds were not met for any target organization."
            )
        elif self._use_llm():
            try:
                parts: list[str] = []
                if org_answers:
                    parts.append(
                        "\n\n".join([
                            f"[{self.network.org_names.get(oid, oid)}]\n{ans}"
                            for oid, ans in org_answers.items()
                        ])
                    )
                if org_denials:
                    deny_lines = "\n".join([
                        f"[{self.network.org_names.get(oid, oid)}] — {reason}"
                        for oid, reason in org_denials.items()
                    ])
                    parts.append(f"Organizations that could not contribute:\n{deny_lines}")
                combined = "\n\n".join(parts)
                resp = self.llm.invoke([
                    SystemMessage(content=(
                        "You are an enterprise intelligence synthesizer. "
                        "Combine insights from multiple organizations into a "
                        "clear, structured answer. Cite which organization "
                        "provided each insight. If some partners could not "
                        "contribute, summarize why briefly without inventing facts."
                    )),
                    HumanMessage(content=f"Query: {query}\n\n{combined}")
                ])
                final = resp.content
            except Exception as e:
                final = f"[Synthesis error: {e}]\n" + "\n".join(org_answers.values())
                if org_denials:
                    final += "\n" + "\n".join(
                        f"{oid}: {r}" for oid, r in org_denials.items()
                    )
        else:
            blocks = [
                f"**{self.network.org_names.get(oid, oid)}**: {ans}"
                for oid, ans in org_answers.items()
            ]
            if org_denials:
                blocks.extend([
                    f"**{self.network.org_names.get(oid, oid)}** (no data): {reason}"
                    for oid, reason in org_denials.items()
                ])
            final = "\n\n".join(blocks)

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
            "  %% IEOTBSM LangGraph — structural view (sequential multi-org)\n"
            "  __start__([START]) --> org_orchestrator[org_orchestrator]\n"
            "  org_orchestrator -->|query_partners| trust_gate[trust_gate]\n"
            "  org_orchestrator -->|synthesize| synthesizer[synthesizer]\n"
            "  trust_gate -->|approved| boundary_spanner[boundary_spanner]\n"
            "  trust_gate -->|human_review| human_review[human_review]\n"
            "  trust_gate -->|denied| advance_org[advance_org]\n"
            "  boundary_spanner --> internal_agent[internal_agent]\n"
            "  internal_agent --> advance_org\n"
            "  human_review -->|approved| boundary_spanner\n"
            "  human_review -->|denied| advance_org\n"
            "  advance_org -->|next_org| trust_gate\n"
            "  advance_org -->|synthesize| synthesizer\n"
            "  synthesizer --> __end__([END])\n"
        )

    def run(
        self,
        state: dict,
        *,
        run_name: str | None = None,
        run_tags: list[str] | None = None,
        run_metadata: dict[str, Any] | None = None,
        stream: bool = False,
        stream_step: Any | None = None,
    ) -> dict:
        """Execute the graph for a given initial state.

        When LangSmith tracing is enabled (LANGSMITH_TRACING + LANGSMITH_API_KEY),
        optional run_name / run_tags / run_metadata appear on the trace for filtering.

        If ``stream`` is True, runs ``graph.stream`` with ``stream_mode="values"`` and
        calls ``stream_step(step_index, snapshot)`` after each superstep; returns the
        last accumulated state.
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
        cfg = config if config else {}
        if stream:
            last: dict[str, Any] = dict(state)
            for i, snapshot in enumerate(
                self.graph.stream(state, config=cfg, stream_mode="values")
            ):
                last = snapshot
                if stream_step is not None:
                    stream_step(i, snapshot)
            return last
        if config:
            return self.graph.invoke(state, config=config)
        return self.graph.invoke(state)
