from ieotbsm_core.enums import SensitivityLevel
from ieotbsm_core.ledger import InterOrgTrustLedger


def test_threshold_monotonicity():
    led = InterOrgTrustLedger()
    assert led.threshold_for(SensitivityLevel.PUBLIC) < led.threshold_for(
        SensitivityLevel.INTERNAL
    )
    assert led.threshold_for(SensitivityLevel.INTERNAL) < led.threshold_for(
        SensitivityLevel.CONFIDENTIAL
    )
    assert led.threshold_for(SensitivityLevel.CONFIDENTIAL) < led.threshold_for(
        SensitivityLevel.RESTRICTED
    )


def test_check_and_update_roundtrip():
    led = InterOrgTrustLedger(alpha=0.65)
    led.initialize("a", "b", 0.5)
    ok, tau, th = led.check("a", "b", SensitivityLevel.INTERNAL)
    assert tau == 0.5
    assert th == led.threshold_for(SensitivityLevel.INTERNAL)
    led.update("a", "b", [0.7], 1)
    assert led.get("a", "b") >= 0.5


def test_persistence_roundtrip():
    led = InterOrgTrustLedger(alpha=0.7, rate_scale=0.01)
    led.initialize("x", "y", 0.4)
    led.update("x", "y", [0.5], 1)
    blob = led.to_persistence()
    led2 = InterOrgTrustLedger.from_persistence(blob)
    assert led2.alpha == led.alpha
    assert led2.get("x", "y") == led.get("x", "y")
