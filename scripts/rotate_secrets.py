#!/usr/bin/env python3
"""
Secret rotation script for Angavu Intelligence Backend.

Can be run as a standalone script or via cron to check and trigger
secret rotation.

Usage:
    # Check rotation status
    python scripts/rotate_secrets.py --status

    # Trigger rotation for overdue secrets
    python scripts/rotate_secrets.py --rotate

    # Force rotate a specific secret type
    python scripts/rotate_secrets.py --force --type encryption_key

Environment variables:
    SECRET_ROTATION_ENABLED=true
    SECRET_ROTATION_ENCRYPTION_DAYS=90
    SECRET_ROTATION_JWT_DAYS=30
    SECRET_ROTATION_WEBHOOK_DAYS=90
    SECRET_ROTATION_GRACE_HOURS=24
"""

import argparse
import json
import os
import sys
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.security.secret_rotation import (
    RotationConfig,
    SecretRotationManager,
    SecretType,
)


def generate_new_secret(length: int = 64) -> str:
    """Generate a cryptographically secure random secret."""
    import secrets
    return secrets.token_urlsafe(length)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage secret rotation")
    parser.add_argument("--status", action="store_true", help="Show rotation status")
    parser.add_argument("--rotate", action="store_true", help="Rotate overdue secrets")
    parser.add_argument("--force", action="store_true", help="Force rotation (use with --type)")
    parser.add_argument("--type", type=str, help="Secret type to force rotate")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    manager = SecretRotationManager()

    # Load current secrets from environment (simulating active secrets)
    secret_mapping = {
        SecretType.ENCRYPTION_KEY: "ENCRYPTION_KEY",
        SecretType.JWT_KEY: "JWT_SECRET_KEY",
        SecretType.WEBHOOK_SECRET: "OPENWA_WEBHOOK_SECRET",
        SecretType.API_KEY: "SECRET_KEY",
    }

    for secret_type, env_key in secret_mapping.items():
        value = os.getenv(env_key, "")
        if value:
            manager.add_secret(secret_type, value)

    if args.status:
        status = manager.get_rotation_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print("\n🔐 Secret Rotation Status")
            print("=" * 60)
            for name, info in status.items():
                if info.get("current_version"):
                    icon = "🔴" if info["needs_rotation"] else "🟢"
                    print(f"{icon} {name}:")
                    print(f"   Version: {info['current_version']}")
                    print(f"   Age: {info['age_days']} days")
                    print(f"   Rotation interval: {info['rotation_interval_days']} days")
                    print(f"   Remaining: {info['remaining_days']} days")
                else:
                    print(f"⚪ {name}: No active secret")
            print()
        return

    if args.force and args.type:
        try:
            secret_type = SecretType(args.type)
        except ValueError:
            print(f"Unknown secret type: {args.type}")
            print(f"Valid types: {[st.value for st in SecretType]}")
            sys.exit(1)

        new_value = generate_new_secret()
        manager.add_secret(secret_type, new_value)
        print(f"✅ Rotated {args.type} to new value (version {manager.get_active_secret(secret_type).version})")
        print(f"   New secret (store securely): {new_value[:8]}...{new_value[-8:]}")
        return

    if args.rotate:
        needs_rotation = manager.check_rotation_needed()
        if not needs_rotation:
            print("✅ All secrets are within their rotation intervals.")
            return

        print(f"🔄 Rotating {len(needs_rotation)} overdue secret(s)...")
        for secret_type in needs_rotation:
            new_value = generate_new_secret()
            manager.add_secret(secret_type, new_value)
            active = manager.get_active_secret(secret_type)
            print(f"   ✅ {secret_type.value}: rotated to version {active.version}")

        print("\n⚠️  Remember to:")
        print("   1. Update environment variables with new secrets")
        print("   2. Deploy with rolling restart (grace period handles overlap)")
        print("   3. Verify services are healthy after deployment")
        return

    # Default: show status
    parser.print_help()


if __name__ == "__main__":
    main()
