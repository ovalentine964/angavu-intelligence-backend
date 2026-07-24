"""
Federated Learning API endpoints.

Receives model updates from Msaidizi Android devices and serves
aggregated global models. All endpoints are privacy-preserving —
the server never sees raw speech or text data.

Endpoints align with FederatedLearningClient.kt in the Android app:
- Upload: POST /api/v1/fl/upload-update  (also /api/v1/federated/upload)
- Download: GET /api/v1/fl/global-model/{dialect}
- Status: GET /api/v1/fl/status
"""

import base64
import gzip
import hashlib
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.auth import get_current_user
from app.schemas.federated_learning import (
    FLStatusResponse,
    FLUpdate,
    GlobalModelResponse,
    UploadResponse,
)

# Post-Quantum Cryptography — ML-KEM-768 + ML-DSA-65
from app.security.pqc import (
    CryptoAuditLogger,
    EncryptedGradientPayload,
    FlPqcDecryptor,
    MlKemParameterSet,
    MlKemProvider,
)

# Security exception for PQC encryption
from app.security.pqc.fl_encryption import SecurityException
from app.services.federated_learning import FederatedLearningService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Federated Learning"])

# Service singleton (stateful, holds in-memory aggregation state)
_fl_service = FederatedLearningService()

# ── PQC Infrastructure ──────────────────────────────────────────────
# Server-side ML-KEM-768 key pair for gradient decapsulation.
# Generated once at startup; public key distributed to devices.
try:
    _server_ml_kem = MlKemProvider(MlKemParameterSet.ML_KEM_768)
    _server_kem_keypair = _server_ml_kem.generate_key_pair()
    _fl_decryptor = FlPqcDecryptor(server_ml_mek_keypair=_server_kem_keypair)
    _crypto_audit = CryptoAuditLogger()
except (RuntimeError, Exception):
    _server_ml_kem = None
    _server_kem_keypair = None
    _fl_decryptor = None
    _crypto_audit = None  # PQC disabled — liboqs not installed


# ════════════════════════════════════════════════════════════════════
# PQC Public Key — Distribute server's ML-KEM-768 public key
# ════════════════════════════════════════════════════════════════════


@router.get(
    "/fl/pqc-public-key",
    summary="Get server's ML-KEM-768 public key",
    description=(
        "Returns the server's post-quantum ML-KEM-768 public key for "
        "encrypting federated learning gradient uploads. Devices use this "
        "key to encapsulate a shared secret, then encrypt gradients with "
        "AES-256-GCM."
    ),
)
async def get_pqc_public_key() -> dict:
    """
    Distribute the server's ML-KEM-768 public key.

    Devices call this endpoint to obtain the public key needed for
    PQC-encrypted gradient uploads. The key is rotated periodically
    (recommended: every 24 hours or per aggregation round).

    Returns:
        Dict with algorithm, public_key (base64), and key_id
    """
    pub_key_b64 = base64.b64encode(_server_kem_keypair.public_key).decode("ascii")
    key_id = hashlib.sha256(_server_kem_keypair.public_key).hexdigest()[:16]
    return {
        "algorithm": "ML-KEM-768",
        "public_key": pub_key_b64,
        "key_id": key_id,
        "security_level": 3,
        "description": "NIST FIPS 203 — 192-bit post-quantum security",
    }


# ════════════════════════════════════════════════════════════════════
# Upload — Receive model updates from devices
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/fl/upload-update",
    response_model=UploadResponse,
    summary="Upload federated learning update",
    description=(
        "Receive an encrypted model update from a device. "
        "The update contains anonymized correction patterns and optional "
        "LoRA adapter deltas. Raw speech/text data is never transmitted."
    ),
)
async def upload_model_update(
    update: FLUpdate,
    current_user=Depends(get_current_user),
) -> UploadResponse:
    """
    Receive encrypted model update from device.

    Privacy guarantees:
    - Device sends only anonymized correction patterns (no raw text)
    - LoRA weight deltas are encrypted client-side (Android Keystore)
    - Differential privacy (ε=0.1) is applied server-side before aggregation
    - Device ID is a one-way hash — server cannot identify the user

    PRIVACY AUDIT NOTES:
    - The FLUpdate schema contains NO audio fields (no ShortArray, ByteArray of audio)
    - The only binary field is adapter_deltas (LoRA weights, not audio)
    - correction_patterns contains only hashes and statistics, not raw text
    - The server never receives, stores, or processes raw voice data
    - All PII is stripped before the update reaches this endpoint

    The update is queued for aggregation. Once enough updates are
    collected (≥5 from the same dialect), FedAvg aggregation runs
    and a new global model version is published.

    Args:
        update: The federated learning update from the device

    Returns:
        UploadResponse with status, update ID, and new model version
        if aggregation was triggered
    """
    # Consent check — verify user has consented to data sharing
    if hasattr(current_user, 'consent_data_sharing') and not current_user.consent_data_sharing:
        logger.warning("fl_upload_no_consent", user_id=current_user.id)
        raise HTTPException(
            status_code=403,
            detail="User has not consented to data sharing. Enable in Settings > Privacy."
        )

    try:
        result = await _fl_service.upload_update(update)
        return result
    except Exception as e:
        logger.error("fl_upload_failed", error=str(e), device_id=update.device_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process federated learning update",
        )


