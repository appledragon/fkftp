"""Tests for hash_password module."""

import hashlib
from hash_password import hash_password


class TestHashPassword:
    def test_returns_salt_dollar_hash_format(self):
        result = hash_password("test123")
        assert "$" in result
        parts = result.split("$", 1)
        assert len(parts) == 2

    def test_salt_is_32_hex_chars(self):
        result = hash_password("pw")
        salt = result.split("$")[0]
        assert len(salt) == 32
        int(salt, 16)  # Should not raise

    def test_hash_is_sha256_hex(self):
        result = hash_password("hello")
        h = result.split("$")[1]
        assert len(h) == 64
        int(h, 16)

    def test_hash_is_correct(self):
        result = hash_password("mypassword")
        salt, stored_hash = result.split("$", 1)
        expected = hashlib.sha256((salt + "mypassword").encode("utf-8")).hexdigest()
        assert stored_hash == expected

    def test_different_calls_produce_different_salts(self):
        r1 = hash_password("same")
        r2 = hash_password("same")
        assert r1 != r2  # Different salts

    def test_empty_password(self):
        result = hash_password("")
        salt, h = result.split("$", 1)
        expected = hashlib.sha256((salt + "").encode("utf-8")).hexdigest()
        assert h == expected

    def test_unicode_password(self):
        result = hash_password("密码测试")
        salt, h = result.split("$", 1)
        expected = hashlib.sha256((salt + "密码测试").encode("utf-8")).hexdigest()
        assert h == expected
