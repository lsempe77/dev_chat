"""
DevChat v2.0 SOTA - Usage Logger

Persistent logging of API usage, tokens, and costs to Supabase.
"""

import os
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import uuid4

from src.config.costs import calculate_cost, get_model_pricing
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class UsageEvent:
    """A single usage event to be logged."""
    event_type: str  # 'query', 'embed', 'rerank', 'llm', 'metadata_enrichment'
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: Optional[int] = None
    
    # Context
    user_id: Optional[str] = None
    rag_project_id: Optional[str] = None
    query_text: Optional[str] = None
    query_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Auto-populated
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provider: Optional[str] = None
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Calculate cost and provider after initialization."""
        if self.cost_usd == Decimal("0"):
            self.cost_usd = calculate_cost(self.model, self.input_tokens, self.output_tokens)
        
        if self.provider is None:
            pricing = get_model_pricing(self.model)
            if pricing:
                self.provider = pricing.provider


class UsageLogger:
    """
    Logs usage events to Supabase usage_logs table.
    
    Features:
    - Async batch logging for performance
    - Fallback to in-memory if DB unavailable
    - Cost calculation on write
    """
    
    def __init__(self, batch_size: int = 10, flush_interval_seconds: float = 5.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval_seconds
        self._buffer: List[UsageEvent] = []
        self._supabase = None
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # In-memory fallback when DB is unavailable
        self._memory_log: List[UsageEvent] = []
        self._max_memory_log = 1000
    
    def _get_supabase(self):
        """Lazy-load Supabase client."""
        if self._supabase is None:
            try:
                from supabase import create_client
                url = os.environ.get("SUPABASE_URL", "")
                key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
                if url and key:
                    self._supabase = create_client(url, key)
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase for usage logging: {e}")
        return self._supabase
    
    async def log(self, event: UsageEvent) -> None:
        """
        Log a usage event.
        
        Events are buffered and flushed in batches for performance.
        """
        async with self._lock:
            self._buffer.append(event)
            
            if len(self._buffer) >= self.batch_size:
                await self._flush()
    
    def log_sync(self, event: UsageEvent) -> None:
        """
        Synchronous log method for non-async contexts.
        
        Stores in buffer; actual DB write happens on next flush.
        """
        self._buffer.append(event)
        
        if len(self._buffer) >= self.batch_size:
            # Schedule flush for later
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._flush())
                else:
                    loop.run_until_complete(self._flush())
            except RuntimeError:
                # No event loop - store in memory
                self._store_in_memory(self._buffer)
                self._buffer = []
    
    async def _flush(self) -> None:
        """Flush buffered events to database."""
        if not self._buffer:
            return
        
        events_to_flush = self._buffer
        self._buffer = []
        
        supabase = self._get_supabase()
        if supabase is None:
            self._store_in_memory(events_to_flush)
            return
        
        try:
            # Convert events to dictionaries for insertion
            rows = []
            for event in events_to_flush:
                row = {
                    "id": event.id,
                    "created_at": event.created_at.isoformat(),
                    "user_id": event.user_id,
                    "rag_project_id": event.rag_project_id,
                    "event_type": event.event_type,
                    "provider": event.provider,
                    "model": event.model,
                    "input_tokens": event.input_tokens,
                    "output_tokens": event.output_tokens,
                    "cost_usd": float(event.cost_usd),
                    "latency_ms": event.latency_ms,
                    "metadata": event.metadata,
                    "query_text": event.query_text[:500] if event.query_text else None,  # Truncate
                    "query_id": event.query_id,
                    "session_id": event.session_id,
                }
                rows.append(row)
            
            # Batch insert
            supabase.table("usage_logs").insert(rows).execute()
            logger.debug(f"Flushed {len(rows)} usage events to database")
            
        except Exception as e:
            logger.error(f"Failed to flush usage logs to database: {e}")
            self._store_in_memory(events_to_flush)
    
    def _store_in_memory(self, events: List[UsageEvent]) -> None:
        """Store events in memory as fallback."""
        self._memory_log.extend(events)
        if len(self._memory_log) > self._max_memory_log:
            self._memory_log = self._memory_log[-self._max_memory_log:]
        logger.warning(f"Stored {len(events)} events in memory (DB unavailable)")
    
    async def start_periodic_flush(self) -> None:
        """Start periodic flush task."""
        if self._flush_task is not None:
            return
        
        async def periodic_flush():
            while True:
                await asyncio.sleep(self.flush_interval)
                async with self._lock:
                    await self._flush()
        
        self._flush_task = asyncio.create_task(periodic_flush())
    
    async def flush(self) -> None:
        """Public method to force flush buffered events."""
        async with self._lock:
            await self._flush()
    
    async def stop(self) -> None:
        """Stop periodic flush and flush remaining events."""
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        
        async with self._lock:
            await self._flush()
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Get summary of in-memory events (for debugging/fallback)."""
        if not self._memory_log:
            return {"count": 0}
        
        total_cost = sum(e.cost_usd for e in self._memory_log)
        total_input = sum(e.input_tokens for e in self._memory_log)
        total_output = sum(e.output_tokens for e in self._memory_log)
        
        by_type = {}
        for e in self._memory_log:
            if e.event_type not in by_type:
                by_type[e.event_type] = 0
            by_type[e.event_type] += 1
        
        return {
            "count": len(self._memory_log),
            "total_cost_usd": float(total_cost),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "by_event_type": by_type,
        }


# Global usage logger instance
_usage_logger: Optional[UsageLogger] = None


def get_usage_logger() -> UsageLogger:
    """Get the global usage logger instance."""
    global _usage_logger
    if _usage_logger is None:
        _usage_logger = UsageLogger()
    return _usage_logger


# Convenience functions for common logging patterns

async def log_llm_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    user_id: Optional[str] = None,
    rag_project_id: Optional[str] = None,
    query_text: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> None:
    """Log an LLM call."""
    event = UsageEvent(
        event_type="llm",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        user_id=user_id,
        rag_project_id=rag_project_id,
        query_text=query_text,
        metadata=metadata or {},
    )
    await get_usage_logger().log(event)


async def log_embedding_call(
    model: str,
    input_tokens: int,
    latency_ms: int,
    num_texts: int,
    user_id: Optional[str] = None,
    rag_project_id: Optional[str] = None,
) -> None:
    """Log an embedding call."""
    event = UsageEvent(
        event_type="embed",
        model=model,
        input_tokens=input_tokens,
        output_tokens=0,
        latency_ms=latency_ms,
        user_id=user_id,
        rag_project_id=rag_project_id,
        metadata={"num_texts": num_texts},
    )
    await get_usage_logger().log(event)


async def log_rerank_call(
    model: str,
    input_tokens: int,
    latency_ms: int,
    num_documents: int,
    user_id: Optional[str] = None,
    rag_project_id: Optional[str] = None,
) -> None:
    """Log a rerank call."""
    event = UsageEvent(
        event_type="rerank",
        model=model,
        input_tokens=input_tokens,
        output_tokens=0,
        latency_ms=latency_ms,
        user_id=user_id,
        rag_project_id=rag_project_id,
        metadata={"num_documents": num_documents},
    )
    await get_usage_logger().log(event)


async def log_query(
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    query_text: str,
    user_id: Optional[str] = None,
    rag_project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    query_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> None:
    """Log a complete query (synthesis)."""
    event = UsageEvent(
        event_type="query",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        user_id=user_id,
        rag_project_id=rag_project_id,
        query_text=query_text,
        session_id=session_id,
        query_id=query_id,
        metadata=metadata or {},
    )
    await get_usage_logger().log(event)
