from ieotbsm_core.enums import SensitivityLevel
from ieotbsm_core.ledger import InterOrgTrustLedger
from ieotbsm_core.models import AgentTrustState, QueryProvenance, TrustViolation
from ieotbsm_core.tpm import AgenticTPM


def test_tpm4_queues_human():
    tpm = AgenticTPM(mode=4, decrement=0.06)
    prov = QueryProvenance(originating_agent="a0")
    prov.agent_chain = [
        {"agent_id": "a0"},
        {"agent_id": "a1"},
    ]
    led = InterOrgTrustLedger()
    led.initialize("o1", "o2", 0.5)
    states = {
        ("a0", "a1"): AgentTrustState(
            trustor_id="a0", trustee_id="a1", base_trust=0.8
        )
    }
    v = TrustViolation(
        requesting_org="o1",
        target_org="o2",
        sensitivity=SensitivityLevel.CONFIDENTIAL,
    )
    hq: list = []
    tpm.apply(prov, states, led, v, hq)
    assert len(hq) == 1
    assert hq[0].violation_id == v.violation_id
