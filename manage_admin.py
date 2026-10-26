#!/usr/bin/env python3
"""
=============================================================================
FRAS Enterprise — Terminal Admin Management Console
=============================================================================
Safely manage, create, and update Administrator accounts directly from the
backend terminal.

Usage:
  Interactive Mode:
    python manage_admin.py

  Command Line Mode:
    python manage_admin.py list
    python manage_admin.py set --username <user> [--password <pwd>] [--name <name>] [--email <email>]
    python manage_admin.py change-password --username <user>
    python manage_admin.py purge-default
    python manage_admin.py delete --username <user>
=============================================================================
"""

import sys
import os
import argparse
import getpass
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if present
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'attendance.db'}")


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 rounds and a unique 16-byte salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"


def get_db_connection():
    """
    Get database session or raw connection.
    Attempts SQLAlchemy first, falls back to sqlite3 standard library if SQLite is used.
    """
    try:
        from app.database import SessionLocal
        return ("sqlalchemy", SessionLocal())
    except Exception:
        if "sqlite" in DATABASE_URL:
            import sqlite3
            db_path = DATABASE_URL.replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            return ("sqlite", conn)
        raise RuntimeError(f"Cannot connect to database at {DATABASE_URL}")


def list_admins():
    """List all users with administrative roles."""
    db_type, db = get_db_connection()
    print("\n" + "=" * 70)
    print("  CURRENT SYSTEM ADMINISTRATORS")
    print("=" * 70)

    admin_roles = ("ADMIN", "SUPER_ADMIN", "HR_MANAGER")

    if db_type == "sqlalchemy":
        from app.models import User
        admins = db.query(User).filter(User.role.in_(admin_roles)).all()
        if not admins:
            print("  [!] No administrator accounts found in database.")
        for a in admins:
            status = "ACTIVE" if a.is_active else "INACTIVE"
            print(f"  • ID: {a.id:<3} | Username: {a.user_code:<18} | Role: {a.role:<12} | Status: {status:<8}")
            print(f"    Name: {a.full_name} | Email: {a.email or 'N/A'}")
            print("  " + "-" * 66)
        db.close()
    else:
        cursor = db.cursor()
        rows = cursor.execute(
            "SELECT id, user_code, full_name, email, role, is_active FROM users WHERE role IN ('ADMIN', 'SUPER_ADMIN', 'HR_MANAGER')"
        ).fetchall()
        if not rows:
            print("  [!] No administrator accounts found in database.")
        for r in rows:
            status = "ACTIVE" if r[5] else "INACTIVE"
            print(f"  • ID: {r[0]:<3} | Username: {r[1]:<18} | Role: {r[4]:<12} | Status: {status:<8}")
            print(f"    Name: {r[2]} | Email: {r[3] or 'N/A'}")
            print("  " + "-" * 66)
        db.close()
    print("=" * 70 + "\n")


