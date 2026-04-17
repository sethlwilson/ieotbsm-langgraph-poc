"""
IEOTBSM Trust Engine — compatibility shim.

Implementation lives in the ``ieotbsm_core`` package. Install with:

  pip install -e ./packages/ieotbsm_core
"""

from ieotbsm_core import (  # noqa: F401
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

__all__ = [
    "AgentIdentity",
    "AgentRole",
    "AgentTrustState",
    "AgenticTPM",
    "InterOrgTrustLedger",
    "QueryProvenance",
    "SensitivityLevel",
    "TrustGate",
    "TrustMetrics",
    "TrustViolation",
    "ViolationType",
]
