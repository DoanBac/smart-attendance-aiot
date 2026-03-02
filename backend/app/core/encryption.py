"""
AES-256-GCM encryption for face embeddings.
Key is never stored alongside the data.
"""
import os
import struct
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings

def _get_key() -> bytes:
    key_hex = settings.AES_KEY
    return bytes.fromhex(key_hex)

def encrypt_embedding(embedding: np.ndarray) -> bytes:
    """Encrypt a 512-dim float32 numpy array → bytes (nonce + ciphertext + tag)."""
    raw = embedding.astype(np.float32).tobytes()  # 512 * 4 = 2048 bytes
    aesgcm = AESGCM(_get_key())
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, raw, None)
    return nonce + ciphertext  # prepend nonce for storage

def decrypt_embedding(data: bytes) -> np.ndarray:
    """Decrypt Cloud-encrypted embedding → 512-dim float32 L2-normalized vector."""
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(_get_key())
    raw = aesgcm.decrypt(nonce, ciphertext, None)
    vec = np.frombuffer(raw, dtype=np.float32).copy()
    # Re-normalize after decryption
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-10)