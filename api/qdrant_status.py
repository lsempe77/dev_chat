"""Qdrant connection status tracking and warmup helpers."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.ingestion.indexer import QdrantIndexer
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class QdrantConnectionState:
    """Simple container for Qdrant connection health."""

    healthy: bool = False
    last_checked: Optional[datetime] = None
    last_error: Optional[str] = None
    connecting: bool = False


_state = QdrantConnectionState()
_state_lock = asyncio.Lock()


async def _update_state(*, healthy: bool, error: Optional[str], connecting: Optional[bool] = None) -> None:
    """Update connection state while holding the lock."""
    async with _state_lock:
        _state.healthy = healthy
        _state.last_checked = datetime.utcnow()
        _state.last_error = error
        if connecting is not None:
            _state.connecting = connecting


def _check_qdrant_connection() -> bool:
    """Run the blocking Qdrant connection attempt in a worker thread."""
    indexer = QdrantIndexer()
    info = indexer.get_collection_info()
    if info and "error" not in info:
        return True
    raise RuntimeError(info.get("error", "Unknown Qdrant error"))


async def warm_up_qdrant_connection() -> None:
    """Start connecting to Qdrant without blocking startup or health checks."""
    async with _state_lock:
        if _state.connecting:
            logger.debug("Qdrant warmup already in progress; skipping")
            return
        _state.connecting = True

    try:
        await asyncio.to_thread(_check_qdrant_connection)
    except Exception as exc:  # noqa: BLE001 - surface warmup failures
        logger.warning(f"Qdrant warmup failed: {exc}")
        await _update_state(healthy=False, error=str(exc), connecting=False)
    else:
        logger.info("Qdrant connection established during warmup")
        await _update_state(healthy=True, error=None, connecting=False)


async def mark_qdrant_healthy() -> None:
    """Mark Qdrant as healthy based on a successful query."""
    await _update_state(healthy=True, error=None)


async def get_qdrant_status_snapshot() -> QdrantConnectionState:
    """Return a copy of the current Qdrant connection state."""
    async with _state_lock:
        return QdrantConnectionState(
            healthy=_state.healthy,
            last_checked=_state.last_checked,
            last_error=_state.last_error,
            connecting=_state.connecting,
        )
