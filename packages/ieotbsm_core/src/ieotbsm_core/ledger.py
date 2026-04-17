"""Inter-organizational trust ledger (τ)."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from ieotbsm_core.enums import SensitivityLevel


class InterOrgTrustLedger:
    SENSITIVITY_THRESHOLDS = {
        SensitivityLevel.PUBLIC: 0.10,
        SensitivityLevel.INTERNAL: 0.35,
        SensitivityLevel.CONFIDENTIAL: 0.60,
        SensitivityLevel.RESTRICTED: 0.80,
    }

    def __init__(self, alpha: float = 0.65, rate_scale: float = 0.005):
        self.alpha = alpha
        self.rate_scale = rate_scale
        self._trust: dict[str, dict[str, float]] = defaultdict(dict)
        self._initial: dict[str, dict[str, float]] = defaultdict(dict)
        self._interactions: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._history: list[dict] = []

    def initialize(self, org_id: str, partner_id: str, tau_0: float) -> None:
        self._trust[org_id][partner_id] = tau_0
        self._initial[org_id][partner_id] = tau_0

    def get(self, org_id: str, partner_id: str) -> float:
        return self._trust.get(org_id, {}).get(partner_id, 0.0)

    def threshold_for(self, sensitivity: SensitivityLevel) -> float:
        return self.SENSITIVITY_THRESHOLDS[sensitivity]

    def check(
        self, org_id: str, partner_id: str, sensitivity: SensitivityLevel
    ) -> tuple[bool, float, float]:
        trust_val = self.get(org_id, partner_id)
        threshold = self.threshold_for(sensitivity)
        return trust_val >= threshold, trust_val, threshold

    def update(
        self,
        org_id: str,
        partner_id: str,
        bs_trust_values: list[float],
        num_bs: int,
    ) -> None:
        self._interactions[org_id][partner_id] += 1
        i = self._interactions[org_id][partner_id]
        tau_0 = self._initial[org_id].get(partner_id, 0.3)

        if bs_trust_values and num_bs > 0:
            xy = len(bs_trust_values)
            denom = xy ** max(num_bs, 1)
            r = (sum(bs_trust_values) / denom) * self.rate_scale
        else:
            r = 0.001 * self.rate_scale

        denom = tau_0 + (1.0 - tau_0) * math.exp(-r * i)
        new_trust = tau_0 / denom if denom > 0 else tau_0
        self._trust[org_id][partner_id] = min(1.0, new_trust)

        self._history.append(
            {
                "org": org_id,
                "partner": partner_id,
                "trust": round(new_trust, 4),
                "i": i,
                "r": round(r, 6),
            }
        )

    def apply_bs_influence(
        self, org_id: str, partner_id: str, bs_trust: float
    ) -> float:
        io_trust = self.get(org_id, partner_id)
        new_bs = io_trust * self.alpha + bs_trust * (1.0 - self.alpha)
        return min(1.0, max(0.0, new_bs))

    def penalize(
        self, org_id: str, partner_id: str, amount: float = 0.05
    ) -> None:
        current = self.get(org_id, partner_id)
        self._trust[org_id][partner_id] = max(0.0, current - amount)

    def matrix(self, org_ids: list[str]) -> list[list[float]]:
        return [
            [
                1.0 if i == j else round(self.get(org_ids[i], org_ids[j]), 3)
                for j in range(len(org_ids))
            ]
            for i in range(len(org_ids))
        ]

    def history(self) -> list[dict]:
        return self._history

    def to_persistence(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "rate_scale": self.rate_scale,
            "trust": {k: dict(v) for k, v in self._trust.items()},
            "initial": {k: dict(v) for k, v in self._initial.items()},
            "interactions": {
                k: dict(v) for k, v in self._interactions.items()
            },
            "history": list(self._history),
        }

    @classmethod
    def from_persistence(cls, data: dict[str, Any]) -> InterOrgTrustLedger:
        obj = cls(
            alpha=float(data.get("alpha", 0.65)),
            rate_scale=float(data.get("rate_scale", 0.005)),
        )
        obj._trust = defaultdict(dict)
        for k, v in (data.get("trust") or {}).items():
            obj._trust[k] = dict(v)
        obj._initial = defaultdict(dict)
        for k, v in (data.get("initial") or {}).items():
            obj._initial[k] = dict(v)
        obj._interactions = defaultdict(lambda: defaultdict(int))
        for k, v in (data.get("interactions") or {}).items():
            for pk, pv in v.items():
                obj._interactions[k][pk] = int(pv)
        obj._history = list(data.get("history") or [])
        return obj
