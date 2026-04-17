"""Append-only pedigree chain: RFC 8785 canonical payloads, SHA-256 links, Ed25519 signatures."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# First link uses this constant as prev_root (32 bytes).
GENESIS_ROOT = hashlib.sha256(b"ieotbsm_pedigree_genesis_v1").digest()

# Domain separation for the signed link record.
LINK_SCHEMA_ID = "ieotbsm_pedigree_link_v1"


def payload_digest(payload: dict[str, Any]) -> bytes:
    """SHA-256 over RFC 8785 canonical encoding of the event payload."""
    body = rfc8785.dumps(payload)
    return hashlib.sha256(body).digest()


def link_digest(
    *,
    run_id: str,
    tenant_id: str,
    seq: int,
    event_type: str,
    payload_hash: bytes,
    prev_root: bytes,
) -> bytes:
    """Digest of one chain link (32 bytes). Signed by the trust service."""
    record = {
        "schema": LINK_SCHEMA_ID,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "seq": seq,
        "event_type": event_type,
        "payload_digest": payload_hash.hex(),
        "prev_root": prev_root.hex(),
    }
    body = rfc8785.dumps(record)
    return hashlib.sha256(body).digest()


def sign_link_digest(private_key: Ed25519PrivateKey, link_digest_bytes: bytes) -> bytes:
    """Ed25519 signature over the 32-byte link digest."""
    return private_key.sign(link_digest_bytes)


def verify_link_digest(
    public_key: Ed25519PublicKey,
    signature: bytes,
    link_digest_bytes: bytes,
) -> None:
    """Raises cryptography.exceptions.InvalidSignature if invalid."""
    public_key.verify(signature, link_digest_bytes)


def prev_root_from_row(chain_seq: int, chain_root_b64: str | None) -> bytes:
    if chain_seq <= 0 or not chain_root_b64:
        return GENESIS_ROOT
    return base64.standard_b64decode(chain_root_b64.encode("ascii"))