# ════════════════════════════════════════════════════════════════════
# PQC-Encrypted Upload — Quantum-safe gradient transport
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/fl/upload-encrypted",
    response_model=UploadResponse,
    summary="Upload PQC-encrypted federated learning update",
    description=(
        "Receive a post-quantum encrypted model update from a device. "
        "Uses ML-KEM-768 for key encapsulation and AES-256-GCM for "
        "encryption. ML-DSA-65 signature verifies authenticity."
    ),
)
async def upload_encrypted_model_update(
    request: Request,
    current_user=Depends(get_current_user),
) -> UploadResponse:
    """
    Receive PQC-encrypted gradient upload from device.

    Security flow:
    1. Device obtains server's ML-KEM-768 public key via /fl/pqc-public-key
    2. Device encapsulates shared secret using ML-KEM-768
    3. Device encrypts gradients with AES-256-GCM using shared secret
    4. Device signs encrypted payload with ML-DSA-65
    5. Server decapsulates, verifies signature, decrypts

    This provides:
    - Confidentiality: AES-256-GCM (128-bit post-quantum security)
    - Key exchange: ML-KEM-768 (IND-CCA2, NIST Level 3)
    - Authenticity: ML-DSA-65 (EUF-CMA, NIST Level 3)
    """
    try:
        body = await request.json()
        payload = EncryptedGradientPayload.from_dict(body)

        # Decrypt and verify
        gradients_bytes, sig_valid = _fl_decryptor.decrypt_gradients(
            payload, verify_signature=True
        )

        _crypto_audit.log_decryption(
            algorithm_id="ML-KEM-768+AES-256-GCM",
            data_size=len(gradients_bytes),
            key_alias="fl_server_kem",
            success=True,
        )

        # Parse decrypted gradients into FLUpdate
        update_data = json.loads(gradients_bytes.decode("utf-8"))
        update = _parse_kotlin_payload(update_data)

        result = await _fl_service.upload_update(update)
        return result

    except SecurityException as e:
        _crypto_audit.log_verification(
            algorithm_id="ML-DSA-65",
            data_hash="fl_gradient",
            valid=False,
            error=str(e),
        )
        logger.warning("fl_pqc_signature_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Quantum-safe signature verification failed",
        )
    except Exception as e:
        _crypto_audit.log_decryption(
            algorithm_id="ML-KEM-768+AES-256-GCM",
            data_size=0,
            key_alias="fl_server_kem",
            success=False,
            error=str(e),
        )
        logger.error("fl_pqc_upload_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process encrypted federated learning update",
        )


# ── Compatibility endpoint matching Android client's URL ──


@router.post(
    "/federated/upload",
    response_model=UploadResponse,
    include_in_schema=False,
    summary="[Compat] Upload federated learning update",
)
async def upload_model_update_compat(
    request: Request,
    current_user=Depends(get_current_user),
) -> UploadResponse:
    """
    Compatibility endpoint for FederatedLearningClient.kt.

    The Android client posts to /api/v1/federated/upload with
    Content-Encoding: gzip. This endpoint handles decompression
    and delegates to the main upload handler.
    """
    try:
        # Handle gzip-compressed body
        body = await request.body()
        content_encoding = request.headers.get("content-encoding", "")

        if content_encoding == "gzip":
            try:
                body = gzip.decompress(body)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to decompress gzip payload",
                )

        # Parse JSON
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )

        # Convert to FLUpdate (handle camelCase from Kotlin)
        update = _parse_kotlin_payload(data)
        return await _fl_service.upload_update(update)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("fl_compat_upload_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process federated learning update",
        )


# ════════════════════════════════════════════════════════════════════
# Download — Serve global models to devices
# ════════════════════════════════════════════════════════════════════


