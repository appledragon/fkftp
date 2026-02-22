"""FKFTP - FTP Server with Web Management UI."""

import json
import logging
import os
import string
import sys
import threading
import time
import webbrowser

from flask import Flask, render_template, request, jsonify

from hash_password import hash_password
from server import setup_server, load_config, validate_directories
from filesystem import USER_DIR_MAP

# --- Path resolution (works both for dev and PyInstaller frozen exe) ---
if getattr(sys, "frozen", False):
    _BUNDLE_DIR = sys._MEIPASS
    _CONFIG_DIR = os.path.dirname(sys.executable)
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    _CONFIG_DIR = _BUNDLE_DIR

CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")

app = Flask(__name__, template_folder=os.path.join(_BUNDLE_DIR, "templates"))
app.secret_key = os.urandom(24)

logger = logging.getLogger("fkftp")

# --- FTP server lifecycle ---
_ftp_server = None
_ftp_thread = None
_ftp_lock = threading.Lock()

_DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 2121,
    "passive_ports": [60000, 65535],
    "max_connections": 256,
    "max_connections_per_ip": 5,
    "banner": "Welcome to FKFTP Server.",
    "web_port": 8080,
    "auto_start": False,
    "users": [],
}


def _ensure_config():
    if not os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)


# -------- Pages --------

@app.route("/")
def index():
    return render_template("index.html")


# -------- Config API --------

@app.route("/api/config", methods=["GET"])
def api_get_config():
    config = load_config(CONFIG_PATH)
    # Strip password hashes — only tell the frontend whether a password exists
    for user in config.get("users", []):
        user["has_password"] = bool(user.get("password_hash", ""))
        user.pop("password_hash", None)
    return jsonify(config)


@app.route("/api/config", methods=["POST"])
def api_save_config():
    new_config = request.get_json()
    if not new_config:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    # Preserve existing password hashes unless a new password is provided
    try:
        old_config = load_config(CONFIG_PATH)
    except Exception:
        old_config = {"users": []}

    old_users = {u["username"]: u for u in old_config.get("users", [])}

    for user in new_config.get("users", []):
        new_pw = user.pop("new_password", None)
        user.pop("has_password", None)
        if new_pw:
            user["password_hash"] = hash_password(new_pw)
        elif user.get("username") in old_users:
            user["password_hash"] = old_users[user["username"]].get(
                "password_hash", ""
            )
        else:
            user.setdefault("password_hash", "")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(new_config, f, indent=4, ensure_ascii=False)

    return jsonify({"status": "ok", "message": "Configuration saved"})


# -------- Server control API --------

@app.route("/api/server/start", methods=["POST"])
def api_start():
    global _ftp_server, _ftp_thread
    with _ftp_lock:
        if _ftp_thread and _ftp_thread.is_alive():
            return jsonify({"status": "error", "message": "FTP server is already running"})
        try:
            config = load_config(CONFIG_PATH)
            if not config.get("users"):
                return jsonify({"status": "error", "message": "No users configured"})
            USER_DIR_MAP.clear()
            last_err = None
            for _attempt in range(5):
                try:
                    _ftp_server = setup_server(config)
                    break
                except OSError as e:
                    last_err = e
                    if e.errno in (48, 98, 10048):  # EADDRINUSE on macOS/Linux/Windows
                        time.sleep(1)
                    else:
                        raise
            else:
                raise last_err
            _ftp_thread = threading.Thread(
                target=_ftp_server.serve_forever, daemon=True
            )
            _ftp_thread.start()
            port = config.get("port", 2121)
            return jsonify(
                {"status": "ok", "message": f"FTP server started (port {port})"}
            )
        except Exception as e:
            logger.exception("Failed to start FTP server")
            return jsonify({"status": "error", "message": str(e)})


