"""Fernet encryption helpers for sensitive token storage."""

import base64
import hashlib

from cryptography.fernet import Fernet


def derive_fernet_key(secret_key: str) -> bytes:
    """Derive a Fernet-compatible key from secret_key using SHA-256 + domain separation."""
    raw = hashlib.sha256(f"google-token-enc:{secret_key}".encode()).digest()
    return base64.urlsafe_b64encode(raw)


def get_enc_key(explicit_key: str | None, secret_key: str) -> bytes:
    """Return Fernet key from explicit base64url value, or derive from secret_key."""
    if explicit_key:
        raw = base64.urlsafe_b64decode(explicit_key + "==")[:32]
        raw = raw.ljust(32, b"\0")
        return base64.urlsafe_b64encode(raw)
    return derive_fernet_key(secret_key)


def encrypt(plaintext: str, key: bytes) -> str:
    return Fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: bytes) -> str:
    return Fernet(key).decrypt(ciphertext.encode()).decode()
