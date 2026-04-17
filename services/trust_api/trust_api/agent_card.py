"""A2A Agent Card JSON (discovery) for the trust service."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from trust_api.config import Settings


def build_agent_card(settings: Settings) -> dict[str, Any]:
    base = settings.public_base_url.rstrip("/")
    return {
        "name": "IEOTBSM Trust Service",
        "description": (
            "Inter-organizational trust gate, ledger, pedigree chain, and "
            "violation workflow (IEOTBSM PoC)."
        ),
        "version": "0.2.0",
        "protocolVersion": "1.0",
        "supportedInterfaces": [
            {
                "url": f"{base}/v2/a2a",
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            }
        ],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "trust.create_run",
                "name": "Create trust run",
                "description": "POST /v1/runs — correlated run + query_id.",
                "tags": ["trust", "runs"],
                "examples": [f"{base}/v1/runs"],
            },
            {
                "id": "trust.evaluate_gate",
                "name": "Evaluate inter-org gate",
                "description": "POST /v1/runs/{{run_id}}/gate",
                "tags": ["trust", "gate"],
            },
            {
                "id": "trust.append_event",
                "name": "Append run event",
                "description": "POST /v1/runs/{{run_id}}/events (pedigree_sign, context, custom).",
                "tags": ["trust", "provenance"],
            },
            {
                "id": "trust.get_run",
                "name": "Get run snapshot",
                "description": "JSON-RPC trust/getRun or REST snapshot (provenance + chain).",
                "tags": ["trust", "introspection"],
            },
            {
                "id": "trust.ledger_matrix",
                "name": "Ledger matrix",
                "description": "GET /v1/ledger/matrix",
                "tags": ["trust", "ledger"],
            },
            {
                "id": "trust.patch_violation",
                "name": "Patch violation",
                "description": "PATCH /v1/violations/{{id}}",
                "tags": ["trust", "tpm"],
            },
        ],
        "securitySchemes": {
            "trustApiKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            },
            "trustTenantId": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Tenant-ID",
            },
        },
        "security": [{"trustApiKey": []}, {"trustTenantId": []}],
    }


def agent_card_etag(card: dict[str, Any]) -> str:
    raw = json.dumps(card, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()
