"""AES-256-GCM encryption helpers for DB-stored connector credentials."""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key() -> bytes:
    raw = os.environ.get("CORVIN_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise ValueError(
            "CORVIN_ENCRYPTION_KEY env var not set — required for db_encrypted credentials"
        )
    return base64.b64decode(raw)


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext with AES-256-GCM. Returns base64(nonce + ciphertext)."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt base64(nonce + ciphertext) produced by encrypt()."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(ciphertext)
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()
