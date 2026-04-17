"""Vectors for pedigree chain digests and Ed25519 sign/verify."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ieotbsm_core.pedigree_chain import (
    GENESIS_ROOT,
    link_digest,
    payload_digest,
    prev_root_from_row,
    sign_link_digest,
    verify_link_digest,
)


def test_genesis_constant_length():
    assert len(GENESIS_ROOT) == 32


def test_payload_digest_stable():
    d1 = payload_digest({"b": 2, "a": 1})
    d2 = payload_digest({"a": 1, "b": 2})
    assert d1 == d2


def test_link_digest_changes_with_seq():
    ph = payload_digest({"x": 1})
    d1 = link_digest(
        run_id="r1",
        tenant_id="t1",
        seq=1,
        event_type="pedigree_sign",
        payload_hash=ph,
        prev_root=GENESIS_ROOT,
    )
    d2 = link_digest(
        run_id="r1",
        tenant_id="t1",
        seq=2,
        event_type="pedigree_sign",
        payload_hash=ph,
        prev_root=GENESIS_ROOT,
    )
    assert d1 != d2


def test_sign_verify_roundtrip():
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    ld = link_digest(
        run_id="run",
        tenant_id="tenant",
        seq=1,
        event_type="context",
        payload_hash=payload_digest({"k": "v"}),
        prev_root=GENESIS_ROOT,
    )
    sig = sign_link_digest(sk, ld)
    verify_link_digest(pk, sig, ld)


def test_verify_fails_on_tamper():
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    ld = link_digest(
        run_id="run",
        tenant_id="tenant",
        seq=1,
        event_type="custom",
        payload_hash=payload_digest({}),
        prev_root=GENESIS_ROOT,
    )
    sig = sign_link_digest(sk, ld)
    ld2 = link_digest(
        run_id="run",
        tenant_id="tenant",
        seq=1,
        event_type="custom",
        payload_hash=payload_digest({"t": True}),
        prev_root=GENESIS_ROOT,
    )
    with pytest.raises(InvalidSignature):
        verify_link_digest(pk, sig, ld2)


def test_prev_root_from_row():
    assert prev_root_from_row(0, None) == GENESIS_ROOT
    assert prev_root_from_row(0, "") == GENESIS_ROOT
    root = base64.standard_b64encode(b"\x01" * 32).decode("ascii")
    assert prev_root_from_row(1, root) == b"\x01" * 32
