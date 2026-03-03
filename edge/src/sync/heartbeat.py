"""
Heartbeat — re-exports send_heartbeat from queue_sync.
Kept separate for future richer telemetry payloads.
"""
from edge.src.sync.queue_sync import send_heartbeat  # noqa: F401

__all__ = ["send_heartbeat"]
