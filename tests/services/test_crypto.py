"""Tests for services/crypto.py — Fernet encryption helpers."""

import pytest

from wodplanner.services.crypto import decrypt, encrypt


def _make_key(key: str) -> bytes:
    import base64
    import hashlib
    raw = hashlib.sha256(key.encode()).digest()
    return base64.urlsafe_b64encode(raw)


class TestEncryptDecrypt:
    def test_round_trip(self):
        key = _make_key("testkey")
        plaintext = "hello world"
        ciphertext = encrypt(plaintext, key)
        assert ciphertext != plaintext
        assert decrypt(ciphertext, key) == plaintext

    def test_different_plaintext_gives_different_ciphertext(self):
        key = _make_key("testkey")
        assert encrypt("foo", key) != encrypt("bar", key)

    def test_encrypt_produces_string(self):
        key = _make_key("testkey")
        result = encrypt("data", key)
        assert isinstance(result, str)

    def test_decrypt_with_wrong_key_raises(self):
        key1 = _make_key("key1")
        key2 = _make_key("key2")
        ciphertext = encrypt("secret", key1)
        with pytest.raises(Exception):
            decrypt(ciphertext, key2)

    def test_encrypt_empty_string(self):
        key = _make_key("testkey")
        assert decrypt(encrypt("", key), key) == ""