@router.get(
    "/fl/global-model/{dialect}",
    response_model=GlobalModelResponse,
    summary="Get global model for dialect",
    description=(
        "Download the latest aggregated model for a language/dialect. "
        "Includes LoRA adapter deltas, calibration parameters, and "
        "vocabulary updates from all contributing devices."
    ),
)
async def get_global_model(
    dialect: str,
    current_user=Depends(get_current_user),
) -> GlobalModelResponse:
    """
    Get latest aggregated model for a dialect.

    Returns the most recent global model that was produced by
    FedAvg aggregation of device updates. Includes:
    - LoRA adapter weight deltas (base64-encoded)
    - Calibration parameters (temperature, Platt scaling)
    - Vocabulary updates (phoneme confusion statistics)

    Supported dialects: sw, en, luo, kik, kal, kam, luh, mer, mij

    Args:
        dialect: Language/dialect code (e.g. 'sw', 'luo')

    Returns:
        GlobalModelResponse with model data and version
    """
    model = await _fl_service.get_global_model(dialect)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No model available for dialect '{dialect}'. "
            f"Supported: sw, en, luo, kik, kal, kam, luh, mer, mij",
        )
    return model


# ── Compatibility endpoint matching Android client's URL ──


@router.get(
    "/federated/models/{language}",
    response_model=GlobalModelResponse,
    include_in_schema=False,
    summary="[Compat] Get global model",
)
async def get_global_model_compat(
    language: str,
    current_user=Depends(get_current_user),
) -> GlobalModelResponse:
    """Compatibility endpoint for FederatedLearningClient.kt."""
    return await get_global_model(language)


# ════════════════════════════════════════════════════════════════════
# Status — System health and metrics
# ════════════════════════════════════════════════════════════════════


@router.get(
    "/fl/status",
    response_model=FLStatusResponse,
    summary="Federated learning system status",
    description=(
        "Returns the current state of the federated learning system: "
        "update counts, active devices, model versions, and DP parameters."
    ),
)
async def fl_status(
    current_user=Depends(get_current_user),
) -> FLStatusResponse:
    """
    Federated learning system status.

    Returns system-wide metrics including:
    - Total updates received
    - Number of active (unique) devices
    - Supported languages
    - Current model versions per dialect
    - Aggregation round and last aggregation time
    - Differential privacy parameters
    """
    return await _fl_service.get_status()


# ════════════════════════════════════════════════════════════════════
# Version Check — Lightweight polling for model updates
# ════════════════════════════════════════════════════════════════════


@router.get(
    "/fl/check-version/{dialect}",
    summary="Check for model updates",
    description=(
        "Lightweight version check for devices. "
        "Returns whether a newer model is available without downloading it. "
        "Devices poll this endpoint to decide when to pull the full model."
    ),
)
@router.get(
    "/federated/check-version/{dialect}",
    summary="Check for model updates (alias)",
    include_in_schema=False,
)
async def check_model_version(
    dialect: str,
    client_version: str = "v0.0.0",
    current_user=Depends(get_current_user),
) -> dict:
    """
    Check if a newer global model is available for a dialect.

    This is the push-notification mechanism: devices poll this
    lightweight endpoint. When update_available=true, the device
    triggers a full model download.

    Args:
        dialect: Language/dialect code
        client_version: Device's current model version (query param)

    Returns:
        Dict with update_available, latest_version, download_url
    """
    return await _fl_service.check_version(dialect, client_version)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def _parse_kotlin_payload(data: dict) -> FLUpdate:
    """
    Parse a Kotlin-serialized FederatedUpload into FLUpdate.

    The Android client uses camelCase field names (Kotlin serialization).
    This function maps them to Python's snake_case.
    """
    from app.schemas.federated_learning import (
        AnonymizedPattern,
        CalibrationParams,
        UploadMetadata,
    )

    # Map camelCase → snake_case
    patterns = []
    for p in data.get("correctionPatterns", []):
        patterns.append(
            AnonymizedPattern(
                error_type=p.get("errorType", ""),
                error_hash=p.get("errorHash", ""),
                correction_hash=p.get("correctionHash", ""),
                phoneme_pattern=p.get("phonemePattern", ""),
                hour_of_day=p.get("hourOfDay", 12),
                edit_distance=p.get("editDistance", 0.5),
            )
        )

    cal_params = None
    cp = data.get("calibrationParams")
    if cp:
        cal_params = CalibrationParams(
            temperature=cp.get("temperature", 1.0),
            platt_a=cp.get("plattA", 0.0),
            platt_b=cp.get("plattB", 0.0),
            prior=cp.get("prior", 0.5),
        )

    meta = None
    m = data.get("metadata")
    if m:
        meta = UploadMetadata(
            corrections_count=m.get("correctionsCount", 0),
            vocabulary_size=m.get("vocabularySize", 0),
            estimated_wer=m.get("estimatedWer", 0.0),
            device_tier=m.get("deviceTier", "basic"),
        )

    return FLUpdate(
        device_id=data.get("deviceId", ""),
        language=data.get("language", "sw"),
        timestamp=data.get("timestamp", 0),
        correction_patterns=patterns,
        adapter_deltas=data.get("adapterDeltas"),
        calibration_params=cal_params,
        metadata=meta,
    )
