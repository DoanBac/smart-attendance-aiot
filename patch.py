with open("backend/app/services/attendance_service.py", "r") as f:
    text = f.read()

idx_step2 = text.find("    # ── Step 2:")
idx_end = text.find("async def get_class_attendance")

step2_code = text[idx_step2:idx_end]

# indent it properly or use it directly
new_func = """
async def verify_sequence_and_log(
    db: AsyncSession,
    images_b64: List[str],
    class_id: UUID,
    device_id: Optional[int] = None,
) -> dict:
    from app.services.ai_client import ai_extract_burst
    from app.services.face_service import identify_face
    
    try:
        embedding, quality, meta = await ai_extract_burst(images_b64)
    except ValueError as e:
        return {"matched": False, "status": "liveness_failed", "message": str(e), "confidence": 0.0}
    except RuntimeError as e:
        logger.error(f"[KIOSK] AI service error during burst extract: {e}")
        return {"matched": False, "status": "error", "message": "AI service unavailable", "confidence": 0.0}

""" + step2_code

text = text[:idx_end] + new_func + text[idx_end:]

with open("backend/app/services/attendance_service.py", "w") as f:
    f.write(text)
