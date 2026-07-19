"""
Algorithm-agnostic cryptography provider interface.

Core of crypto-agility: all cryptographic operations go through this interface,
allowing algorithm swaps without changing calling code.

Designed for post-quantum migration — implementations can switch between
classical (AES-256-GCM, RSA, ECDSA) and post-quantum (ML-KEM, ML-DSA)
algorithms transparently.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CryptoKeyPair:
    """A cryptographic key pair."""
    public_key: bytes
    private_key: bytes
    algorithm_id: str


@dataclass
class EncapsulatedKey:
    """Result of a key encapsulation mechanism (KEM) operation."""
    ciphertext: bytes  # Send to peer
    shared_secret: bytes  # Derived shared secret
    algorithm_id: str


class CryptoProvider(ABC):
    """Algorithm-agnostic cryptography provider interface."""

    @property
    @abstractmethod
    def algorithm_id(self) -> str:
        """Unique identifier for this provider (e.g., 'AES-256-GCM', 'ML-KEM-768')."""
        ...

    @property
    @abstractmethod
    def is_post_quantum(self) -> bool:
        """Whether this algorithm is post-quantum resistant."""
        ...

    @property
    @abstractmethod
    def is_stub(self) -> bool:
        """Whether this is a STUB implementation (not real cryptography)."""
        ...

    @property
    @abstractmethod
    def security_level(self) -> int:
        """Security level (1-5, matching NIST levels)."""
        ...

    @abstractmethod
    def get_real_provider(self) -> "CryptoProvider | None":
        """Return a real (non-stub) provider if available, else None.
        
        Callers MUST check is_stub before using this provider for
        actual security. If is_stub is True and get_real_provider()
        returns None, the system MUST fall back to AES-256-GCM.
        """
        ...

    @abstractmethod
    def generate_key_pair(self) -> CryptoKeyPair:
        """Generate a key pair (asymmetric) or key (symmetric)."""
        ...

    @abstractmethod
    def encrypt(self, plaintext: bytes, key: bytes) -> bytes:
        """Encrypt data."""
        ...

    @abstractmethod
    def decrypt(self, ciphertext: bytes, key: bytes) -> bytes:
        """Decrypt data."""
        ...

    @abstractmethod
    def sign(self, data: bytes, private_key: bytes) -> bytes:
        """Sign data (asymmetric algorithms only)."""
        ...

    @abstractmethod
    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """Verify a signature."""
        ...


class KeyEncapsulationProvider(ABC):
    """Interface for key encapsulation mechanisms (KEM)."""

    @property
    @abstractmethod
    def algorithm_id(self) -> str:
        ...

    @property
    @abstractmethod
    def is_post_quantum(self) -> bool:
        ...

    @property
    @abstractmethod
    def is_stub(self) -> bool:
        """Whether this is a STUB implementation (not real cryptography)."""
        ...

    @property
    @abstractmethod
    def security_level(self) -> int:
        ...

    @abstractmethod
    def generate_key_pair(self) -> CryptoKeyPair:
        ...

    @abstractmethod
    def encapsulate(self, public_key: bytes) -> EncapsulatedKey:
        """Encapsulate: generate shared secret for a public key."""
        ...

    @abstractmethod
    def decapsulate(self, ciphertext: bytes, private_key: bytes) -> bytes:
        """Decapsulate: recover shared secret from ciphertext."""
        ...
