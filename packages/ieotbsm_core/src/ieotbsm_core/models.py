"""In-process domain models (dataclasses)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from ieotbsm_core.enums import AgentRole, SensitivityLevel, ViolationType


@dataclass
class AgentIdentity:
    agent_id: str
    org_id: str
    role: AgentRole
    name: str
    capabilities: list[str] = field(default_factory=list)
    reliability_score: float = 0.5
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentTrustState:
    trustor_id: str
    trustee_id: str
    base_trust: float
    interaction_count: int = 0
    last_interaction: float = field(default_factory=time.time)
    good_interactions: int = 0
    bad_interactions: int = 0
    recency_decay: float = 0.995

    @property
    def effective_trust(self) -> float:
        if self.interaction_count == 0:
            return self.base_trust
        age_penalty = self.recency_decay ** max(
            0, self.interaction_count - self.good_interactions
        )
        return max(0.0, min(1.0, self.base_trust * age_penalty))

    def record_good(self) -> None:
        self.good_interactions += 1
        self.interaction_count += 1
        self.last_interaction = time.time()
        self.base_trust = min(1.0, self.base_trust + 0.02)

    def record_bad(self) -> None:
        self.bad_interactions += 1
        self.interaction_count += 1
        self.last_interaction = time.time()
        self.base_trust = max(0.0, self.base_trust - 0.08)


@dataclass
class QueryProvenance:
    query_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    query_text: str = ""
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    originating_org: str = ""
    originating_agent: str = ""
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 300.0
    agent_chain: list[dict] = field(default_factory=list)
    retrieved_contexts: list[dict] = field(default_factory=list)
    final_answer: str = ""
    trust_checks: list[dict] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    def sign(
        self, agent_id: str, org_id: str, role: AgentRole, action: str
    ) -> None:
        self.agent_chain.append(
            {
                "agent_id": agent_id,
                "org_id": org_id,
                "role": role.value,
                "action": action,
                "timestamp": time.time(),
            }
        )

    def add_context(
        self,
        org_id: str,
        agent_id: str,
        content: str,
        sensitivity: SensitivityLevel,
    ) -> None:
        self.retrieved_contexts.append(
            {
                "org_id": org_id,
                "agent_id": agent_id,
                "content": content,
                "sensitivity": sensitivity.value,
                "timestamp": time.time(),
            }
        )

    def log_trust_check(
        self,
        from_id: str,
        to_id: str,
        trust_val: float,
        threshold: float,
        passed: bool,
    ) -> None:
        self.trust_checks.append(
            {
                "from": from_id,
                "to": to_id,
                "trust": round(trust_val, 3),
                "threshold": threshold,
                "passed": passed,
                "timestamp": time.time(),
            }
        )


@dataclass
class TrustViolation:
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
    status: str = "pending"
    reviewer_notes: str = ""


@dataclass
class TrustMetrics:
    cycle: int = 0
    intended_queries: int = 0
    unintended_queries: int = 0
    total_queries: int = 0
    human_review_count: int = 0
    approved_by_human: int = 0
    denied_by_human: int = 0

    @property
    def ia_pct(self) -> float:
        if self.total_queries == 0:
            return 100.0
        return (self.intended_queries / self.total_queries) * 100

    @property
    def sm_pct(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return (self.unintended_queries / self.total_queries) * 100
