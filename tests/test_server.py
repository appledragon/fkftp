"""Tests for HashedAuthorizer and server utilities."""

import hashlib
import json
import os
import tempfile

import pytest
from unittest.mock import patch

from server import HashedAuthorizer, load_config, validate_directories
from filesystem import USER_DIR_MAP


class TestHashedAuthorizer:
    def setup_method(self):
        self.auth = HashedAuthorizer()
        USER_DIR_MAP.clear()

    def _make_hash(self, password, salt="abcd1234"):
        h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return f"{salt}${h}"

    def test_add_user(self):
        with tempfile.TemporaryDirectory() as d:
            self.auth.add_user("alice", self._make_hash("pw"), d)
            assert self.auth.has_user("alice")

    def test_add_duplicate_user_raises(self):
        with tempfile.TemporaryDirectory() as d:
            self.auth.add_user("alice", self._make_hash("pw"), d)
            with pytest.raises(Exception):
                self.auth.add_user("alice", self._make_hash("pw2"), d)

    def test_validate_correct_password(self):
        with tempfile.TemporaryDirectory() as d:
            pw_hash = self._make_hash("secret")
            self.auth.add_user("bob", pw_hash, d)
            # Should not raise
            self.auth.validate_authentication("bob", "secret", None)

    def test_validate_wrong_password_raises(self):
        from pyftpdlib.exceptions import AuthenticationFailed
        with tempfile.TemporaryDirectory() as d:
            pw_hash = self._make_hash("secret")
            self.auth.add_user("bob", pw_hash, d)
            with pytest.raises(AuthenticationFailed):
                self.auth.validate_authentication("bob", "wrong", None)

    def test_validate_nonexistent_user_raises(self):
        from pyftpdlib.exceptions import AuthenticationFailed
        with pytest.raises(AuthenticationFailed):
            self.auth.validate_authentication("nobody", "pw", None)

    def test_validate_empty_hash_raises(self):
        from pyftpdlib.exceptions import AuthenticationFailed
        with tempfile.TemporaryDirectory() as d:
            self.auth.add_user("empty", "", d)
            with pytest.raises(AuthenticationFailed, match="not configured"):
                self.auth.validate_authentication("empty", "pw", None)

    def test_validate_invalid_hash_format_raises(self):
        from pyftpdlib.exceptions import AuthenticationFailed
        with tempfile.TemporaryDirectory() as d:
            self.auth.add_user("bad", "nodoallarsign", d)
            with pytest.raises(AuthenticationFailed, match="Invalid password hash"):
                self.auth.validate_authentication("bad", "pw", None)

    def test_has_perm_basic(self):
        with tempfile.TemporaryDirectory() as d:
            self.auth.add_user("u", self._make_hash("pw"), d, perm="elr")
            assert self.auth.has_perm("u", "e")
            assert self.auth.has_perm("u", "l")
            assert self.auth.has_perm("u", "r")
            assert not self.auth.has_perm("u", "w")

    def test_has_perm_virtual_root(self):
        with tempfile.TemporaryDirectory() as d:
            self.auth.add_user("u", self._make_hash("pw"), d, perm="elr")
            assert self.auth.has_perm("u", "e", "/")
            assert not self.auth.has_perm("u", "w", "/")

    def test_has_perm_mounted_directory(self):
        with tempfile.TemporaryDirectory() as d:
            USER_DIR_MAP["u"] = {"docs": d}
            self.auth.add_user("u", self._make_hash("pw"), d, perm="elrw")
            assert self.auth.has_perm("u", "w", d)
            subpath = os.path.join(d, "subdir")
            assert self.auth.has_perm("u", "w", subpath)

    def test_has_perm_unmounted_path(self):
        with tempfile.TemporaryDirectory() as d:
            USER_DIR_MAP["u"] = {"docs": d}
            self.auth.add_user("u", self._make_hash("pw"), d, perm="elrw")
            assert not self.auth.has_perm("u", "w", "/some/random/path")


class TestLoadConfig:
    def test_load_valid_config(self):
        data = {"host": "0.0.0.0", "port": 2121, "users": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            path = f.name
        try:
            result = load_config(path)
            assert result["host"] == "0.0.0.0"
            assert result["port"] == 2121
        finally:
            os.unlink(path)

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.json")


class TestValidateDirectories:
    def test_creates_missing_directory(self):
        with tempfile.TemporaryDirectory() as d:
            new_dir = os.path.join(d, "newdir")
            assert not os.path.isdir(new_dir)
            validate_directories([{"directories": {"mount": new_dir}}])
            assert os.path.isdir(new_dir)

    def test_existing_directory_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            validate_directories([{"directories": {"mount": d}}])
            assert os.path.isdir(d)
