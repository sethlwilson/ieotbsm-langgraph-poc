"""Stdio MCP server — tools map to Trust HTTP API (MCP-first agent boundary)."""

from __future__ import annotations

import json
import os
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ieotbsm-trust")


def _headers() -> dict[str, str]:
    return {
        "X-API-Key": os.getenv("TRUST_API_KEY", "dev-key"),
        "X-Tenant-ID": os.getenv("TRUST_API_TENANT", "default"),
        "Content-Type": "application/json",
    }


def _base() -> str:
    return os.getenv("TRUST_API_BASE_URL", "http://127.0.0.1:8088").rstrip("/")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=_base(), headers=_headers(), timeout=60.0)


@mcp.tool()
async def trust_admin_seed() -> str:
    """Reset tenant trust state to a fresh demo network (dev/admin)."""
    async with _client() as c:
        r = await c.post("/v1/admin/seed")
        r.raise_for_status()
        return json.dumps(r.json())


@mcp.tool()
async def trust_get_state() -> str:
    """Return trust matrix, org list, cycle, human-review queue size."""
    async with _client() as c:
        r = await c.get("/v1/state")
        r.raise_for_status()
        return json.dumps(r.json())


@mcp.tool()
async def trust_ledger_matrix() -> str:
    """Return τ matrix labels and numeric grid."""
    async with _client() as c:
        r = await c.get("/v1/ledger/matrix")
        r.raise_for_status()
        return json.dumps(r.json())


@mcp.tool()
async def trust_create_run(
    requesting_org_id: str,
    query_text: str = "",
    requesting_agent_id: str = "",
    sensitivity: Annotated[int, "0=PUBLIC,1=INTERNAL,2=CONFIDENTIAL,3=RESTRICTED"] = 1,
) -> str:
    """Start a correlated trust run; returns run_id and query_id."""
    body = {
        "schema_version": 1,
        "query_text": query_text,
        "requesting_org_id": requesting_org_id,
        "requesting_agent_id": requesting_agent_id,
        "sensitivity": sensitivity,
    }
    async with _client() as c:
        r = await c.post("/v1/runs", json=body)
        r.raise_for_status()
        return json.dumps(r.json())


@mcp.tool()
async def trust_evaluate_gate(
    run_id: str,
    trustor_org_id: str,
    trustee_org_id: str,
    sensitivity: Annotated[int, "0–3 sensitivity tier"] = 1,
    trustor_agent_id: str | None = None,
    trustee_agent_id: str | None = None,
    commit: Annotated[
        bool,
        "If true, persist ledger updates after an allow (successful hop).",
    ] = False,
) -> str:
    """Evaluate ISP-style inter-org gate for one hop; optional commit updates τ."""
    body = {
        "schema_version": 1,
        "trustor_org_id": trustor_org_id,
        "trustee_org_id": trustee_org_id,
        "trustor_agent_id": trustor_agent_id,
        "trustee_agent_id": trustee_agent_id,
        "sensitivity": sensitivity,
    }
    async with _client() as c:
        r = await c.post(
            f"/v1/runs/{run_id}/gate",
            json=body,
            params={"commit": str(commit).lower()},
        )
        r.raise_for_status()
        return json.dumps(r.json())


@mcp.tool()
async def trust_append_run_event(
    run_id: str,
    event_type: Annotated[str, "pedigree_sign | context | custom"],
    payload_json: str,
) -> str:
    """Append a provenance event (payload_json is a JSON object string)."""
    payload = json.loads(payload_json) if payload_json.strip() else {}
    body = {"schema_version": 1, "event_type": event_type, "payload": payload}
    async with _client() as c:
        r = await c.post(f"/v1/runs/{run_id}/events", json=body)
        r.raise_for_status()
        return json.dumps(r.json())


@mcp.tool()
async def trust_patch_violation(
    violation_id: str,
    status: Annotated[str, "pending | approved | denied"],
    reviewer_notes: str = "",
) -> str:
    """Update human-review outcome for a violation id."""
    body = {
        "schema_version": 1,
        "status": status,
        "reviewer_notes": reviewer_notes,
    }
    async with _client() as c:
        r = await c.patch(f"/v1/violations/{violation_id}", json=body)
        r.raise_for_status()
        return json.dumps(r.json())


@mcp.resource("trust://state")
async def trust_resource_state() -> str:
    """Latest tenant trust summary (same payload as trust_get_state)."""
    async with _client() as c:
        r = await c.get("/v1/state")
        r.raise_for_status()
        return json.dumps(r.json(), indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
