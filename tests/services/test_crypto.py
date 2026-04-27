"""Tests for services/crypto.py — Fernet encryption helpers."""

import base64

import pytest

from wodplanner.services.crypto import decrypt, derive_fernet_key, encrypt, get_enc_key


class TestDeriveKey:
    def test_returns_valid_fernet_key(self):
        key = derive_fernet_key("mysecret")
        # Fernet keys are 32 bytes encoded as base64url — 44 chars
        assert len(key) == 44
        raw = base64.urlsafe_b64decode(key)
        assert len(raw) == 32

    def test_deterministic(self):
        assert derive_fernet_key("abc") == derive_fernet_key("abc")

    def test_different_secrets_give_different_keys(self):
        assert derive_fernet_key("secret1") != derive_fernet_key("secret2")


class TestGetEncKey:
    def test_derives_from_secret_when_no_explicit_key(self):
        key = get_enc_key(None, "mysecret")
        assert key == derive_fernet_key("mysecret")

    def test_uses_explicit_key_when_provided(self):
        raw = b"a" * 32
        explicit = base64.urlsafe_b64encode(raw).decode()
        key = get_enc_key(explicit, "ignored_secret")
        assert len(key) == 44

    def test_explicit_key_shorter_than_32_bytes_is_padded(self):
        raw = b"short"
        explicit = base64.urlsafe_b64encode(raw).decode()
        key = get_enc_key(explicit, "ignored_secret")
        assert len(key) == 44


class TestEncryptDecrypt:
    def test_round_trip(self):
        key = derive_fernet_key("testkey")
        plaintext = "hello world"
        ciphertext = encrypt(plaintext, key)
        assert ciphertext != plaintext
        assert decrypt(ciphertext, key) == plaintext

    def test_different_plaintext_gives_different_ciphertext(self):
        key = derive_fernet_key("testkey")
        assert encrypt("foo", key) != encrypt("bar", key)

    def test_encrypt_produces_string(self):
        key = derive_fernet_key("testkey")
        result = encrypt("data", key)
        assert isinstance(result, str)

    def test_decrypt_with_wrong_key_raises(self):
        key1 = derive_fernet_key("key1")
        key2 = derive_fernet_key("key2")
        ciphertext = encrypt("secret", key1)
        with pytest.raises(Exception):
            decrypt(ciphertext, key2)

    def test_encrypt_empty_string(self):
        key = derive_fernet_key("testkey")
        assert decrypt(encrypt("", key), key) == ""
