"""
Encryption utilities for Msaidizi backend.

Handles:
- AES-256 encryption/decryption for PII (phone numbers, names)
- SHA-256 hashing for secure lookups
- HMAC for webhook signature validation

All PII is encrypted at rest using AES-256-GCM. Phone numbers are
additionally hashed (SHA-256) for lookup purposes without decryption.
"""

import base64
import hashlib
import hmac
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import get_settings

settings = get_settings()


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit key from a passphrase using PBKDF2.

    Args:
        passphrase: The encryption passphrase
        salt: Random salt bytes

    Returns:
        32-byte derived key
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,  # OWASP recommended minimum
    )
    return kdf.derive(passphrase.encode())


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value using AES-256-GCM.

    The encrypted output includes the nonce and tag prepended
    to the ciphertext, all base64-encoded for safe storage.

    Args:
        plaintext: The value to encrypt (phone number, name, etc.)

    Returns:
        Base64-encoded encrypted string
    """
    if not plaintext:
        return ""

    key = settings.ENCRYPTION_KEY.encode()[:32].ljust(32, b"\0")
    nonce = os.urandom(12)  # 96-bit nonce for GCM

    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce))
    encryptor = cipher.encryptor()

    ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()

    # Combine nonce + tag + ciphertext
    combined = nonce + encryptor.tag + ciphertext
    return base64.b64encode(combined).decode()


def decrypt_value(encrypted: str) -> str:
    """
    Decrypt a value encrypted with encrypt_value.

    Args:
        encrypted: Base64-encoded encrypted string

    Returns:
        Decrypted plaintext string

    Raises:
        ValueError: If decryption fails (wrong key, corrupted data)
    """
    if not encrypted:
        return ""

    key = settings.ENCRYPTION_KEY.encode()[:32].ljust(32, b"\0")
    combined = base64.b64decode(encrypted)

    nonce = combined[:12]
    tag = combined[12:28]
    ciphertext = combined[28:]

    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
    decryptor = cipher.decryptor()

    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return plaintext.decode()


def hash_phone(phone: str) -> str:
    """
    Create a SHA-256 hash of a phone number for secure lookups.

    This allows matching phone numbers without decrypting them.
    Used for the phone_hash column in the users table.

    Args:
        phone: Phone number string

    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(phone.encode()).hexdigest()


def hash_value(value: str, salt: Optional[str] = None) -> str:
    """
    Create a salted SHA-256 hash of any value.

    Args:
        value: Value to hash
        salt: Optional salt (defaults to config salt)

    Returns:
        Hex-encoded salted hash
    """
    if salt is None:
        salt = settings.DATA_ENCRYPTION_SALT
    return hashlib.sha256(f"{salt}{value}".encode()).hexdigest()


def create_hmac_signature(payload: bytes, secret: str) -> str:
    """
    Create HMAC-SHA256 signature for webhook payloads.

    Args:
        payload: Raw payload bytes
        secret: HMAC secret key

    Returns:
        Hex-encoded HMAC signature
    """
    return hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_hmac_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify an HMAC-SHA256 signature.

    Args:
        payload: Raw payload bytes
        signature: Signature to verify
        secret: HMAC secret key

    Returns:
        True if signature is valid
    """
    expected = create_hmac_signature(payload, secret)
    return hmac.compare_digest(signature, expected)


def encrypt_payload(data: bytes) -> bytes:
    """
    Encrypt a binary payload (e.g., sync data from device).

    Uses Fernet (AES-128-CBC with HMAC-SHA256) for simplicity
    and authenticated encryption.

    Args:
        data: Raw bytes to encrypt

    Returns:
        Encrypted bytes (base64-encoded internally by Fernet)
    """
    key = settings.ENCRYPTION_KEY.encode()[:32].ljust(32, b"\0")
    # Fernet requires a URL-safe base64-encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(key)
    f = Fernet(fernet_key)
    return f.encrypt(data)


def decrypt_payload(encrypted_data: bytes) -> bytes:
    """
    Decrypt a payload encrypted with encrypt_payload.

    Args:
        encrypted_data: Encrypted bytes

    Returns:
        Decrypted raw bytes

    Raises:
        InvalidToken: If decryption fails
    """
    key = settings.ENCRYPTION_KEY.encode()[:32].ljust(32, b"\0")
    fernet_key = base64.urlsafe_b64encode(key)
    f = Fernet(fernet_key)
    return f.decrypt(encrypted_data)


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key with prefix and hash.

    Returns:
        Tuple of (full_key, key_hash, key_prefix)
    """
    import secrets
    full_key = f"msai_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:10]
    return full_key, key_hash, key_prefix
