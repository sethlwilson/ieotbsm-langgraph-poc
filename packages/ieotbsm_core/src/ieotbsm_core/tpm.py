"""Trust Policy Models (TPM1–TPM4)."""

from __future__ import annotations

from collections import defaultdict

from ieotbsm_core.enums import SensitivityLevel, ViolationType
from ieotbsm_core.ledger import InterOrgTrustLedger
from ieotbsm_core.models import AgentTrustState, QueryProvenance, TrustViolation


class AgenticTPM:
    def __init__(
        self,
        mode: int = 4,
        decrement: float = 0.06,
        repeat_threshold: int = 3,
    ):
        self.mode = mode
        self.decrement = decrement
        self.repeat_threshold = repeat_threshold
        self._breach_counts: dict[tuple[str, str], int] = defaultdict(int)

    def apply(
        self,
        provenance: QueryProvenance,
        trust_states: dict[tuple[str, str], AgentTrustState],
        ledger: InterOrgTrustLedger,
        violation: TrustViolation,
        human_queue: list[TrustViolation],
    ) -> str:
        pair = (violation.requesting_org, violation.target_org)
        self._breach_counts[pair] += 1
        repeated = self._breach_counts[pair] >= self.repeat_threshold

        if (
            self.mode == 4
            or violation.sensitivity
            in (SensitivityLevel.CONFIDENTIAL, SensitivityLevel.RESTRICTED)
            or repeated
        ):
            if repeated:
                violation.violation_type = ViolationType.REPEATED_BREACH
            human_queue.append(violation)
            return f"TPM4:human_review(violation={violation.violation_id})"

        if self.mode == 1:
            chain = provenance.agent_chain
            depth = len(chain)
            for k in range(1, depth):
                prev_id = chain[k - 1]["agent_id"]
                curr_id = chain[k]["agent_id"]
                key = (prev_id, curr_id)
                if key in trust_states:
                    degree = k + 1
                    update = self.decrement ** (depth - degree + 1)
                    trust_states[key].base_trust = max(
                        0.0, trust_states[key].base_trust - update
                    )
            return f"TPM1:proportional_decay(depth={depth})"

        if self.mode == 2:
            chain = provenance.agent_chain
            for k in range(1, len(chain)):
                prev_id = chain[k - 1]["agent_id"]
                curr_id = chain[k]["agent_id"]
                key = (prev_id, curr_id)
                if key in trust_states:
                    trust_states[key].base_trust = max(
                        0.0,
                        trust_states[key].base_trust - self.decrement,
                    )
            return "TPM2:uniform_decay"

        if self.mode == 3:
            initiator = provenance.originating_agent
            for entry in provenance.agent_chain[1:]:
                key = (initiator, entry["agent_id"])
                if key in trust_states:
                    trust_states[key].base_trust = max(
                        0.0,
                        trust_states[key].base_trust - self.decrement,
                    )
                ledger.penalize(
                    violation.requesting_org,
                    violation.target_org,
                    self.decrement,
                )
            return "TPM3:initiator_cuts"

        return "no_tpm_applied"

    def to_persistence(self) -> dict:
        return {
            "mode": self.mode,
            "decrement": self.decrement,
            "repeat_threshold": self.repeat_threshold,
            "breach_counts": {
                f"{a}\x1f{b}": c
                for (a, b), c in self._breach_counts.items()
            },
        }

    @classmethod
    def from_persistence(cls, data: dict) -> AgenticTPM:
        obj = cls(
            mode=int(data.get("mode", 4)),
            decrement=float(data.get("decrement", 0.06)),
            repeat_threshold=int(data.get("repeat_threshold", 3)),
        )
        for k, c in (data.get("breach_counts") or {}).items():
            parts = k.split("\x1f", 1)
            if len(parts) == 2:
                obj._breach_counts[(parts[0], parts[1])] = int(c)
        return obj
