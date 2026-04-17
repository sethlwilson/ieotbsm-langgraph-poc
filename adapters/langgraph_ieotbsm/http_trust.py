"""Synchronous HTTP client for the Trust API (LangGraph remote trust mode)."""

from __future__ import annotations

import os
from typing import Any

import httpx


class TrustApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        tenant: str | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("IEOTBSM_TRUST_API_URL")
            or "http://127.0.0.1:8088"
        ).rstrip("/")
        self.headers = {
            "X-API-Key": api_key
            or os.getenv("IEOTBSM_TRUST_API_KEY")
            or os.getenv("TRUST_API_API_KEY", "dev-key"),
            "X-Tenant-ID": tenant or os.getenv("IEOTBSM_TRUST_TENANT", "default"),
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, headers=self.headers, timeout=60.0)

    def admin_seed(self) -> dict[str, Any]:
        with self._client() as c:
            r = c.post("/v1/admin/seed")
            r.raise_for_status()
            return r.json()

    def create_run(
        self,
        query_text: str,
        requesting_org_id: str,
        requesting_agent_id: str,
        sensitivity: int,
    ) -> dict[str, Any]:
        body = {
            "schema_version": 1,
            "query_text": query_text,
            "requesting_org_id": requesting_org_id,
            "requesting_agent_id": requesting_agent_id,
            "sensitivity": sensitivity,
        }
        with self._client() as c:
            r = c.post("/v1/runs", json=body)
            r.raise_for_status()
            return r.json()

    def evaluate_gate(
        self,
        run_id: str,
        trustor_org_id: str,
        trustee_org_id: str,
        trustor_agent_id: str | None,
        trustee_agent_id: str | None,
        sensitivity: int,
        *,
        commit: bool = True,
    ) -> dict[str, Any]:
        body = {
            "schema_version": 1,
            "trustor_org_id": trustor_org_id,
            "trustee_org_id": trustee_org_id,
            "trustor_agent_id": trustor_agent_id,
            "trustee_agent_id": trustee_agent_id,
            "sensitivity": sensitivity,
        }
        with self._client() as c:
            r = c.post(
                f"/v1/runs/{run_id}/gate",
                json=body,
                params={"commit": str(commit).lower()},
            )
            r.raise_for_status()
            return r.json()

    def get_snapshot(self) -> dict[str, Any]:
        with self._client() as c:
            r = c.get("/v1/tenant/snapshot")
            r.raise_for_status()
            return r.json()

    def put_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._client() as c:
            r = c.put("/v1/tenant/snapshot", json=snapshot)
            r.raise_for_status()

    def sync_network(self, network: Any) -> None:
        network.import_trust_snapshot(self.get_snapshot())
