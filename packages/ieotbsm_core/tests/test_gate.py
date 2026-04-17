from ieotbsm_core.enums import AgentRole, SensitivityLevel
from ieotbsm_core.gate import TrustGate
from ieotbsm_core.ledger import InterOrgTrustLedger
from ieotbsm_core.models import AgentTrustState, QueryProvenance


def test_inter_org_gate_high_io_trust():
    led = InterOrgTrustLedger(alpha=0.65)
    led.initialize("org_a", "org_b", 0.95)
    agent_trust: dict = {}
    agent_trust[("bs_a", "bs_b")] = AgentTrustState(
        trustor_id="bs_a", trustee_id="bs_b", base_trust=0.1
    )
    gate = TrustGate(led, agent_trust)
    prov = QueryProvenance()
    passed, eff = gate.check_inter_org(
        "bs_a",
        "bs_b",
        "org_a",
        "org_b",
        SensitivityLevel.INTERNAL,
        prov,
    )
    assert eff > 0.5
    assert passed is True


def test_inter_org_gate_denied():
    led = InterOrgTrustLedger(alpha=0.65)
    led.initialize("org_a", "org_b", 0.05)
    agent_trust = {
        ("bs_a", "bs_b"): AgentTrustState(
            trustor_id="bs_a", trustee_id="bs_b", base_trust=0.05
        )
    }
    gate = TrustGate(led, agent_trust)
    prov = QueryProvenance()
    passed, eff = gate.check_inter_org(
        "bs_a",
        "bs_b",
        "org_a",
        "org_b",
        SensitivityLevel.RESTRICTED,
        prov,
    )
    assert passed is False
    assert len(prov.trust_checks) == 1