def set_admin(username: str, password: str, full_name: str = None, email: str = None, role: str = "SUPER_ADMIN"):
    """Create or update an administrator account."""
    if not username or len(username.strip()) < 3:
        print("[ERROR] Username must be at least 3 characters long.")
        return False

    if not password or len(password) < 6:
        print("[ERROR] Password must be at least 6 characters long (8+ recommended).")
        return False

    username = username.strip()
    full_name = (full_name or username).strip()
    email = email.strip() if email else None
    role = role.upper() if role in ("SUPER_ADMIN", "ADMIN", "HR_MANAGER") else "SUPER_ADMIN"
    pwd_hash = hash_password(password)
    now = datetime.now(timezone.utc)

    db_type, db = get_db_connection()

    if db_type == "sqlalchemy":
        from app.models import User, AuditLog
        user = db.query(User).filter(User.user_code == username).first()
        is_new = user is None
        if is_new:
            user = User(
                user_code=username,
                full_name=full_name,
                email=email,
                role=role,
                password_hash=pwd_hash,
                is_active=True,
                created_at=now,
            )
            db.add(user)
        else:
            user.full_name = full_name
            if email:
                user.email = email
            user.role = role
            user.password_hash = pwd_hash
            user.is_active = True

        audit = AuditLog(
            actor="CLI_CONSOLE",
            action="SET_ADMIN",
            details=f"Admin account '{username}' {'created' if is_new else 'updated'} via terminal CLI.",
            timestamp=datetime.now(),
        )
        db.add(audit)
        db.commit()
        db.close()
    else:
        cursor = db.cursor()
        existing = cursor.execute("SELECT id FROM users WHERE user_code = ?", (username,)).fetchone()
        if existing:
            cursor.execute(
                "UPDATE users SET full_name = ?, email = ?, role = ?, password_hash = ?, is_active = 1 WHERE user_code = ?",
                (full_name, email, role, pwd_hash, username),
            )
        else:
            cursor.execute(
                "INSERT INTO users (user_code, full_name, email, role, password_hash, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (username, full_name, email, role, pwd_hash, now.strftime("%Y-%m-%d %H:%M:%S")),
            )
        cursor.execute(
            "INSERT INTO audit_logs (actor, action, details, timestamp) VALUES (?, ?, ?, ?)",
            ("CLI_CONSOLE", "SET_ADMIN", f"Admin '{username}' updated via terminal CLI", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        db.close()

    print(f"\n[SUCCESS] Administrator '{username}' has been successfully configured with role '{role}'!")
    return True


def change_admin_password(username: str, new_password: str):
    """Change password for an existing administrator."""
    if not new_password or len(new_password) < 6:
        print("[ERROR] Password must be at least 6 characters long.")
        return False

    pwd_hash = hash_password(new_password)
    db_type, db = get_db_connection()

    if db_type == "sqlalchemy":
        from app.models import User, AuditLog
        user = db.query(User).filter(User.user_code == username).first()
        if not user:
            print(f"[ERROR] User with username '{username}' not found.")
            db.close()
            return False
        user.password_hash = pwd_hash
        user.is_active = True
        audit = AuditLog(
            actor="CLI_CONSOLE",
            action="CHANGE_PASSWORD",
            details=f"Password for '{username}' was updated via terminal CLI.",
            timestamp=datetime.now(),
        )
        db.add(audit)
        db.commit()
        db.close()
    else:
        cursor = db.cursor()
        user = cursor.execute("SELECT id FROM users WHERE user_code = ?", (username,)).fetchone()
        if not user:
            print(f"[ERROR] User with username '{username}' not found.")
            db.close()
            return False
        cursor.execute("UPDATE users SET password_hash = ?, is_active = 1 WHERE user_code = ?", (pwd_hash, username))
        cursor.execute(
            "INSERT INTO audit_logs (actor, action, details, timestamp) VALUES (?, ?, ?, ?)",
            ("CLI_CONSOLE", "CHANGE_PASSWORD", f"Password for '{username}' changed via terminal CLI", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        db.close()

    print(f"\n[SUCCESS] Password for administrator '{username}' has been updated!")
    return True


def purge_default_admin(confirm: bool = False):
    """Remove or deactivate the default insecure 'admin' account."""
    db_type, db = get_db_connection()

    if db_type == "sqlalchemy":
        from app.models import User, AuditLog
        default_admin = db.query(User).filter(User.user_code == "admin").first()
        if not default_admin:
            print("[INFO] Default 'admin' account does not exist or was already removed.")
            db.close()
            return

        other_admins = db.query(User).filter(User.user_code != "admin", User.role.in_(("ADMIN", "SUPER_ADMIN"))).count()
        if other_admins == 0:
            print("[WARNING] You must create your custom admin account BEFORE deleting the default admin, or you will be locked out!")
            db.close()
            return

        db.delete(default_admin)
        audit = AuditLog(
            actor="CLI_CONSOLE",
            action="PURGE_DEFAULT_ADMIN",
            details="Removed insecure default 'admin' account from database.",
            timestamp=datetime.now(),
        )
        db.add(audit)
        db.commit()
        db.close()
    else:
        cursor = db.cursor()
        default_admin = cursor.execute("SELECT id FROM users WHERE user_code = 'admin'").fetchone()
        if not default_admin:
            print("[INFO] Default 'admin' account does not exist or was already removed.")
            db.close()
            return

        other_admins = cursor.execute(
            "SELECT COUNT(*) FROM users WHERE user_code != 'admin' AND role IN ('ADMIN', 'SUPER_ADMIN')"
        ).fetchone()[0]
        if other_admins == 0:
            print("[WARNING] You must create your custom admin account BEFORE deleting the default admin, or you will be locked out!")
            db.close()
            return

        cursor.execute("DELETE FROM users WHERE user_code = 'admin'")
        cursor.execute(
            "INSERT INTO audit_logs (actor, action, details, timestamp) VALUES (?, ?, ?, ?)",
            ("CLI_CONSOLE", "PURGE_DEFAULT_ADMIN", "Purged default admin account", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        db.close()

    print("\n[SUCCESS] Default 'admin' account has been completely purged from the system.")
    print("          No one can log in using default 'admin' / 'admin123' anymore!")


def delete_admin(username: str):
    """Delete a specific administrator account."""
    if not username:
        print("[ERROR] Username is required.")
        return

    db_type, db = get_db_connection()
    if db_type == "sqlalchemy":
        from app.models import User, AuditLog
        user = db.query(User).filter(User.user_code == username).first()
        if not user:
            print(f"[ERROR] User '{username}' not found.")
            db.close()
            return
        db.delete(user)
        audit = AuditLog(
            actor="CLI_CONSOLE",
            action="DELETE_ADMIN",
            details=f"Deleted admin account '{username}' via terminal CLI.",
            timestamp=datetime.now(),
        )
        db.add(audit)
        db.commit()
        db.close()
    else:
        cursor = db.cursor()
        cursor.execute("DELETE FROM users WHERE user_code = ?", (username,))
        cursor.execute(
            "INSERT INTO audit_logs (actor, action, details, timestamp) VALUES (?, ?, ?, ?)",
            ("CLI_CONSOLE", "DELETE_ADMIN", f"Deleted admin '{username}'", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        db.close()

    print(f"\n[SUCCESS] Admin user '{username}' deleted.")


def interactive_menu():
    """Interactive CLI menu with secure hidden password prompts."""
    while True:
        print("\n" + "=" * 65)
        print("  FRAS Enterprise — Terminal Admin Security Console")
        print("=" * 65)
        print("  [1] Create / Update Custom Administrator Account")
        print("  [2] Change Admin Password")
        print("  [3] Remove / Purge Insecure Default 'admin' Account")
        print("  [4] List All Administrator Accounts")
        print("  [5] Delete an Admin Account")
        print("  [0] Exit")
        print("=" * 65)

        try:
            choice = input("Enter choice [0-5]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == "0":
            print("Exiting console.")
            break
        elif choice == "1":
            print("\n--- Create / Update Custom Administrator ---")
            username = input("Enter new Admin Username: ").strip()
            if not username:
                print("[!] Username cannot be empty.")
                continue

            full_name = input(f"Enter Full Name [{username}]: ").strip() or username
            email = input("Enter Email Address (optional): ").strip()

            print("Roles: [1] SUPER_ADMIN (Full privileges)  [2] ADMIN  [3] HR_MANAGER")
            role_choice = input("Select Role [1]: ").strip()
            role = "SUPER_ADMIN" if role_choice in ("", "1") else ("ADMIN" if role_choice == "2" else "HR_MANAGER")

            pwd1 = getpass.getpass("Enter Secure Password (hidden): ")
            if len(pwd1) < 6:
                print("[!] Password must be at least 6 characters (8+ recommended).")
                continue
            pwd2 = getpass.getpass("Confirm Secure Password (hidden): ")
            if pwd1 != pwd2:
                print("[!] Passwords do not match. Aborting.")
                continue

            set_admin(username=username, password=pwd1, full_name=full_name, email=email, role=role)

            # Proactively prompt to purge default admin if it still exists
            purge = input("\nWould you like to remove the default insecure 'admin' account now? (y/n) [y]: ").strip().lower()
            if purge in ("", "y", "yes"):
                purge_default_admin()

        elif choice == "2":
            print("\n--- Change Admin Password ---")
            username = input("Enter Admin Username: ").strip()
            if not username:
                continue
            pwd1 = getpass.getpass("Enter New Password (hidden): ")
            pwd2 = getpass.getpass("Confirm New Password (hidden): ")
            if pwd1 != pwd2:
                print("[!] Passwords do not match.")
                continue
            change_admin_password(username, pwd1)

        elif choice == "3":
            print("\n--- Purge Default 'admin' Account ---")
            confirm = input("Are you sure you want to remove the default 'admin' account? (y/n): ").strip().lower()
            if confirm in ("y", "yes"):
                purge_default_admin()

        elif choice == "4":
            list_admins()

        elif choice == "5":
            print("\n--- Delete Admin Account ---")
            username = input("Enter Username to delete: ").strip()
            if not username:
                continue
            confirm = input(f"Permanently delete admin '{username}'? (y/n): ").strip().lower()
            if confirm in ("y", "yes"):
                delete_admin(username)
        else:
            print("Invalid option. Please enter 0-5.")


def main():
    parser = argparse.ArgumentParser(description="FRAS Enterprise Administrator Terminal Tool")
    subparsers = parser.add_subparsers(dest="command")

    # Command: list
    subparsers.add_parser("list", help="List all administrator accounts")

    # Command: set
    set_parser = subparsers.add_parser("set", help="Create or update an admin account")
    set_parser.add_argument("--username", "-u", required=True, help="Admin username / login code")
    set_parser.add_argument("--password", "-p", help="Admin password (if omitted, will prompt securely)")
    set_parser.add_argument("--name", "-n", help="Full display name")
    set_parser.add_argument("--email", "-e", help="Email address")
    set_parser.add_argument("--role", "-r", default="SUPER_ADMIN", choices=["SUPER_ADMIN", "ADMIN", "HR_MANAGER"])

    # Command: change-password
    pwd_parser = subparsers.add_parser("change-password", help="Change password for an existing admin")
    pwd_parser.add_argument("--username", "-u", required=True, help="Admin username")
    pwd_parser.add_argument("--password", "-p", help="New password (if omitted, will prompt securely)")

    # Command: purge-default
    subparsers.add_parser("purge-default", help="Remove the default 'admin' account")

    # Command: delete
    del_parser = subparsers.add_parser("delete", help="Delete an admin account")
    del_parser.add_argument("--username", "-u", required=True, help="Username of admin to delete")

    args = parser.parse_args()

    if not args.command:
        # No command passed -> launch interactive console
        interactive_menu()
    elif args.command == "list":
        list_admins()
    elif args.command == "set":
        pwd = args.password
        if not pwd:
            pwd = getpass.getpass("Enter Admin Password (hidden): ")
            pwd_confirm = getpass.getpass("Confirm Admin Password (hidden): ")
            if pwd != pwd_confirm:
                print("[ERROR] Passwords do not match.")
                sys.exit(1)
        set_admin(username=args.username, password=pwd, full_name=args.name, email=args.email, role=args.role)
    elif args.command == "change-password":
        pwd = args.password
        if not pwd:
            pwd = getpass.getpass("Enter New Password (hidden): ")
            pwd_confirm = getpass.getpass("Confirm New Password (hidden): ")
            if pwd != pwd_confirm:
                print("[ERROR] Passwords do not match.")
                sys.exit(1)
        change_admin_password(args.username, pwd)
    elif args.command == "purge-default":
        purge_default_admin()
    elif args.command == "delete":
        delete_admin(args.username)


if __name__ == "__main__":
    main()
