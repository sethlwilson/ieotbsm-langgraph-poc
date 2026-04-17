"""ISP-style trust gate."""

from __future__ import annotations

from ieotbsm_core.enums import SensitivityLevel
from ieotbsm_core.ledger import InterOrgTrustLedger
from ieotbsm_core.models import AgentTrustState, QueryProvenance


class TrustGate:
    def __init__(
        self,
        ledger: InterOrgTrustLedger,
        agent_trust: dict[tuple[str, str], AgentTrustState],
    ):
        self.ledger = ledger
        self.agent_trust = agent_trust

    def check_intra_org(
        self,
        trustor_id: str,
        trustee_id: str,
        sensitivity: SensitivityLevel,
        provenance: QueryProvenance,
    ) -> tuple[bool, float]:
        key = (trustor_id, trustee_id)
        state = self.agent_trust.get(key)
        trust_val = state.effective_trust if state else 0.0
        threshold = self.ledger.threshold_for(sensitivity)
        passed = trust_val >= threshold
        provenance.log_trust_check(trustor_id, trustee_id, trust_val, threshold, passed)
        return passed, trust_val

    def check_inter_org(
        self,
        trustor_agent_id: str,
        trustee_agent_id: str,
        org_id: str,
        partner_org_id: str,
        sensitivity: SensitivityLevel,
        provenance: QueryProvenance,
    ) -> tuple[bool, float]:
        key = (trustor_agent_id, trustee_agent_id)
        bs_state = self.agent_trust.get(key)
        bs_trust = bs_state.effective_trust if bs_state else 0.0
        io_trust = self.ledger.get(org_id, partner_org_id)
        alpha = self.ledger.alpha
        effective = io_trust * alpha + bs_trust * (1.0 - alpha)
        threshold = self.ledger.threshold_for(sensitivity)
        passed = effective >= threshold
        provenance.log_trust_check(
            f"{org_id}:{trustor_agent_id}",
            f"{partner_org_id}:{trustee_agent_id}",
            effective,
            threshold,
            passed,
        )
        return passed, effective

    def record_outcome(self, trustor_id: str, trustee_id: str, success: bool) -> None:
        key = (trustor_id, trustee_id)
        if key in self.agent_trust:
            if success:
                self.agent_trust[key].record_good()
            else:
                self.agent_trust[key].record_bad()
