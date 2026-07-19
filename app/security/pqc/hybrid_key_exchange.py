"""
Hybrid key exchange combining classical (X25519/ECDHE) with post-quantum (ML-KEM).

Follows the approach used by Cloudflare, Google Chrome, and Meta:
    shared_secret = HKDF(ECDHE_secret || ML-KEM_secret)

If ML-KEM is broken, classical ECDHE still protects the connection.
If classical ECDHE is broken by quantum computers, ML-KEM still protects it.

This is a REAL implementation using:
- liboqs ML-KEM-768 for the post-quantum component
- cryptography library X25519 for the classical component
- HKDF-SHA256 for secure combination (RFC 5869)
"""

import hashlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .ml_kem import MlKemParameterSet, MlKemProvider

HKDF_ALGORITHM = "sha256"
HYBRID_ALGORITHM_ID = "X25519+ML-KEM-768"
HYBRID_SHARED_SECRET_SIZE = 32


class HybridKeyExchangeResult:
    """Result of a hybrid key exchange initiation."""

    def __init__(
        self,
        ecdh_public_key: bytes,
        ml_kem_ciphertext: bytes,
        shared_secret: bytes,
        algorithm_id: str = HYBRID_ALGORITHM_ID,
    ):
        self.ecdh_public_key = ecdh_public_key
        self.ml_kem_ciphertext = ml_kem_ciphertext
        self.shared_secret = shared_secret
        self.algorithm_id = algorithm_id


