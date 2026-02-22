"""
Password hash generation tool.

Paste the generated hash into the password_hash field in config.json.

Usage:
    python hash_password.py
    python hash_password.py -p mypassword
"""

import argparse
import getpass
import hashlib
import os


def hash_password(password):
    """Generate password hash using SHA-256 + random salt.

    Return format: "salt$hash"
    """
    salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${h}"


def main():
    parser = argparse.ArgumentParser(description="Generate password hash for FKFTP")
    parser.add_argument("-p", "--password", help="Password (prompted if not provided)")
    args = parser.parse_args()

    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Enter password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: Passwords do not match.")
            return

    result = hash_password(password)
    print()
    print("Password hash (copy to config.json 'password_hash' field):")
    print(result)


if __name__ == "__main__":
    main()
