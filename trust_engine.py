"""
IEOTBSM Trust Engine — Extended for Agentic AI
================================================
Extension of: Hexmoor, Wilson & Bhattaram (2006)
"A Theoretical Inter-organizational Trust-based Security Model"
The Knowledge Engineering Review, 21(2), 127–161.

New concepts introduced for agentic AI context:
  - QueryProvenance   : extends Fact/FactPedigree to LLM query/response chains
  - AgentTrustState   : extends ITR to include agent capability + recency dimensions
  - TrustViolation    : structured breach record routed to human review queue
  - TrustGate         : callable that enforces ISP1-ISP4 at LangGraph edge boundaries
  - AgenticTPM        : extends TPM1/2/3 with human-review routing (new TPM4)

Mapping to original IEOTBSM formal definitions:
  Agent            → InternalAgent      (Definition 4)
  Boundary Spanner → BoundarySpannerAgent (Definition 5)
  Organization     → EnterpriseOrg      (Definition 3)
  Fact             → QueryProvenance    (Definition 6 + 19)
  ITR              → AgentTrustState    (Definition 10)
  ISP              → TrustGate          (Definition 14)
  TPM              → AgenticTPM         (Definition 24)
  IA / SM          → TrustMetrics       (Definitions 27–30)
"""

import math
import uuid
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from collections import defaultdict


# ─────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────

class AgentRole(Enum):
    """Roles within the IEOTBSM agentic hierarchy."""
    INTERNAL = "internal"            # Definition 4: constituent agent
    BOUNDARY_SPANNER = "boundary_spanner"  # Definition 5: inter-org representative
    ORG_ORCHESTRATOR = "org_orchestrator"  # Extension: org-level LangGraph supervisor


class SensitivityLevel(Enum):
    """
    Extension: Data sensitivity tiers that modulate trust thresholds.
    Higher sensitivity → higher trust threshold required (NIST SP 800-150 alignment).
    """
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


class ViolationType(Enum):
    """Types of trust violation triggering human review (new in agentic extension)."""
    INSUFFICIENT_INTER_ORG_TRUST = "insufficient_inter_org_trust"
    INSUFFICIENT_INTERPERSONAL_TRUST = "insufficient_interpersonal_trust"
    SENSITIVITY_THRESHOLD_BREACH = "sensitivity_threshold_breach"
    PEDIGREE_CHAIN_BROKEN = "pedigree_chain_broken"
    REPEATED_BREACH = "repeated_breach"


# ─────────────────────────────────────────────────────────────
# Core data structures
# ─────────────────────────────────────────────────────────────

@dataclass
class AgentIdentity:
    """
    Extended Definition 4/5: Agent identity with role, org membership,
    and capability profile for agentic AI context.
    """
    agent_id: str
    org_id: str
    role: AgentRole
    name: str
    capabilities: list[str] = field(default_factory=list)  # e.g. ["rag", "summarize"]
    reliability_score: float = 0.5    # From boundary spanner regulatory process §4.7
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentTrustState:
    """
    Extended Definition 10: Interaction Trust Relation (ITR) for agentic AI.
    Adds recency weighting and capability-based trust modulation.

    Original ITR: τ(ei, ej) ∈ [0, 1]
    Extension   : τ_agentic = τ_base × recency_weight × capability_match
    """
    trustor_id: str
    trustee_id: str
    base_trust: float                  # τ from original IEOTBSM
    interaction_count: int = 0         # i from Equation 5
    last_interaction: float = field(default_factory=time.time)
    good_interactions: int = 0
    bad_interactions: int = 0
    recency_decay: float = 0.995       # per-cycle decay (Ebbinghaus forgetting, §4.4)

    @property
    def effective_trust(self) -> float:
        """
        Agentic extension of τ: applies recency decay to base trust.
        Trust degrades slightly without recent positive interactions,
        consistent with the forgetting model in Luna-Reyes et al. [66].
        """
        if self.interaction_count == 0:
            return self.base_trust
        age_penalty = self.recency_decay ** max(0, self.interaction_count - self.good_interactions)
        return max(0.0, min(1.0, self.base_trust * age_penalty))

    def record_good(self):
        self.good_interactions += 1
        self.interaction_count += 1
        self.last_interaction = time.time()
        # Gradual trust increase (logistic-consistent: slow growth)
        self.base_trust = min(1.0, self.base_trust + 0.02)

    def record_bad(self):
        self.bad_interactions += 1
        self.interaction_count += 1
        self.last_interaction = time.time()
        # Trust damage is faster than trust building (asymmetry, §4.4)
        self.base_trust = max(0.0, self.base_trust - 0.08)