@app.route("/api/server/stop", methods=["POST"])
def api_stop():
    global _ftp_server, _ftp_thread
    with _ftp_lock:
        if not _ftp_thread or not _ftp_thread.is_alive():
            return jsonify({"status": "error", "message": "FTP server is not running"})
        try:
            _ftp_server._serving = False
            _ftp_server.close_all()
            _ftp_thread.join(timeout=10)
            if _ftp_thread.is_alive():
                return jsonify({"status": "error", "message": "Server did not stop in time"})
            _ftp_server = None
            _ftp_thread = None
            return jsonify({"status": "ok", "message": "FTP server stopped"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})


@app.route("/api/server/status")
def api_status():
    running = _ftp_thread is not None and _ftp_thread.is_alive()
    return jsonify({"running": running})


# -------- Firewall API (Windows only) --------

def _run_netsh(cmd):
    """Run a netsh command and return decoded stdout/stderr safely."""
    import subprocess
    r = subprocess.run(cmd, capture_output=True, timeout=10)
    out = r.stdout.decode(errors="replace").strip()
    err = r.stderr.decode(errors="replace").strip()
    return out or err


@app.route("/api/firewall/add", methods=["POST"])
def api_firewall_add():
    if os.name != "nt":
        return jsonify({"status": "error", "message": "Windows only"})
    config = load_config(CONFIG_PATH)
    port = config.get("port", 2121)
    pp = config.get("passive_ports", [60000, 65535])
    results = []
    cmds = [
        ["netsh", "advfirewall", "firewall", "add", "rule",
         f"name=FKFTP Server (Port {port})", "dir=in", "action=allow",
         "protocol=TCP", f"localport={port}"],
        ["netsh", "advfirewall", "firewall", "add", "rule",
         f"name=FKFTP Passive ({pp[0]}-{pp[1]})", "dir=in", "action=allow",
         "protocol=TCP", f"localport={pp[0]}-{pp[1]}"],
    ]
    for cmd in cmds:
        try:
            results.append(_run_netsh(cmd))
        except Exception as e:
            results.append(str(e))
    ok = all("Ok" in r or "already exists" in r.lower() for r in results)
    msg = "Firewall rules added" if ok else "Result: " + " | ".join(results)
    return jsonify({"status": "ok" if ok else "error", "message": msg, "details": results})


@app.route("/api/firewall/remove", methods=["POST"])
def api_firewall_remove():
    if os.name != "nt":
        return jsonify({"status": "error", "message": "Windows only"})
    config = load_config(CONFIG_PATH)
    port = config.get("port", 2121)
    pp = config.get("passive_ports", [60000, 65535])
    results = []
    rule_names = [
        f"FKFTP Server (Port {port})",
        f"FKFTP Passive ({pp[0]}-{pp[1]})",
    ]
    for name in rule_names:
        try:
            results.append(_run_netsh(
                ["netsh", "advfirewall", "firewall", "delete", "rule",
                 f"name={name}"]))
        except Exception as e:
            results.append(str(e))
    return jsonify({"status": "ok", "message": "Firewall rules removed", "details": results})


