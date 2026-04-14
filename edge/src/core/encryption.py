"""
AES-256-GCM encryption for face embeddings — Edge device side.
Key must match the Cloud backend AES_KEY setting.
"""
import os
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from edge.src.config import config


def _get_key() -> bytes:
    key_hex = config.AES_KEY
    if not key_hex:
        raise RuntimeError("AES_KEY is not configured. Set AES_KEY in device.env")
    return bytes.fromhex(key_hex)


def encrypt_embedding(embedding: np.ndarray) -> bytes:
    """Encrypt a 512-dim float32 numpy array → bytes (nonce + ciphertext + tag)."""
    raw = embedding.astype(np.float32).tobytes()
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
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-10)
