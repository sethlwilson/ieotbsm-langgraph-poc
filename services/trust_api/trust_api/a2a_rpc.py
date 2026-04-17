"""Minimal JSON-RPC 2.0 surface for A2A clients (delegates to TrustApiService)."""

from __future__ import annotations

from typing import Any

from ieotbsm_core.schemas import (
    GateEvaluateRequestV1,
    RunCreateRequestV1,
    RunEventAppendRequestV1,
)

from trust_api.service import TrustApiService

SUPPORTED_A2A_VERSIONS = frozenset({"1.0", "1.0.0"})


def _rpc_result(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _rpc_err(rpc_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": err}


def handle_a2a_jsonrpc(
    body: dict[str, Any],
    *,
    service: TrustApiService,
    tenant_id: str,
    a2a_version: str | None,
) -> dict[str, Any]:
    rpc_id = body.get("id")
    ver = (a2a_version or "").strip()
    if ver not in SUPPORTED_A2A_VERSIONS:
        return _rpc_err(
            rpc_id,
            -32001,
            "Unsupported or missing A2A-Version header (supported: 1.0, 1.0.0)",
            {"supported": sorted(SUPPORTED_A2A_VERSIONS)},
        )

    if body.get("jsonrpc") != "2.0":
        return _rpc_err(rpc_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = body.get("method")
    params = body.get("params")
    if not isinstance(params, dict):
        params = {}

    try:
        return _dispatch(method, params, rpc_id, service=service, tenant_id=tenant_id)
    except KeyError as e:
        return _rpc_err(rpc_id, -32004, str(e) or "not found")
    except Exception as e:  # noqa: BLE001 — surface as JSON-RPC
        return _rpc_err(rpc_id, -32603, "Internal error", {"detail": str(e)})


def _dispatch(
    method: str | None,
    params: dict[str, Any],
    rpc_id: Any,
    *,
    service: TrustApiService,
    tenant_id: str,
) -> dict[str, Any]:
    if method == "trust/createRun":
        req = RunCreateRequestV1.model_validate(params)
        out = service.create_run(
            tenant_id,
            req.query_text,
            req.requesting_org_id,
            req.requesting_agent_id,
            req.sensitivity,
        )
        return _rpc_result(rpc_id, out.model_dump())

    if method == "trust/getRun":
        run_id = str(params.get("run_id", ""))
        if not run_id:
            return _rpc_err(rpc_id, -32602, "Invalid params: run_id required")
        snap = service.get_run_snapshot(tenant_id, run_id)
        return _rpc_result(rpc_id, snap)

    if method == "trust/appendEvent":
        run_id = str(params.get("run_id", ""))
        if not run_id:
            return _rpc_err(rpc_id, -32602, "Invalid params: run_id required")
        inner = {k: v for k, v in params.items() if k != "run_id"}
        req = RunEventAppendRequestV1.model_validate(inner)
        out = service.append_run_event(
            tenant_id, run_id, req.event_type, req.payload
        )
        return _rpc_result(rpc_id, out)

    if method == "trust/evaluateGate":
        run_id = str(params.get("run_id", ""))
        if not run_id:
            return _rpc_err(rpc_id, -32602, "Invalid params: run_id required")
        commit = bool(params.get("commit", False))
        gate_body = {k: v for k, v in params.items() if k not in ("run_id", "commit")}
        req = GateEvaluateRequestV1.model_validate(gate_body)
        out = service.evaluate_gate(
            tenant_id,
            run_id,
            req.trustor_org_id,
            req.trustee_org_id,
            req.trustor_agent_id,
            req.trustee_agent_id,
            req.sensitivity,
            commit,
        )
        return _rpc_result(rpc_id, out.model_dump())

    if method == "tasks/get":
        run_id = str(params.get("id") or params.get("run_id", ""))
        if not run_id:
            return _rpc_err(rpc_id, -32602, "Invalid params: id (run_id) required")
        snap = service.get_run_snapshot(tenant_id, run_id)
        return _rpc_result(
            rpc_id,
            {"id": run_id, "status": "completed", "artifacts": [snap]},
        )

    if method == "tasks/send":
        meta = params.get("metadata") or {}
        skill = str(meta.get("skillId") or meta.get("skill") or "")
        msg = params.get("message") or {}
        parts = msg.get("parts") or []
        data: dict[str, Any] = {}
        if parts and isinstance(parts[0], dict):
            data = parts[0].get("data") or {}
        if skill == "trust.create_run":
            req = RunCreateRequestV1.model_validate(data)
            out = service.create_run(
                tenant_id,
                req.query_text,
                req.requesting_org_id,
                req.requesting_agent_id,
                req.sensitivity,
            )
            rid = out.run_id
            return _rpc_result(
                rpc_id,
                {
                    "id": rid,
                    "status": "completed",
                    "artifacts": [{"parts": [{"kind": "data", "data": out.model_dump()}]}],
                },
            )
        if skill == "trust.appendEvent":
            run_id = str(data.get("run_id", ""))
            req = RunEventAppendRequestV1.model_validate(
                {k: v for k, v in data.items() if k != "run_id"}
            )
            out = service.append_run_event(
                tenant_id, run_id, req.event_type, req.payload
            )
            return _rpc_result(
                rpc_id,
                {
                    "id": run_id,
                    "status": "completed",
                    "artifacts": [{"parts": [{"kind": "data", "data": out}]}],
                },
            )
        if skill == "trust.evaluateGate":
            run_id = str(data.get("run_id", ""))
            commit = bool(data.get("commit", False))
            gate_body = {
                k: v
                for k, v in data.items()
                if k not in ("run_id", "commit")
            }
            req = GateEvaluateRequestV1.model_validate(gate_body)
            out = service.evaluate_gate(
                tenant_id,
                run_id,
                req.trustor_org_id,
                req.trustee_org_id,
                req.trustor_agent_id,
                req.trustee_agent_id,
                req.sensitivity,
                commit,
            )
            return _rpc_result(
                rpc_id,
                {
                    "id": run_id,
                    "status": "completed",
                    "artifacts": [
                        {"parts": [{"kind": "data", "data": out.model_dump()}]}
                    ],
                },
            )
        return _rpc_err(
            rpc_id,
            -32601,
            "Method not found",
            {"method": method, "hint": "unknown tasks/send skillId"},
        )

    return _rpc_err(
        rpc_id,
        -32601,
        "Method not found",
        {"method": method},
    )
