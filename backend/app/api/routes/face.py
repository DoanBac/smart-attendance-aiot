"""
Face Embedding Sync API — for Edge Devices
==========================================
Edge device calls GET /api/face/embeddings with X-Device-Token
to download AES-256-GCM encrypted embeddings for offline recognition.

Response format (per edge/src/sync/queue_sync.py expectation):
  [{student_id, student_code, full_name, embedding_enc}]
  where embedding_enc is base64-encoded bytes of the encrypted blob.
"""
import base64
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.device import Device
from app.models.student import Student
from app.models.enrollment import StudentEnrollment
from app.core.security import verify_device_token

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response schema ────────────────────────────────────────────────────────── #

class EmbeddingEntry(BaseModel):
    student_id:    UUID
    student_code:  str
    full_name:     str
    embedding_enc: str   # base64-encoded AES-256-GCM blob


# ── Endpoint ──────────────────────────────────────────────────────────────── #

@router.get(
    "/embeddings",
    response_model=List[EmbeddingEntry],
    summary="Download encrypted face embeddings (edge device only)",
    description=(
        "Returns AES-256-GCM encrypted face embeddings for all students "
        "enrolled in the device's assigned class. "
        "Auth: X-Device-Token header."
    ),
)
async def get_embeddings_for_device(
    db:     AsyncSession = Depends(get_db),
    device: Device       = Depends(verify_device_token),
):
    """
    Edge device calls this once at startup / on schedule to sync
    the local SQLite embedding store for offline face recognition.
    """
    if device.class_id is None:
        raise HTTPException(
            status_code=400,
            detail="Device has no class assigned — cannot fetch embeddings.",
        )

    # ── Students enrolled in this class with a stored embedding ─────────── #
    result = await db.execute(
        select(Student)
        .join(
            StudentEnrollment,
            (StudentEnrollment.student_id == Student.id)
            & (StudentEnrollment.class_id == device.class_id)
            & (StudentEnrollment.status == "active"),
        )
        .where(Student.face_embedding.isnot(None))
        .where(Student.status == "active")
    )
    students: List[Student] = result.scalars().all()

    logger.info(
        f"[FACE/EMBEDDINGS] device_id={device.id} class_id={device.class_id} "
        f"→ {len(students)} embedding(s)"
    )

    return [
        EmbeddingEntry(
            student_id=s.id,
            student_code=s.student_code,
            full_name=s.full_name,
            embedding_enc=base64.b64encode(s.face_embedding).decode(),
        )
        for s in students
    ]
