"""
Automated Secret Rotation for Angavu Intelligence Backend.

Provides configuration and utilities for periodic secret rotation
including encryption keys, JWT keys, webhook secrets, and API keys.

Rotation schedule is configurable via environment variables.
An HTTP endpoint (/admin/rotate-secrets) triggers rotation
(protected by admin authentication).

Rotation strategy:
- Encryption keys: Generate new key, re-encrypt data, retire old key
- JWT keys: Generate new RSA/ML-DSA keypair, accept old tokens until expiry
- Webhook secrets: Rotate with grace period for upstream propagation
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SecretType(StrEnum):
    """Types of secrets that can be rotated."""
    ENCRYPTION_KEY = "encryption_key"
    JWT_KEY = "jwt_key"
    WEBHOOK_SECRET = "webhook_secret"
    API_KEY = "api_key"
    DATA_ENCRYPTION_SALT = "data_encryption_salt"


@dataclass
class RotationPolicy:
    """Policy for a specific secret type."""
    secret_type: SecretType
    rotation_interval_days: int
    grace_period_hours: int = 24  # Keep old secret valid for this long
    max_key_versions: int = 3  # How many old versions to retain
    auto_rotate: bool = True


@dataclass
class SecretVersion:
    """A versioned secret entry."""
    secret_type: SecretType
    version: int
    value: str
    created_at: float
    expires_at: float
    retired_at: float | None = None
    is_active: bool = True


@dataclass
class RotationConfig:
    """Secret rotation configuration loaded from environment."""

    # Rotation intervals (in days)
    ENCRYPTION_KEY_ROTATION_DAYS: int = int(
        os.getenv("SECRET_ROTATION_ENCRYPTION_DAYS", "90")
    )
    JWT_KEY_ROTATION_DAYS: int = int(
        os.getenv("SECRET_ROTATION_JWT_DAYS", "30")
    )
    WEBHOOK_SECRET_ROTATION_DAYS: int = int(
        os.getenv("SECRET_ROTATION_WEBHOOK_DAYS", "90")
    )
    API_KEY_ROTATION_DAYS: int = int(
        os.getenv("SECRET_ROTATION_API_KEY_DAYS", "180")
    )

    # Grace period (in hours) — old secrets remain valid during this window
    GRACE_PERIOD_HOURS: int = int(
        os.getenv("SECRET_ROTATION_GRACE_HOURS", "24")
    )

    # Enable/disable automatic rotation
    AUTO_ROTATE_ENABLED: bool = (
        os.getenv("SECRET_ROTATION_ENABLED", "true").lower() == "true"
    )

    # Admin endpoint for manual rotation trigger
    ROTATION_ENDPOINT_ENABLED: bool = (
        os.getenv("SECRET_ROTATION_ENDPOINT_ENABLED", "true").lower() == "true"
    )

    @classmethod
    def get_policies(cls) -> dict[SecretType, RotationPolicy]:
        """Get rotation policies for all secret types."""
        cfg = cls()
        return {
            SecretType.ENCRYPTION_KEY: RotationPolicy(
                secret_type=SecretType.ENCRYPTION_KEY,
                rotation_interval_days=cfg.ENCRYPTION_KEY_ROTATION_DAYS,
                grace_period_hours=cfg.GRACE_PERIOD_HOURS,
                auto_rotate=cfg.AUTO_ROTATE_ENABLED,
            ),
            SecretType.JWT_KEY: RotationPolicy(
                secret_type=SecretType.JWT_KEY,
                rotation_interval_days=cfg.JWT_KEY_ROTATION_DAYS,
                grace_period_hours=cfg.GRACE_PERIOD_HOURS,
                auto_rotate=cfg.AUTO_ROTATE_ENABLED,
            ),
            SecretType.WEBHOOK_SECRET: RotationPolicy(
                secret_type=SecretType.WEBHOOK_SECRET,
                rotation_interval_days=cfg.WEBHOOK_SECRET_ROTATION_DAYS,
                grace_period_hours=cfg.GRACE_PERIOD_HOURS,
                auto_rotate=cfg.AUTO_ROTATE_ENABLED,
            ),
            SecretType.API_KEY: RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval_days=cfg.API_KEY_ROTATION_DAYS,
                grace_period_hours=cfg.GRACE_PERIOD_HOURS,
                auto_rotate=cfg.AUTO_ROTATE_ENABLED,
            ),
        }


class SecretRotationManager:
    """
    Manages secret rotation lifecycle.

    Tracks secret versions, enforces rotation policies, and provides
    the current + previous secrets during grace periods.
    """

    def __init__(self) -> None:
        self._secrets: dict[SecretType, list[SecretVersion]] = {}
        self._policies = RotationConfig.get_policies()
        self._logger = logger.bind(component="secret_rotation")

    def register_policy(self, policy: RotationPolicy) -> None:
        """Register or update a rotation policy."""
        self._policies[policy.secret_type] = policy

    def add_secret(
        self,
        secret_type: SecretType,
        value: str,
        rotation_interval_days: int | None = None,
    ) -> SecretVersion:
        """
        Add a new version of a secret.

        Args:
            secret_type: The type of secret
            value: The secret value
            rotation_interval_days: Override the policy interval

        Returns:
            The new SecretVersion
        """
        policy = self._policies.get(secret_type)
        if policy is None:
            policy = RotationPolicy(
                secret_type=secret_type,
                rotation_interval_days=rotation_interval_days or 90,
            )
            self._policies[secret_type] = policy

        interval_days = rotation_interval_days or policy.rotation_interval_days
        now = time.time()

        # Get next version number
        existing = self._secrets.get(secret_type, [])
        version = (existing[-1].version + 1) if existing else 1

        # Deactivate previous versions (keep them for grace period)
        for sv in existing:
            if sv.is_active:
                sv.is_active = False
                sv.retired_at = now

        new_version = SecretVersion(
            secret_type=secret_type,
            version=version,
            value=value,
            created_at=now,
            expires_at=now + (interval_days * 86400),
        )

        self._secrets.setdefault(secret_type, []).append(new_version)

        # Enforce max versions
        self._cleanup_old_versions(secret_type, policy.max_key_versions)

        self._logger.info(
            "secret_rotated",
            secret_type=secret_type.value,
            version=version,
            expires_in_days=interval_days,
        )

        return new_version

    def get_active_secret(self, secret_type: SecretType) -> SecretVersion | None:
        """Get the currently active secret for a type."""
        versions = self._secrets.get(secret_type, [])
        for sv in reversed(versions):
            if sv.is_active:
                return sv
        return None

    def get_valid_secrets(self, secret_type: SecretType) -> list[SecretVersion]:
        """
        Get all secrets that are currently valid (active + within grace period).

        During rotation grace periods, both old and new secrets are valid
        to allow smooth transitions.
        """
        versions = self._secrets.get(secret_type, [])
        now = time.time()
        valid = []
        for sv in versions:
            if sv.is_active:
                valid.append(sv)
            elif sv.retired_at is not None:
                policy = self._policies.get(secret_type)
                grace_seconds = (policy.grace_period_hours * 3600) if policy else 86400
                if now - sv.retired_at < grace_seconds:
                    valid.append(sv)
        return valid

    def check_rotation_needed(self) -> list[SecretType]:
        """
        Check which secrets need rotation.

        Returns:
            List of secret types that have passed their rotation interval.
        """
        now = time.time()
        needs_rotation = []

        for secret_type, policy in self._policies.items():
            if not policy.auto_rotate:
                continue

            active = self.get_active_secret(secret_type)
            if active is None:
                needs_rotation.append(secret_type)
                continue

            age_days = (now - active.created_at) / 86400
            if age_days >= policy.rotation_interval_days:
                needs_rotation.append(secret_type)
                self._logger.warning(
                    "secret_rotation_overdue",
                    secret_type=secret_type.value,
                    age_days=round(age_days, 1),
                    interval_days=policy.rotation_interval_days,
                )

        return needs_rotation

    def get_rotation_status(self) -> dict[str, Any]:
        """Get a status report of all secrets and their rotation state."""
        now = time.time()
        status = {}

        for secret_type in SecretType:
            active = self.get_active_secret(secret_type)
            policy = self._policies.get(secret_type)
            versions = self._secrets.get(secret_type, [])

            if active and policy:
                age_days = (now - active.created_at) / 86400
                remaining_days = max(0, policy.rotation_interval_days - age_days)
                status[secret_type.value] = {
                    "current_version": active.version,
                    "age_days": round(age_days, 1),
                    "rotation_interval_days": policy.rotation_interval_days,
                    "remaining_days": round(remaining_days, 1),
                    "needs_rotation": remaining_days <= 0,
                    "total_versions": len(versions),
                    "auto_rotate": policy.auto_rotate,
                }
            else:
                status[secret_type.value] = {
                    "current_version": None,
                    "needs_rotation": True,
                    "auto_rotate": policy.auto_rotate if policy else False,
                }

        return status

    def _cleanup_old_versions(
        self, secret_type: SecretType, max_versions: int
    ) -> None:
        """Remove retired versions beyond the retention limit."""
        versions = self._secrets.get(secret_type, [])
        retired = [v for v in versions if not v.is_active]
        if len(retired) > max_versions:
            # Keep only the most recent retired versions
            to_remove = retired[: len(retired) - max_versions]
            for sv in to_remove:
                versions.remove(sv)


# ══════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════

_rotation_manager: SecretRotationManager | None = None


def get_rotation_manager() -> SecretRotationManager:
    """Get or create the singleton rotation manager."""
    global _rotation_manager
    if _rotation_manager is None:
        _rotation_manager = SecretRotationManager()
    return _rotation_manager
