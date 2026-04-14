"""Logging setup for Edge device — stdout + rotating file."""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_PATH  = os.getenv("LOG_PATH",  "/app/data/edge.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
FMT      = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging():
    """Call once at startup."""
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    handlers = [logging.StreamHandler()]
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(logging.Formatter(FMT, DATE_FMT))
        handlers.append(fh)
    except OSError:
        pass  # no /app/data outside Docker — stdout only
    logging.basicConfig(level=level, format=FMT, datefmt=DATE_FMT, handlers=handlers, force=True)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
