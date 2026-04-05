"""
IEOTBSM live simulation dashboard (FastAPI + SSE).

Run from repo root:
  pip install -r requirements.txt
  uvicorn dashboard_app:app --reload --host 127.0.0.1 --port 8765

Open http://127.0.0.1:8765/ (sets session cookie). Static assets under /static/.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from network import IEOTBSMAgenticNetwork
from run_poc import DEMO_QUERIES
from trust_engine import SensitivityLevel

SESSION_COOKIE = "ieotbsm_sid"
sessions: dict[str, IEOTBSMAgenticNetwork] = {}

app = FastAPI(title="IEOTBSM Dashboard")

STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _get_or_create_session(request: Request, response: Response | None) -> tuple[str, IEOTBSMAgenticNetwork]:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid or sid not in sessions:
        sid = str(uuid.uuid4())
        sessions[sid] = IEOTBSMAgenticNetwork()
        if response is not None:
            response.set_cookie(
                key=SESSION_COOKIE,
                value=sid,
                httponly=True,
                samesite="lax",
                max_age=86400 * 7,
            )
    return sid, sessions[sid]


def _parse_sensitivity(raw: str) -> SensitivityLevel:
    raw = raw.strip()
    if raw.isdigit():
        return SensitivityLevel(int(raw))
    try:
        return SensitivityLevel[raw.upper()]
    except KeyError as e:
        raise HTTPException(400, f"Invalid sensitivity: {raw}") from e


def _state_payload(net: IEOTBSMAgenticNetwork) -> dict[str, Any]:
    tm = net.get_trust_matrix()
    return {
        "cycle": net.cycle,
        "human_review_queue_size": len(net.human_review_queue),
        "trust_matrix": tm,
        "orgs": [{"id": oid, "name": net.org_names[oid]} for oid in tm["org_ids"]],
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@app.get("/")
def index(request: Request, response: Response):
    _get_or_create_session(request, response)
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(500, "Missing static/index.html — add dashboard static files.")
    return FileResponse(index_path)


@app.get("/api/state")
def api_state(request: Request, response: Response):
    _, net = _get_or_create_session(request, response)
    return _state_payload(net)


@app.get("/api/demo-scenarios")
def api_demo_scenarios() -> list[dict[str, Any]]:
    """Catalog of scripted demo scenes for the dashboard."""
    out: list[dict[str, Any]] = []
    for i, d in enumerate(DEMO_QUERIES):
        out.append(
            {
                "id": d.get("id", f"scenario_{i}"),
                "title": d.get("title", f"Scenario {i + 1}"),
                "tagline": d.get("tagline", ""),
                "description": d.get("description", ""),
                "requesting_org_id": d["requesting_org"],
                "sensitivity": d["sensitivity"].name,
                "query": d["query"],
            }
        )
    return out


@app.post("/api/session/reset")
def api_reset_session(request: Request, response: Response):
    sid, _ = _get_or_create_session(request, response)
    sessions[sid] = IEOTBSMAgenticNetwork()
    return {"ok": True, **_state_payload(sessions[sid])}


@app.get("/api/simulation/stream")
def api_simulation_stream(
    request: Request,
    demo: int = Query(0, ge=0, le=1),
    scenario_id: str | None = Query(None),
    query: str | None = Query(None),
    requesting_org_id: str | None = Query(None),
    sensitivity: str = Query("INTERNAL"),
    throttle_ms: int = Query(0, ge=0, le=5000),
):
    _, net = _get_or_create_session(request, None)

    def event_iter():
        if demo == 1:
            yield _sse(
                {
                    "type": "demo_started",
                    "count": len(DEMO_QUERIES),
                    "subtitle": "Six-scene trust arc: from coalition briefings to RESTRICTED vault access.",
                }
            )
            for i, item in enumerate(DEMO_QUERIES):
                yield _sse(
                    {
                        "type": "demo_query",
                        "index": i,
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "tagline": item.get("tagline"),
                        "description": item.get("description", ""),
                    }
                )
                for ev in net.iter_query_simulation_events(
                    item["query"],
                    item["requesting_org"],
                    item["sensitivity"],
                    throttle_ms=throttle_ms,
                    description=item.get("title") or item.get("description"),
                ):
                    yield _sse(ev)
            yield _sse({"type": "demo_complete"})
            yield _sse({"type": "stream_end"})
            return

        if scenario_id:
            item = next(
                (d for d in DEMO_QUERIES if d.get("id") == scenario_id),
                None,
            )
            if item is None:
                yield _sse(
                    {
                        "type": "error",
                        "message": f"Unknown scenario_id: {scenario_id}",
                    }
                )
                yield _sse({"type": "stream_end"})
                return
            yield _sse(
                {
                    "type": "scenario_started",
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "tagline": item.get("tagline"),
                }
            )
            for ev in net.iter_query_simulation_events(
                item["query"],
                item["requesting_org"],
                item["sensitivity"],
                throttle_ms=throttle_ms,
                description=item.get("title") or item.get("description"),
            ):
                yield _sse(ev)
            yield _sse({"type": "stream_end"})
            return

        if not query or not requesting_org_id:
            yield _sse(
                {
                    "type": "error",
                    "message": "Missing query or requesting_org_id (or use demo=1)",
                }
            )
            yield _sse({"type": "stream_end"})
            return

        sens = _parse_sensitivity(sensitivity)
        for ev in net.iter_query_simulation_events(
            query,
            requesting_org_id,
            sens,
            throttle_ms=throttle_ms,
        ):
            yield _sse(ev)
        yield _sse({"type": "stream_end"})

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
