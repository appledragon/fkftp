"""Tests for Flask API endpoints."""

import json
import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from hash_password import hash_password

# Patch CONFIG_PATH before importing app
_tmpdir = tempfile.mkdtemp()
_config_path = os.path.join(_tmpdir, "config.json")

_test_config = {
    "host": "0.0.0.0",
    "port": 2121,
    "passive_ports": [60000, 65535],
    "max_connections": 256,
    "max_connections_per_ip": 5,
    "banner": "Test",
    "web_port": 8080,
    "auto_start": False,
    "users": [
        {
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "permissions": "elradfmw",
            "directories": {},
        }
    ],
}

with open(_config_path, "w", encoding="utf-8") as _f:
    json.dump(_test_config, _f)

# Patch before import
import app as app_module
app_module.CONFIG_PATH = _config_path


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config file before each test."""
    with open(_config_path, "w", encoding="utf-8") as f:
        json.dump(_test_config, f)
    yield


class TestIndexPage:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"FKFTP" in resp.data


class TestConfigAPI:
    def test_get_config(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["port"] == 2121
        assert data["users"][0]["username"] == "admin"

    def test_get_config_strips_password_hash(self, client):
        resp = client.get("/api/config")
        data = resp.get_json()
        user = data["users"][0]
        assert "password_hash" not in user
        assert user["has_password"] is True

    def test_save_config(self, client):
        new_cfg = {
            "host": "0.0.0.0",
            "port": 3000,
            "passive_ports": [60000, 65535],
            "max_connections": 100,
            "max_connections_per_ip": 3,
            "banner": "Hello",
            "web_port": 9090,
            "auto_start": False,
            "users": [],
        }
        resp = client.post("/api/config", json=new_cfg)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

        # Verify saved
        resp2 = client.get("/api/config")
        saved = resp2.get_json()
        assert saved["port"] == 3000

    def test_save_config_with_new_password(self, client):
        new_cfg = {
            "host": "0.0.0.0",
            "port": 2121,
            "passive_ports": [60000, 65535],
            "max_connections": 256,
            "max_connections_per_ip": 5,
            "banner": "Test",
            "web_port": 8080,
            "auto_start": False,
            "users": [
                {
                    "username": "newuser",
                    "new_password": "newpass",
                    "permissions": "elr",
                    "directories": {},
                }
            ],
        }
        resp = client.post("/api/config", json=new_cfg)
        assert resp.get_json()["status"] == "ok"

        # Re-read raw config to verify hash was stored
        with open(_config_path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "$" in raw["users"][0]["password_hash"]

    def test_save_config_preserves_existing_password(self, client):
        # Get existing hash
        with open(_config_path, encoding="utf-8") as f:
            old = json.load(f)
        old_hash = old["users"][0]["password_hash"]

        new_cfg = {
            "host": "0.0.0.0",
            "port": 2121,
            "passive_ports": [60000, 65535],
            "max_connections": 256,
            "max_connections_per_ip": 5,
            "banner": "Test",
            "web_port": 8080,
            "auto_start": False,
            "users": [
                {
                    "username": "admin",
                    "permissions": "elr",
                    "directories": {},
                }
            ],
        }
        resp = client.post("/api/config", json=new_cfg)
        assert resp.get_json()["status"] == "ok"

        with open(_config_path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["users"][0]["password_hash"] == old_hash

    def test_save_empty_body_returns_error(self, client):
        resp = client.post(
            "/api/config", data="", content_type="application/json"
        )
        assert resp.status_code == 400


class TestServerControlAPI:
    def test_status_initially_not_running(self, client):
        resp = client.get("/api/server/status")
        data = resp.get_json()
        assert data["running"] is False

    @patch.object(app_module, "_ftp_thread", None)
    @patch.object(app_module, "_ftp_server", None)
    def test_stop_when_not_running(self, client):
        resp = client.post("/api/server/stop")
        data = resp.get_json()
        assert data["status"] == "error"


class TestDrivesAPI:
    def test_drives_returns_list(self, client):
        resp = client.get("/api/drives")
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0


class TestBrowseAPI:
    def test_browse_valid_dir(self, client):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "subdir"))
            resp = client.get(f"/api/browse?path={d}")
            data = resp.get_json()
            assert "current" in data
            assert any(item["name"] == "subdir" for item in data["dirs"])

    def test_browse_invalid_path(self, client):
        resp = client.get("/api/browse?path=/nonexistent/path")
        assert resp.status_code == 400

    def test_browse_empty_path(self, client):
        resp = client.get("/api/browse?path=")
        assert resp.status_code == 400