@dataclass
class QueryProvenance:
    """
    Extended Definition 6 + 19: Fact + FactPedigree combined for agentic AI.
    A QueryProvenance tracks a cross-org RAG query through the agent hierarchy,
    recording every agent that handled it (pedigree) and the data it accessed.

    Maps to:
      Fact.id              → query_id
      Fact.content         → query_text + retrieved_context
      Fact.pedigree        → agent_chain (signed by each handler)
      Fact.expiration      → ttl_seconds
    """
    query_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    query_text: str = ""
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    originating_org: str = ""
    originating_agent: str = ""
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 300.0         # Definition 32: expiration interval

    # Pedigree (Definition 19): ordered list of agent signatures
    agent_chain: list[dict] = field(default_factory=list)

    # Content accumulated as query flows through agents
    retrieved_contexts: list[dict] = field(default_factory=list)
    final_answer: str = ""

    # Trust audit trail
    trust_checks: list[dict] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    def sign(self, agent_id: str, org_id: str, role: AgentRole, action: str):
        """Definition 18/19: Agent signs the query pedigree."""
        self.agent_chain.append({
            "agent_id": agent_id,
            "org_id": org_id,
            "role": role.value,
            "action": action,
            "timestamp": time.time()
        })

    def add_context(self, org_id: str, agent_id: str,
                    content: str, sensitivity: SensitivityLevel):
        """Record retrieved context with provenance metadata."""
        self.retrieved_contexts.append({
            "org_id": org_id,
            "agent_id": agent_id,
            "content": content,
            "sensitivity": sensitivity.value,
            "timestamp": time.time()
        })

    def log_trust_check(self, from_id: str, to_id: str,
                        trust_val: float, threshold: float, passed: bool):
        self.trust_checks.append({
            "from": from_id,
            "to": to_id,
            "trust": round(trust_val, 3),
            "threshold": threshold,
            "passed": passed,
            "timestamp": time.time()
        })