@app.route("/api/firewall/status")
def api_firewall_status():
    if os.name != "nt":
        return jsonify({"status": "error", "message": "Windows only"})
    try:
        out_server = _run_netsh(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=FKFTP Server"])
        out_passive = _run_netsh(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=FKFTP Passive"])
        found_server = "FKFTP Server" in out_server
        found_passive = "FKFTP Passive" in out_passive
        # Also check port-specific names
        config = load_config(CONFIG_PATH)
        port = config.get("port", 2121)
        out_port = _run_netsh(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             f"name=FKFTP Server (Port {port})"])
        found_server = found_server or "FKFTP Server" in out_port
        return jsonify({
            "server_rule": found_server,
            "passive_rule": found_passive,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# -------- Windows Service API --------

@app.route("/api/service/install", methods=["POST"])
def api_service_install():
    if os.name != "nt":
        return jsonify({"status": "error", "message": "Windows only"})
    from service import install_service
    ok = install_service()
    return jsonify({
        "status": "ok" if ok else "error",
        "message": "Windows service installed (auto-start enabled)" if ok else "Installation failed, please run as administrator",
    })


@app.route("/api/service/uninstall", methods=["POST"])
def api_service_uninstall():
    if os.name != "nt":
        return jsonify({"status": "error", "message": "Windows only"})
    from service import uninstall_service
    ok = uninstall_service()
    return jsonify({
        "status": "ok" if ok else "error",
        "message": "Windows service uninstalled" if ok else "Uninstall failed, please run as administrator",
    })


@app.route("/api/service/start", methods=["POST"])
def api_service_start():
    if os.name != "nt":
        return jsonify({"status": "error", "message": "Windows only"})
    from service import start_service
    ok = start_service()
    return jsonify({
        "status": "ok" if ok else "error",
        "message": "Service started" if ok else "Start failed",
    })


@app.route("/api/service/stop", methods=["POST"])
def api_service_stop():
    if os.name != "nt":
        return jsonify({"status": "error", "message": "Windows only"})
    from service import stop_service
    ok = stop_service()
    return jsonify({
        "status": "ok" if ok else "error",
        "message": "Service stopped" if ok else "Stop failed",
    })


@app.route("/api/service/status")
def api_service_status():
    if os.name != "nt":
        return jsonify({"status": "not_installed"})
    from service import query_service
    return jsonify({"status": query_service()})


# -------- Platform info API --------

@app.route("/api/platform")
def api_platform():
    return jsonify({"os": os.name})


# -------- Filesystem browsing API --------

@app.route("/api/drives")
def api_drives():
    drives = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
    else:
        drives = ["/"]
    return jsonify(drives)


@app.route("/api/browse")
def api_browse():
    path = request.args.get("path", "")
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400

    dirs = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if entry.is_dir():
                try:
                    dirs.append({"name": entry.name, "path": entry.path})
                except Exception:
                    pass
    except PermissionError:
        pass
    return jsonify(
        {
            "current": os.path.normpath(path),
            "parent": os.path.dirname(os.path.normpath(path)),
            "dirs": dirs,
        }
    )


# -------- Main --------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    _ensure_config()
    try:
        config = load_config(CONFIG_PATH)
    except Exception as e:
        logger.warning("Config file corrupt, using defaults: %s", e)
        config = _DEFAULT_CONFIG
    web_port = config.get("web_port", 8080)

    # Auto-start FTP server if configured
    if config.get("auto_start") and config.get("users"):
        try:
            global _ftp_server, _ftp_thread
            USER_DIR_MAP.clear()
            _ftp_server = setup_server(config)
            _ftp_thread = threading.Thread(
                target=_ftp_server.serve_forever, daemon=True
            )
            _ftp_thread.start()
            logger.info("FTP server auto-started on port %d", config.get("port", 2121))
        except Exception:
            logger.exception("Auto-start failed")

    url = f"http://127.0.0.1:{web_port}"
    threading.Timer(1.5, webbrowser.open, args=[url]).start()
    logger.info("FKFTP management UI: %s", url)

    app.run(host="127.0.0.1", port=web_port, debug=False, use_reloader=False)


if __name__ == "__main__":
    # Windows Service support (Windows only)
    if os.name == "nt" and len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "--service":
            from service import (
                install_service, uninstall_service,
                start_service, stop_service, query_service,
            )
            action = sys.argv[2].lower() if len(sys.argv) > 2 else "help"
            if action == "install":
                install_service()
            elif action == "uninstall":
                uninstall_service()
            elif action == "start":
                start_service()
            elif action == "stop":
                stop_service()
            elif action == "status":
                status = query_service()
                print(f"Service status: {status}")
            else:
                print("Usage: fkftp --service [install|uninstall|start|stop|status]")
            sys.exit(0)
        elif cmd == "--run-service":
            from service import run_as_service
            run_as_service()
            sys.exit(0)
    main()
