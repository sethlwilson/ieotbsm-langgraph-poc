"""Trust API — HTTP service for runs, gate evaluation, ledger, violations."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query

from trust_api.auth import tenant_id, verify_api_key
from trust_api.config import settings
from trust_api.db import make_session_factory
from trust_api.service import TrustApiService

_session_factory = None
_service: TrustApiService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session_factory, _service
    _session_factory = make_session_factory(settings.database_url)
    _service = TrustApiService(_session_factory)
    yield


app = FastAPI(
    title="IEOTBSM Trust API",
    version="0.1.0",
    lifespan=lifespan,
)


def get_service() -> TrustApiService:
    if _service is None:
        raise RuntimeError("service not initialized")
    return _service


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/v1/admin/seed", dependencies=[Depends(verify_api_key)])
def admin_seed(tid: str = Depends(tenant_id)):
    get_service().seed_tenant(tid)
    return {"ok": True, "tenant_id": tid}


@app.get("/v1/state", dependencies=[Depends(verify_api_key)])
def v1_state(tid: str = Depends(tenant_id)):
    return get_service().get_state(tid).model_dump()


@app.get("/v1/ledger/matrix", dependencies=[Depends(verify_api_key)])
def v1_matrix(tid: str = Depends(tenant_id)):
    return get_service().ledger_matrix(tid).model_dump()


@app.get("/v1/tenant/snapshot", dependencies=[Depends(verify_api_key)])
def v1_tenant_snapshot(tid: str = Depends(tenant_id)):
    """Full trust snapshot for syncing a local ``IEOTBSMAgenticNetwork``."""
    return get_service().export_tenant_snapshot(tid)


@app.put("/v1/tenant/snapshot", dependencies=[Depends(verify_api_key)])
def v1_put_tenant_snapshot(body: dict, tid: str = Depends(tenant_id)):
    """Replace tenant state from a snapshot (push local network to the service)."""
    get_service().replace_tenant_snapshot(tid, body)
    return {"ok": True}


@app.post("/v1/simulation/run", dependencies=[Depends(verify_api_key)])
def v1_simulation_run(body: dict, tid: str = Depends(tenant_id)):
    """Execute one simulation query; returns all events as JSON (no SSE)."""
    return {
        "events": get_service().run_simulation_events(
            tid,
            body.get("query", ""),
            body.get("requesting_org_id", ""),
            int(body.get("sensitivity", 1)),
            description=body.get("description"),
        )
    }


@app.post("/v1/runs", dependencies=[Depends(verify_api_key)])
def v1_create_run(body: dict, tid: str = Depends(tenant_id)):
    from ieotbsm_core.schemas import RunCreateRequestV1

    req = RunCreateRequestV1.model_validate(body)
    out = get_service().create_run(
        tid,
        req.query_text,
        req.requesting_org_id,
        req.requesting_agent_id,
        req.sensitivity,
    )
    return out.model_dump()


@app.post("/v1/runs/{run_id}/gate", dependencies=[Depends(verify_api_key)])
def v1_gate(
    run_id: str,
    body: dict,
    tid: str = Depends(tenant_id),
    commit: bool = Query(False),
):
    from ieotbsm_core.schemas import GateEvaluateRequestV1

    req = GateEvaluateRequestV1.model_validate(body)
    try:
        return (
            get_service()
            .evaluate_gate(
                tid,
                run_id,
                req.trustor_org_id,
                req.trustee_org_id,
                req.trustor_agent_id,
                req.trustee_agent_id,
                req.sensitivity,
                commit,
            )
            .model_dump()
        )
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/v1/runs/{run_id}/events", dependencies=[Depends(verify_api_key)])
def v1_events(run_id: str, body: dict, tid: str = Depends(tenant_id)):
    from ieotbsm_core.schemas import RunEventAppendRequestV1

    req = RunEventAppendRequestV1.model_validate(body)
    try:
        return get_service().append_run_event(
            tid, run_id, req.event_type, req.payload
        )
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.patch("/v1/violations/{violation_id}", dependencies=[Depends(verify_api_key)])
def v1_patch_violation(
    violation_id: str,
    body: dict,
    tid: str = Depends(tenant_id),
):
    from ieotbsm_core.schemas import ViolationPatchRequestV1

    req = ViolationPatchRequestV1.model_validate(body)
    try:
        return get_service().patch_violation(
            tid, violation_id, req.status, req.reviewer_notes
        )
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


def run() -> None:
    import uvicorn

    uvicorn.run(
        "trust_api.main:app",
        host="0.0.0.0",
        port=int(__import__("os").getenv("TRUST_API_PORT", "8088")),
        reload=False,
    )
