"""Enumerations for the IEOTBSM agentic trust model."""

from enum import Enum


class AgentRole(Enum):
    INTERNAL = "internal"
    BOUNDARY_SPANNER = "boundary_spanner"
    ORG_ORCHESTRATOR = "org_orchestrator"


class SensitivityLevel(Enum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


class ViolationType(Enum):
    INSUFFICIENT_INTER_ORG_TRUST = "insufficient_inter_org_trust"
    INSUFFICIENT_INTERPERSONAL_TRUST = "insufficient_interpersonal_trust"
    SENSITIVITY_THRESHOLD_BREACH = "sensitivity_threshold_breach"
    PEDIGREE_CHAIN_BROKEN = "pedigree_chain_broken"
    REPEATED_BREACH = "repeated_breach"
