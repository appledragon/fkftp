"""
FKFTP Server - Multi-drive, multi-directory FTP server.

Usage:
    python server.py                  # Use default config.json
    python server.py -c myconfig.json # Specify config file
"""

import argparse
import hashlib
import hmac
import json
import logging
import os
import sys

from pyftpdlib.authorizers import DummyAuthorizer, AuthorizerError
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from filesystem import MultiDirFilesystem, USER_DIR_MAP

logger = logging.getLogger("fkftp")


class HashedAuthorizer(DummyAuthorizer):
    """Authorizer with SHA-256 hashed password verification.

    Password format: "salt$hash", where hash = sha256(salt + password).
    If password_hash is empty, authentication is skipped (first-time setup only).
    """

    def add_user(self, username, password_hash, homedir,
                 perm="elr", msg_login="Login successful.",
                 msg_quit="Goodbye."):
        if self.has_user(username):
            raise AuthorizerError(f"user {username!r} already exists")
        # Skip homedir existence check (virtual filesystem, no single root)
        self._check_permissions(username, perm)
        self.user_table[username] = {
            "pwd": str(password_hash),
            "home": homedir,
            "perm": perm,
            "operms": {},
            "msg_login": str(msg_login),
            "msg_quit": str(msg_quit),
        }

    def has_perm(self, username, perm, path=None):
        """Override permission check to support multiple mount directories.

        The original implementation only checks the home directory.
        This version checks all mounted directories for the user.
        Virtual root "/" is also treated as a valid path for listing operations.
        """
        if path is None:
            return perm in self.user_table[username]["perm"]
        # Virtual root path (for dir / ls etc.)
        if path == "/":
            return perm in self.user_table[username]["perm"]
        path = os.path.normcase(path)
        # Check per-directory permission overrides
        for dir_ in self.user_table[username]["operms"]:
            operm, recursive = self.user_table[username]["operms"][dir_]
            if path == dir_ or (recursive and path.startswith(dir_ + os.sep)):
                return perm in operm
        # Check all mounted directories
        dirs = USER_DIR_MAP.get(username, {})
        for real_base in dirs.values():
            base = os.path.normcase(os.path.normpath(real_base))
            if path == base or path.startswith(base + os.sep):
                return perm in self.user_table[username]["perm"]
        return False

    def validate_authentication(self, username, password, handler):
        from pyftpdlib.exceptions import AuthenticationFailed
        if not self.has_user(username):
            raise AuthenticationFailed("Authentication failed.")
        stored = self.user_table[username]["pwd"]
        if not stored:
            # Empty password hash => first run, prompt user to set password
            raise AuthenticationFailed(
                "Password not configured. Run hash_password.py first."
            )
        # Format: salt$hash
        if "$" not in stored:
            raise AuthenticationFailed("Invalid password hash format.")
        salt, expected_hash = stored.split("$", 1)
        actual_hash = hashlib.sha256(
            (salt + password).encode("utf-8")
        ).hexdigest()
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise AuthenticationFailed("Authentication failed.")


def load_config(config_path):
    """Load JSON configuration file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_directories(users_config):
    """Validate all directories in config exist; auto-create if missing."""
    for user_cfg in users_config:
        for name, path in user_cfg.get("directories", {}).items():
            real_path = os.path.normpath(path)
            if not os.path.isdir(real_path):
                logger.info("Creating directory: %s -> %s", name, real_path)
                os.makedirs(real_path, exist_ok=True)


def setup_server(config):
    """Create and return an FTPServer instance based on config."""
    authorizer = HashedAuthorizer()

    users = config.get("users", [])
    validate_directories(users)

    for user_cfg in users:
        username = user_cfg["username"]
        password_hash = user_cfg.get("password_hash", "")
        permissions = user_cfg.get("permissions", "elr")
        directories = user_cfg.get("directories", {})

        # Register user directory mapping to global variable
        USER_DIR_MAP[username] = directories

        # Use first mapped directory as home (not actually used; virtual filesystem handles everything)
        first_dir = next(iter(directories.values()), None)
        if first_dir:
            home = os.path.normpath(first_dir)
        else:
            home = os.path.normpath(".")

        authorizer.add_user(username, password_hash, home, perm=permissions)
        logger.info(
            "User '%s' registered with %d mount(s): %s",
            username,
            len(directories),
            ", ".join(f"{k} -> {v}" for k, v in directories.items()),
        )

    handler = FTPHandler
    handler.authorizer = authorizer
    handler.abstracted_fs = MultiDirFilesystem
    handler.banner = config.get("banner", "Welcome to FKFTP Server.")

    # Passive mode port range
    passive_ports = config.get("passive_ports", [60000, 65535])
    if isinstance(passive_ports, list) and len(passive_ports) == 2:
        handler.passive_ports = range(passive_ports[0], passive_ports[1] + 1)

    host = config.get("host", "0.0.0.0")
    port = config.get("port", 2121)
    server = FTPServer((host, port), handler)

    server.max_cons = config.get("max_connections", 256)
    server.max_cons_per_ip = config.get("max_connections_per_ip", 5)

    return server


def main():
    parser = argparse.ArgumentParser(description="FKFTP - Multi-directory FTP Server")
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.path.dirname(__file__), config_path)

    if not os.path.isfile(config_path):
        logger.error("Config file not found: %s", config_path)
        logger.info("Create a config.json file. See config.json for example.")
        sys.exit(1)

    config = load_config(config_path)
    server = setup_server(config)

    logger.info(
        "FKFTP Server starting on %s:%d",
        config.get("host", "0.0.0.0"),
        config.get("port", 2121),
    )
    logger.info("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
        server.close_all()


if __name__ == "__main__":
    main()