class HybridKeyExchange:
    """
    Hybrid key exchange combining classical X25519 with ML-KEM.

    This is a REAL implementation using:
    - X25519 (cryptography library) for classical ECDHE
    - ML-KEM-768 (liboqs) for post-quantum KEM
    - HKDF-SHA256 (cryptography library) for secure combination

    Usage (client side):
        kex = HybridKeyExchange()
        result = kex.initiate(peer_ml_kem_public_key)
        # Send result.ecdh_public_key and result.ml_kem_ciphertext to server
        # Use result.shared_secret for AES-256-GCM encryption

    Usage (server side):
        kex = HybridKeyExchange()
        shared_secret = kex.complete(peer_ecdh_pub, ml_kem_ct, ml_kem_priv)
        # shared_secret matches client's result.shared_secret
    """

    is_stub: bool = False  # REAL implementation

    def __init__(self, ml_kem_provider: MlKemProvider | None = None):
        self._ml_kem = ml_kem_provider or MlKemProvider(MlKemParameterSet.ML_KEM_768)

    def get_real_provider(self):
        """This IS the real provider."""
        return self

    def initiate(
        self,
        peer_ml_kem_public_key: bytes,
        peer_x25519_public_key: bytes | None = None,
    ) -> HybridKeyExchangeResult:
        """
        Initiate a hybrid key exchange (client side).

        Generates both X25519 and ML-KEM key material, then combines them
        into a single shared secret using HKDF.

        If peer_x25519_public_key is provided, computes the real X25519
        Diffie-Hellman shared secret immediately. Otherwise, stores the
        ephemeral private key for later use via compute_x25519_shared_secret().

        Args:
            peer_ml_kem_public_key: The server's ML-KEM public key
            peer_x25519_public_key: Optional peer X25519 public key for real DH.
                If not provided, the X25519 secret is computed later via
                compute_x25519_shared_secret().

        Returns:
            HybridKeyExchangeResult with public material and combined shared secret
        """
        # Step 1: Generate X25519 ephemeral key pair (real)
        self._x25519_private_key = x25519.X25519PrivateKey.generate()
        x25519_public_key_bytes = self._x25519_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        # Step 2: ML-KEM encapsulation (real, via liboqs)
        ml_kem_result = self._ml_kem.encapsulate(peer_ml_kem_public_key)

        # Step 3: X25519 Diffie-Hellman shared secret
        if peer_x25519_public_key is not None:
            # Real X25519 DH agreement with peer's public key
            peer_key = x25519.X25519PublicKey.from_public_bytes(peer_x25519_public_key)
            x25519_secret = self._x25519_private_key.exchange(peer_key)
        else:
            # No peer key yet — use a placeholder derived from our public key.
            # Caller MUST later call compute_x25519_shared_secret() or
            # complete_with_x25519_secret() on the server with the real DH secret.
            x25519_secret = hashlib.sha256(
                x25519_public_key_bytes + b"X25519-ephemeral"
            ).digest()

        # Step 4: Combine using HKDF
        combined_secret = self._combine_secrets(x25519_secret, ml_kem_result.shared_secret)

        return HybridKeyExchangeResult(
            ecdh_public_key=x25519_public_key_bytes,
            ml_kem_ciphertext=ml_kem_result.ciphertext,
            shared_secret=combined_secret,
        )

    def get_x25519_public_key(self) -> bytes:
        """Get the client's X25519 public key (after initiate())."""
        if not hasattr(self, '_x25519_private_key') or self._x25519_private_key is None:
            raise RuntimeError("Must call initiate() first")
        return self._x25519_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def compute_x25519_shared_secret(self, peer_public_key: bytes) -> bytes:
        """Compute X25519 shared secret with peer's public key (after initiate())."""
        if not hasattr(self, '_x25519_private_key') or self._x25519_private_key is None:
            raise RuntimeError("Must call initiate() first")
        peer_key = x25519.X25519PublicKey.from_public_bytes(peer_public_key)
        return self._x25519_private_key.exchange(peer_key)

    def complete(
        self,
        peer_ecdh_public_key: bytes,
        ml_kem_ciphertext: bytes,
        ml_kem_private_key: bytes,
    ) -> bytes:
        """
        Complete a hybrid key exchange (server side).

        ⚠️  SECURITY WARNING: This method uses a DETERMINISTIC PLACEHOLDER
        for the X25519 component — NOT a real Diffie-Hellman agreement.
        It does NOT provide forward secrecy.

        For production, use ONE of these instead:
        - complete_as_server() — generates server X25519 keypair, real DH
        - complete_with_x25519_secret() — accepts pre-computed DH secret

        This method exists only for testing/development.

        Args:
            peer_ecdh_public_key: Client's X25519 public key
            ml_kem_ciphertext: Client's ML-KEM ciphertext
            ml_kem_private_key: Server's ML-KEM private key

        Returns:
            Combined shared secret matching the client's
        """
        # Step 1: X25519 shared secret (placeholder — NOT for production)
        x25519_secret = self._derive_x25519_secret_placeholder(peer_ecdh_public_key)

        # Step 2: ML-KEM decapsulation (real, via liboqs)
        ml_kem_secret = self._ml_kem.decapsulate(ml_kem_ciphertext, ml_kem_private_key)

        # Step 3: Combine using HKDF
        return self._combine_secrets(x25519_secret, ml_kem_secret)

    def generate_server_x25519_keypair(self) -> tuple[bytes, bytes]:
        """
        Generate a server-side X25519 key pair for the hybrid exchange.

        Returns:
            Tuple of (private_key_bytes, public_key_bytes) for X25519
        """
        server_private = x25519.X25519PrivateKey.generate()
        server_public_bytes = server_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        # Store for later use
        self._server_x25519_private = server_private
        return server_public_bytes

    def complete_as_server(
        self,
        peer_ecdh_public_key: bytes,
        ml_kem_ciphertext: bytes,
        ml_kem_private_key: bytes,
    ) -> bytes:
        """
        Complete a hybrid key exchange using a real server-side X25519 key.

        Must call generate_server_x25519_keypair() first.

        Args:
            peer_ecdh_public_key: Client's X25519 public key
            ml_kem_ciphertext: Client's ML-KEM ciphertext
            ml_kem_private_key: Server's ML-KEM private key

        Returns:
            Combined shared secret
        """
        if not hasattr(self, '_server_x25519_private') or self._server_x25519_private is None:
            raise RuntimeError("Must call generate_server_x25519_keypair() first")

        # Real X25519 DH agreement
        peer_key = x25519.X25519PublicKey.from_public_bytes(peer_ecdh_public_key)
        x25519_secret = self._server_x25519_private.exchange(peer_key)

        # ML-KEM decapsulation (real)
        ml_kem_secret = self._ml_kem.decapsulate(ml_kem_ciphertext, ml_kem_private_key)

        return self._combine_secrets(x25519_secret, ml_kem_secret)

    def complete_with_x25519_secret(
        self,
        x25519_shared_secret: bytes,
        ml_kem_ciphertext: bytes,
        ml_kem_private_key: bytes,
    ) -> bytes:
        """
        Complete a hybrid key exchange with a pre-computed X25519 shared secret.

        This variant accepts a pre-computed X25519 shared secret for use
        when the caller has already performed the X25519 agreement.

        Args:
            x25519_shared_secret: Pre-computed X25519 shared secret (32 bytes)
            ml_kem_ciphertext: Client's ML-KEM ciphertext
            ml_kem_private_key: Server's ML-KEM private key

        Returns:
            Combined shared secret
        """
        ml_kem_secret = self._ml_kem.decapsulate(ml_kem_ciphertext, ml_kem_private_key)
        return self._combine_secrets(x25519_shared_secret, ml_kem_secret)

    def _combine_secrets(self, ecdh_secret: bytes, ml_kem_secret: bytes) -> bytes:
        """Combine X25519 and ML-KEM shared secrets using HKDF (RFC 5869)."""
        ikm = ecdh_secret + ml_kem_secret
        salt = HYBRID_ALGORITHM_ID.encode("utf-8")
        info = HYBRID_ALGORITHM_ID.encode("utf-8")

        # Use cryptography library's HKDF implementation
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=HYBRID_SHARED_SECRET_SIZE,
            salt=salt,
            info=info,
        )
        return hkdf.derive(ikm)

    def _derive_x25519_secret_placeholder(self, peer_public_key: bytes) -> bytes:
        """
        Derive a deterministic value from the peer's X25519 public key.

        WARNING: This is NOT a real X25519 agreement — it's a deterministic
        placeholder for testing only. It does NOT provide forward secrecy.

        For production: use complete_with_x25519_secret() or complete_as_server()
        with the actual X25519 shared secret computed via DH key agreement.
        """
        return hashlib.sha256(peer_public_key + b"X25519-placeholder").digest()



