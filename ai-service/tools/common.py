from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TOOLS_DIR = Path(__file__).resolve().parent
AI_SERVICE_DIR = TOOLS_DIR.parent
DEFAULT_DATASET_ROOT = AI_SERVICE_DIR / "data" / "antispoof"
DEFAULT_BASE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:9000").rstrip("/")
DEFAULT_SERVICE_KEY = os.getenv(
    "AI_SERVICE_SECRET_KEY",
    "ai-service-internal-secret-change-in-prod",
)
DEFAULT_TIMEOUT = float(os.getenv("AI_SERVICE_TIMEOUT", "30"))
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def resolve_image_dir(split: str, class_name: str, dataset_root: Path | None = None) -> Path:
    root = (dataset_root or DEFAULT_DATASET_ROOT).resolve()
    return root / split / class_name / "images"


def list_image_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def extract_prediction(
    image_path: Path,
    *,
    base_url: str = DEFAULT_BASE_URL,
    service_key: str = DEFAULT_SERVICE_KEY,
    min_blur: float | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any]]:
    payload: dict[str, Any] = {
        "image_b64": base64.b64encode(image_path.read_bytes()).decode()
    }
    if min_blur is not None:
        payload["min_blur"] = min_blur

    request = Request(
        f"{base_url.rstrip('/')}/api/v1/extract",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-Service-Key": service_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        return 0, {"detail": f"Connection error: {exc.reason}"}

    try:
        data = json.loads(body)
    except Exception:
        data = {"detail": body[:500]}

    return status, data
