"""
Post-Quantum Cryptography configuration.

Controls the PQC migration state and algorithm selection.
Can be driven by environment variables or remote config for gradual rollout.

PQC Migration Phases:
  Phase 0: Classical-only — AES-256-GCM, ECDSA, ECDHE
  Phase 1: Hybrid mode — classical + PQC running in parallel
  Phase 2: PQC-preferred — PQC algorithms preferred, classical fallback
  Phase 3: PQC-only — classical algorithms deprecated

White House EO 14412 mandates federal PQC migration by Dec 31, 2030.
"""

import os
from enum import IntEnum


class MigrationPhase(IntEnum):
    PHASE_0_CLASSICAL = 0
    PHASE_1_HYBRID = 1
    PHASE_2_PQC_PREFERRED = 2
    PHASE_3_PQC_ONLY = 3


class PqcConfig:
    """PQC configuration — driven by environment variables."""

    MIGRATION_PHASE = MigrationPhase(
        int(os.getenv("ANGAVU_PQC_PHASE", "1"))
    )
    ENABLE_HYBRID_KEY_EXCHANGE = os.getenv("ANGAVU_PQC_HYBRID_KEX", "true").lower() == "true"
    ENABLE_PQC_SIGNING = os.getenv("ANGAVU_PQC_SIGNING", "true").lower() == "true"
    ENABLE_AUDIT_LOGGING = os.getenv("ANGAVU_PQC_AUDIT", "true").lower() == "true"

    @classmethod
    def get_recommended_key_exchange_algorithm(cls) -> str:
        if cls.MIGRATION_PHASE == MigrationPhase.PHASE_0_CLASSICAL:
            return "ECDHE"
        return "X25519+ML-KEM-768" if cls.MIGRATION_PHASE == MigrationPhase.PHASE_1_HYBRID else "ML-KEM-768"

    @classmethod
    def get_recommended_signature_algorithm(cls) -> str:
        if cls.MIGRATION_PHASE == MigrationPhase.PHASE_0_CLASSICAL:
            return "ECDSA-P256"
        return "ML-DSA-65"

    @classmethod
    def get_recommended_encryption_algorithm(cls) -> str:
        return "AES-256-GCM"  # Quantum-safe (256-bit key → 128-bit post-quantum)

    @classmethod
    def should_use_hybrid_key_exchange(cls) -> bool:
        return cls.MIGRATION_PHASE >= MigrationPhase.PHASE_1_HYBRID and cls.ENABLE_HYBRID_KEY_EXCHANGE

    @classmethod
    def allow_classical_fallback(cls) -> bool:
        return cls.MIGRATION_PHASE <= MigrationPhase.PHASE_2_PQC_PREFERRED

    @classmethod
    def get_status_report(cls) -> dict:
        return {
            "migration_phase": cls.MIGRATION_PHASE.name,
            "hybrid_key_exchange": cls.ENABLE_HYBRID_KEY_EXCHANGE,
            "pqc_signing": cls.ENABLE_PQC_SIGNING,
            "audit_logging": cls.ENABLE_AUDIT_LOGGING,
            "recommended_key_exchange": cls.get_recommended_key_exchange_algorithm(),
            "recommended_signature": cls.get_recommended_signature_algorithm(),
            "recommended_encryption": cls.get_recommended_encryption_algorithm(),
            "classical_fallback_allowed": cls.allow_classical_fallback(),
            "white_house_eo_deadline": "2030-12-31",
        }
