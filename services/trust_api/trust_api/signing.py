"""Ed25519 signing key for pedigree chain + JWKS material."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from trust_api.config import Settings


def _derive_dev_private_key(settings: Settings) -> Ed25519PrivateKey:
    """Deterministic 32-byte seed from api_key + signing_key_id (dev/tests only)."""
    seed = hashlib.sha256(
        f"{settings.api_key}:{settings.signing_key_id}".encode()
    ).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def load_signing_private_key(settings: Settings) -> Ed25519PrivateKey:
    pem = (settings.signing_private_key_pem or "").strip()
    if pem:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError(
                "TRUST_API_SIGNING_PRIVATE_KEY_PEM must be an Ed25519 private key (PKCS8 PEM)"
            )
        return key
    return _derive_dev_private_key(settings)


def public_jwk(key_id: str, private_key: Ed25519PrivateKey) -> dict[str, Any]:
    pub = private_key.public_key()
    raw = pub.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": key_id,
        "x": base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="),
        "use": "sig",
        "alg": "EdDSA",
    }


def jwks_document(settings: Settings, private_key: Ed25519PrivateKey) -> dict[str, Any]:
    return {
        "keys": [public_jwk(settings.signing_key_id, private_key)],
    }


def private_key_pem(private_key: Ed25519PrivateKey) -> str:
    return private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode()
