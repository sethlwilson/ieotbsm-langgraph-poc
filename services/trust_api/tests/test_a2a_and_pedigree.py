"""A2A Agent Card, JSON-RPC, JWKS, and pedigree chain integration."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient

from trust_api.config import Settings
from trust_api.main import app
from ieotbsm_core.pedigree_chain import verify_link_digest


def _b64url_pad(s: str) -> str:
    return s + "=" * ((4 - len(s) % 4) % 4)


def _jwk_x_to_public_key(x: str) -> Ed25519PublicKey:
    raw = base64.urlsafe_b64decode(_b64url_pad(x))
    return Ed25519PublicKey.from_public_bytes(raw)


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_url = f"sqlite:///{tmp_path / 't.db'}"
    test_settings = Settings(
        database_url=db_url,
        api_key="k",
        default_tenant="t1",
        signing_key_id="test-key",
        public_base_url="http://test.example",
    )
    import trust_api.config as config_mod

    monkeypatch.setattr(config_mod, "settings", test_settings)

    with TestClient(app) as c:
        yield c, test_settings


def test_agent_card_required_fields_and_etag(client):
    c, _ = client
    r1 = c.get("/.well-known/agent-card.json")
    r2 = c.get("/card")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    body = r1.json()
    for key in (
        "name",
        "description",
        "version",
        "protocolVersion",
        "supportedInterfaces",
        "skills",
        "securitySchemes",
        "security",
    ):
        assert key in body
    assert r1.headers.get("ETag")
    assert r1.headers.get("Cache-Control")
    r3 = c.get("/.well-known/agent-card.json")
    assert r1.headers["ETag"] == r3.headers["ETag"]


def test_jwks_okp(client):
    c, _ = client
    r = c.get("/.well-known/jwks.json")
    assert r.status_code == 200
    keys = r.json()["keys"]
    assert len(keys) >= 1
    assert keys[0]["kty"] == "OKP"
    assert keys[0]["crv"] == "Ed25519"
    assert keys[0]["kid"] == "test-key"


def test_a2a_version_required(client):
    c, _ = client
    r = c.post(
        "/v2/a2a",
        json={"jsonrpc": "2.0", "id": 1, "method": "trust/getRun", "params": {}},
        headers={"X-API-Key": "k", "X-Tenant-ID": "t1"},
    )
    assert r.status_code == 200
    err = r.json()["error"]
    assert err["code"] == -32001


def test_jsonrpc_trust_create_and_chain(client):
    c, _ = client
    h = {
        "X-API-Key": "k",
        "X-Tenant-ID": "t1",
        "A2A-Version": "1.0",
        "Content-Type": "application/json",
    }
    r0 = c.post(
        "/v2/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "a",
            "method": "trust/createRun",
            "params": {
                "schema_version": 1,
                "query_text": "q",
                "requesting_org_id": "O_A",
                "requesting_agent_id": "agent1",
                "sensitivity": 1,
            },
        },
        headers=h,
    )
    assert r0.status_code == 200
    res = r0.json()["result"]
    run_id = res["run_id"]

    ev = {
        "schema_version": 1,
        "event_type": "pedigree_sign",
        "payload": {
            "agent_id": "a",
            "org_id": "O_A",
            "role": "org_orchestrator",
            "action": "step1",
        },
    }
    r1 = c.post(
        "/v2/a2a",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "trust/appendEvent",
            "params": {"run_id": run_id, **ev},
        },
        headers=h,
    )
    assert r1.status_code == 200
    assert r1.json()["result"]["chain_seq"] == 1

    r1b = c.post(
        "/v1/runs/{}/events".format(run_id),
        json=ev,
        headers=h,
    )
    assert r1b.status_code == 200
    assert r1b.json()["chain_seq"] == 2

    jw = c.get("/.well-known/jwks.json").json()["keys"][0]
    pk = _jwk_x_to_public_key(jw["x"])

    ch = c.get(f"/v1/runs/{run_id}/pedigree/chain", headers=h).json()
    assert ch["seq"] == 2
    ld = base64.standard_b64decode(ch["root_b64"])
    sig = base64.standard_b64decode(ch["signature_b64"])
    verify_link_digest(pk, sig, ld)


def test_tasks_send_create_run(client):
    c, _ = client
    h = {
        "X-API-Key": "k",
        "X-Tenant-ID": "t1",
        "A2A-Version": "1.0.0",
    }
    r = c.post(
        "/v2/a2a",
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tasks/send",
            "params": {
                "metadata": {"skillId": "trust.create_run"},
                "message": {
                    "parts": [
                        {
                            "kind": "data",
                            "data": {
                                "schema_version": 1,
                                "query_text": "",
                                "requesting_org_id": "O_B",
                                "requesting_agent_id": "",
                                "sensitivity": 1,
                            },
                        }
                    ]
                },
            },
        },
        headers=h,
    )
    assert r.status_code == 200
    out = r.json()["result"]
    assert "id" in out
    assert out["status"] == "completed"


def test_tasks_get_run(client):
    c, _ = client
    h = {
        "X-API-Key": "k",
        "X-Tenant-ID": "t1",
        "A2A-Version": "1.0",
    }
    cr = c.post(
        "/v1/runs",
        json={
            "schema_version": 1,
            "requesting_org_id": "O_C",
            "sensitivity": 1,
        },
        headers=h,
    )
    run_id = cr.json()["run_id"]
    r = c.post(
        "/v2/a2a",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tasks/get",
            "params": {"id": run_id},
        },
        headers=h,
    )
    assert r.status_code == 200
    art = r.json()["result"]["artifacts"][0]
    assert "provenance" in art
    assert "pedigree_chain" in art