@dataclass
class TrustViolation:
    """
    Agentic extension: Structured record of a trust violation routed to
    human review queue. Extends the concept of 'unintended receiver'
    (Definitions 22–23) to include actionable human-review metadata.
    """
    violation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    violation_type: ViolationType = ViolationType.INSUFFICIENT_INTER_ORG_TRUST
    query_id: str = ""
    requesting_org: str = ""
    target_org: str = ""
    requesting_agent: str = ""
    trust_value: float = 0.0
    required_threshold: float = 0.0
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    query_text: str = ""
    agent_chain_at_violation: list[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"            # pending | approved | denied
    reviewer_notes: str = ""


@dataclass
class TrustMetrics:
    """
    Definitions 27–30: IA and SM metrics, extended for agentic AI.
    Tracks per-cycle and cumulative performance of the trust system.
    """
    cycle: int = 0
    intended_queries: int = 0          # Definition 20/21: intended receivers
    unintended_queries: int = 0        # Definition 22/23: unintended receivers
    total_queries: int = 0             # Definition 26
    human_review_count: int = 0        # New: violations routed to humans
    approved_by_human: int = 0
    denied_by_human: int = 0

    @property
    def ia_pct(self) -> float:         # Definition 28
        if self.total_queries == 0:
            return 100.0
        return (self.intended_queries / self.total_queries) * 100

    @property
    def sm_pct(self) -> float:         # Definition 30
        if self.total_queries == 0:
            return 0.0
        return (self.unintended_queries / self.total_queries) * 100


# ─────────────────────────────────────────────────────────────
# Inter-organizational trust calculus (Equations 5, 6, 7)
# ─────────────────────────────────────────────────────────────

class InterOrgTrustLedger:
    """
    Manages inter-organizational trust using the IEOTBSM logistic growth model.
    Extended to support sensitivity-adjusted thresholds for agentic AI.

    Core equations from §4.6:
      Eq 5: τ_i(om,on) = τ_0 / (τ_0 + (1−τ_0)·e^(−r·i))   [logistic growth]
      Eq 6: r = Σ BS trust values / (xy)^x                  [BS-driven rate]
      Eq 7: τ_bs = τ_org·α + τ_bs_prev·(1−α)               [instantaneous BS trust]
    """

    # Sensitivity-adjusted trust thresholds (agentic extension)
    SENSITIVITY_THRESHOLDS = {
        SensitivityLevel.PUBLIC:       0.10,
        SensitivityLevel.INTERNAL:     0.35,
        SensitivityLevel.CONFIDENTIAL: 0.60,
        SensitivityLevel.RESTRICTED:   0.80,
    }

    def __init__(self, alpha: float = 0.65, rate_scale: float = 0.005):
        self.alpha = alpha              # inter-org trust weight (>0.5 per §4.6)
        self.rate_scale = rate_scale   # scales logistic rate for realistic growth
        # org_id → org_id → float
        self._trust: dict[str, dict[str, float]] = defaultdict(dict)
        self._initial: dict[str, dict[str, float]] = defaultdict(dict)
        self._interactions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._history: list[dict] = []

    def initialize(self, org_id: str, partner_id: str, tau_0: float):
        """Set initial trust τ_0 between two organizations."""
        self._trust[org_id][partner_id] = tau_0
        self._initial[org_id][partner_id] = tau_0

    def get(self, org_id: str, partner_id: str) -> float:
        return self._trust.get(org_id, {}).get(partner_id, 0.0)

    def threshold_for(self, sensitivity: SensitivityLevel) -> float:
        """Agentic extension: sensitivity-adjusted trust threshold."""
        return self.SENSITIVITY_THRESHOLDS[sensitivity]

    def check(self, org_id: str, partner_id: str,
              sensitivity: SensitivityLevel) -> tuple[bool, float, float]:
        """
        ISP3 (Definition 14): Check if inter-org trust meets sensitivity threshold.
        Returns (passed, trust_value, required_threshold).
        """
        trust_val = self.get(org_id, partner_id)
        threshold = self.threshold_for(sensitivity)
        return trust_val >= threshold, trust_val, threshold

    def update(self, org_id: str, partner_id: str,
               bs_trust_values: list[float], num_bs: int):
        """
        Equations 5 & 6: Update inter-org trust via logistic growth.
        Called after each successful or attempted cross-org interaction.
        """
        self._interactions[org_id][partner_id] += 1
        i = self._interactions[org_id][partner_id]
        tau_0 = self._initial[org_id].get(partner_id, 0.3)

        # Eq 6: compute rate from BS trust averages
        if bs_trust_values and num_bs > 0:
            xy = len(bs_trust_values)
            denom = (xy ** max(num_bs, 1))
            r = (sum(bs_trust_values) / denom) * self.rate_scale
        else:
            r = 0.001 * self.rate_scale

        # Eq 5: logistic growth
        denom = tau_0 + (1.0 - tau_0) * math.exp(-r * i)
        new_trust = tau_0 / denom if denom > 0 else tau_0
        self._trust[org_id][partner_id] = min(1.0, new_trust)

        self._history.append({
            "org": org_id, "partner": partner_id,
            "trust": round(new_trust, 4), "i": i, "r": round(r, 6)
        })

    def apply_bs_influence(self, org_id: str, partner_id: str,
                           bs_trust: float):
        """Equation 7: Apply instantaneous BS trust influence."""
        io_trust = self.get(org_id, partner_id)
        new_bs = io_trust * self.alpha + bs_trust * (1.0 - self.alpha)
        return min(1.0, max(0.0, new_bs))

    def penalize(self, org_id: str, partner_id: str, amount: float = 0.05):
        """Agentic extension: apply trust penalty on confirmed violation."""
        current = self.get(org_id, partner_id)
        self._trust[org_id][partner_id] = max(0.0, current - amount)

    def matrix(self, org_ids: list[str]) -> list[list[float]]:
        """Return trust matrix for visualization."""
        return [
            [1.0 if i == j else round(self.get(org_ids[i], org_ids[j]), 3)
             for j in range(len(org_ids))]
            for i in range(len(org_ids))
        ]

    def history(self) -> list[dict]:
        return self._history


# ─────────────────────────────────────────────────────────────
# Agentic Trust Policy Models (TPM extension)
# ─────────────────────────────────────────────────────────────

class AgenticTPM:
    """
    Extended Trust Policy Models for agentic AI.

    TPM1: Proportional trust decay along query chain (Definition 24, TPM1)
    TPM2: Uniform trust decay across all chain edges (Definition 24, TPM2)
    TPM3: Initiator cuts trust to all chain agents (Definition 24, TPM3)
    TPM4: NEW — Route to human review queue before any trust modification.
          Applied when violation is at CONFIDENTIAL or RESTRICTED sensitivity,
          or when repeated breaches occur from same agent pair.
    """

    def __init__(self, mode: int = 4, decrement: float = 0.06,
                 repeat_threshold: int = 3):
        self.mode = mode
        self.decrement = decrement
        self.repeat_threshold = repeat_threshold
        self._breach_counts: dict[tuple, int] = defaultdict(int)

    def apply(self,
              provenance: QueryProvenance,
              trust_states: dict[tuple, AgentTrustState],
              ledger: InterOrgTrustLedger,
              violation: TrustViolation,
              human_queue: list[TrustViolation]) -> str:
        """
        Apply the appropriate TPM. Returns action taken.
        TPM4 (human review) takes precedence for high-sensitivity or repeated breaches.
        """
        pair = (violation.requesting_org, violation.target_org)
        self._breach_counts[pair] += 1
        repeated = self._breach_counts[pair] >= self.repeat_threshold

        # TPM4: escalate to human review
        if (self.mode == 4 or
                violation.sensitivity in (SensitivityLevel.CONFIDENTIAL,
                                          SensitivityLevel.RESTRICTED) or
                repeated):
            if repeated:
                violation.violation_type = ViolationType.REPEATED_BREACH
            human_queue.append(violation)
            return f"TPM4:human_review(violation={violation.violation_id})"

        # TPM1: proportional decay
        if self.mode == 1:
            chain = provenance.agent_chain
            depth = len(chain)
            for k in range(1, depth):
                prev_id = chain[k-1]["agent_id"]
                curr_id = chain[k]["agent_id"]
                key = (prev_id, curr_id)
                if key in trust_states:
                    degree = k + 1
                    update = self.decrement ** (depth - degree + 1)
                    trust_states[key].base_trust = max(
                        0.0, trust_states[key].base_trust - update)
            return f"TPM1:proportional_decay(depth={depth})"

        # TPM2: uniform decay
        if self.mode == 2:
            chain = provenance.agent_chain
            for k in range(1, len(chain)):
                prev_id = chain[k-1]["agent_id"]
                curr_id = chain[k]["agent_id"]
                key = (prev_id, curr_id)
                if key in trust_states:
                    trust_states[key].base_trust = max(
                        0.0, trust_states[key].base_trust - self.decrement)
            return f"TPM2:uniform_decay"

        # TPM3: initiator-direct cuts
        if self.mode == 3:
            initiator = provenance.originating_agent
            for entry in provenance.agent_chain[1:]:
                key = (initiator, entry["agent_id"])
                if key in trust_states:
                    trust_states[key].base_trust = max(
                        0.0, trust_states[key].base_trust - self.decrement)
                # Also penalize inter-org trust
                ledger.penalize(violation.requesting_org,
                                violation.target_org, self.decrement)
            return f"TPM3:initiator_cuts"

        return "no_tpm_applied"


# ─────────────────────────────────────────────────────────────
# Trust Gate — enforces ISP at LangGraph edge boundaries
# ─────────────────────────────────────────────────────────────

class TrustGate:
    """
    Definition 14 (ISP) implemented as a callable gate for LangGraph edges.

    In the original IEOTBSM, ISP1-ISP4 are rules governing fact traversal.
    Here they become callable checks at each LangGraph node transition,
    enforcing trust before any agent can pass a query to another agent.

    ISP1/ISP2 → intra-org agent-to-agent checks
    ISP3/ISP4 → inter-org BS-to-BS checks (includes inter-org trust ledger)
    """

    def __init__(self, ledger: InterOrgTrustLedger,
                 agent_trust: dict[tuple, AgentTrustState]):
        self.ledger = ledger
        self.agent_trust = agent_trust   # (trustor_id, trustee_id) → AgentTrustState

    def check_intra_org(self, trustor_id: str, trustee_id: str,
                        sensitivity: SensitivityLevel,
                        provenance: QueryProvenance) -> tuple[bool, float]:
        """ISP1/ISP2: Intra-org trust check."""
        key = (trustor_id, trustee_id)
        state = self.agent_trust.get(key)
        trust_val = state.effective_trust if state else 0.0
        threshold = self.ledger.threshold_for(sensitivity)
        passed = trust_val >= threshold
        provenance.log_trust_check(trustor_id, trustee_id, trust_val, threshold, passed)
        return passed, trust_val

    def check_inter_org(self, trustor_agent_id: str, trustee_agent_id: str,
                        org_id: str, partner_org_id: str,
                        sensitivity: SensitivityLevel,
                        provenance: QueryProvenance) -> tuple[bool, float]:
        """
        ISP3/ISP4: Inter-org BS trust check.
        Both interpersonal BS trust AND inter-org trust must meet threshold.
        High inter-org trust can compensate for lower interpersonal trust (§4.6).
        """
        # Inter-personal BS trust
        key = (trustor_agent_id, trustee_agent_id)
        bs_state = self.agent_trust.get(key)
        bs_trust = bs_state.effective_trust if bs_state else 0.0

        # Inter-organizational trust
        io_trust = self.ledger.get(org_id, partner_org_id)

        # Equation 7 compensation: high IO trust compensates low BS trust
        alpha = self.ledger.alpha
        effective = io_trust * alpha + bs_trust * (1.0 - alpha)

        threshold = self.ledger.threshold_for(sensitivity)
        passed = effective >= threshold
        provenance.log_trust_check(
            f"{org_id}:{trustor_agent_id}",
            f"{partner_org_id}:{trustee_agent_id}",
            effective, threshold, passed
        )
        return passed, effective

    def record_outcome(self, trustor_id: str, trustee_id: str, success: bool):
        """Update agent trust state after an interaction."""
        key = (trustor_id, trustee_id)
        if key in self.agent_trust:
            if success:
                self.agent_trust[key].record_good()
            else:
                self.agent_trust[key].record_bad()
