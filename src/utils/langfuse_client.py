"""
DevChat v2.0 SOTA - Langfuse Observability (v3 SDK)

Provides tracing and observability for LLM calls, embeddings, and retrieval.
Uses Langfuse SDK v3 API with start_as_current_span context managers.
"""

import os
from functools import wraps
from typing import Optional, Any, Dict
from contextlib import contextmanager

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Lazy-loaded Langfuse client
_langfuse_client = None
_langfuse_enabled = None


def is_langfuse_enabled() -> bool:
    """Check if Langfuse is configured and enabled."""
    global _langfuse_enabled
    if _langfuse_enabled is None:
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        _langfuse_enabled = bool(secret_key and public_key)
        if _langfuse_enabled:
            logger.info("Langfuse observability enabled")
        else:
            logger.debug("Langfuse not configured (missing keys)")
    return _langfuse_enabled


def get_langfuse():
    """Get or create the Langfuse client (lazy initialization)."""
    global _langfuse_client
    
    if not is_langfuse_enabled():
        return None
    
    if _langfuse_client is None:
        try:
            from langfuse import Langfuse
            _langfuse_client = Langfuse(
                secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
                public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
                host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
            logger.info("Langfuse client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Langfuse: {e}")
            return None
    
    return _langfuse_client


def flush_langfuse():
    """Flush any pending Langfuse events."""
    client = get_langfuse()
    if client:
        try:
            client.flush()
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse: {e}")


# Store the current root span for adding child spans
_current_root_span = None


def create_trace(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
    input_data: Optional[str] = None,
):
    """
    Create a Langfuse trace/span for manual management (useful in async code).
    
    In v3 SDK, we use start_span() which creates a trace automatically.
    Returns a span object or None if Langfuse is not enabled.
    
    Usage:
        trace = create_trace("chat", input_data=query)
        # Do async work...
        if trace:
            trace.update(output=answer)
            trace.end()
            flush_langfuse()
    """
    global _current_root_span
    client = get_langfuse()
    if not client:
        return None
    
    try:
        # Create a root span (which creates a trace in v3)
        span = client.start_span(
            name=name,
            input=input_data[:2000] if input_data else None,
            metadata={
                "user_id": user_id,
                "session_id": session_id,
                "tags": tags or [],
                **(metadata or {}),
            },
        )
        _current_root_span = span
        return span
    except Exception as e:
        logger.warning(f"Failed to create Langfuse trace: {e}")
        return None


def add_generation_to_trace(
    trace,
    name: str,
    model: str,
    input_text: Optional[str] = None,
    output_text: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Add an LLM generation observation to the current trace.
    
    In v3 SDK, we use start_observation(as_type='generation').
    """
    client = get_langfuse()
    if not client:
        return None
    
    try:
        gen = client.start_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input_text[:2000] if input_text else None,
            metadata={
                "latency_ms": latency_ms,
                **(metadata or {}),
            },
        )
        gen.update(
            output=output_text[:4000] if output_text else None,
            usage={
                "input": input_tokens,
                "output": output_tokens,
            },
        )
        gen.end()
        return gen
    except Exception as e:
        logger.warning(f"Failed to add generation to trace: {e}")
        return None


def add_span_to_trace(
    trace,
    name: str,
    input_data: Optional[str] = None,
    output_data: Optional[Any] = None,
    latency_ms: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Add a span to the current trace (for retrieval, reranking, etc.).
    """
    client = get_langfuse()
    if not client:
        return None
    
    try:
        span = client.start_span(
            name=name,
            input=input_data[:1000] if input_data else None,
            metadata={
                "latency_ms": latency_ms,
                **(metadata or {}),
            },
        )
        span.update(output=output_data)
        span.end()
        return span
    except Exception as e:
        logger.warning(f"Failed to add span to trace: {e}")
        return None


@contextmanager
def langfuse_trace(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
):
    """
    Context manager for creating a Langfuse trace.
    
    Usage:
        with langfuse_trace("query", user_id="user123") as trace:
            # Do work
            trace.update(output="result")
    """
    client = get_langfuse()
    if not client:
        # Yield a dummy object that does nothing
        class DummySpan:
            def update(self, **kwargs): pass
            def end(self): pass
        yield DummySpan()
        return
    
    try:
        with client.start_as_current_span(
            name=name,
            metadata={
                "user_id": user_id,
                "session_id": session_id,
                "tags": tags or [],
                **(metadata or {}),
            },
        ) as span:
            yield span
    except Exception as e:
        logger.warning(f"Langfuse trace error: {e}")
        class DummySpan:
            def update(self, **kwargs): pass
            def end(self): pass
        yield DummySpan()


def observe_llm(
    name: str = "llm_call",
    model: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Decorator to observe LLM calls with Langfuse.
    
    Usage:
        @observe_llm("synthesis", model="gpt-4o-mini")
        async def synthesize(query: str, context: str) -> str:
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            client = get_langfuse()
            if not client:
                return await func(*args, **kwargs)
            
            import time
            start_time = time.time()
            
            try:
                # Create generation observation
                gen = client.start_observation(
                    as_type="generation",
                    name=name,
                    model=model,
                    metadata=metadata or {},
                    input=str(kwargs.get("query", kwargs.get("prompt", args[0] if args else "")))[:1000],
                )
                
                result = await func(*args, **kwargs)
                
                # Update with output
                gen.update(
                    output=str(result)[:2000] if result else None,
                    metadata={
                        "latency_ms": int((time.time() - start_time) * 1000),
                    },
                )
                gen.end()
                
                return result
            except Exception as e:
                logger.warning(f"Langfuse observe error: {e}")
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            client = get_langfuse()
            if not client:
                return func(*args, **kwargs)
            
            import time
            start_time = time.time()
            
            try:
                gen = client.start_observation(
                    as_type="generation",
                    name=name,
                    model=model,
                    metadata=metadata or {},
                    input=str(kwargs.get("query", kwargs.get("prompt", args[0] if args else "")))[:1000],
                )
                
                result = func(*args, **kwargs)
                
                gen.update(
                    output=str(result)[:2000] if result else None,
                    metadata={
                        "latency_ms": int((time.time() - start_time) * 1000),
                    },
                )
                gen.end()
                
                return result
            except Exception as e:
                logger.warning(f"Langfuse observe error: {e}")
                return func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def observe_embedding(name: str = "embedding"):
    """Decorator to observe embedding calls."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            client = get_langfuse()
            if not client:
                return await func(*args, **kwargs)
            
            import time
            start_time = time.time()
            
            try:
                # Get text count
                texts = kwargs.get("texts", args[0] if args else [])
                text_count = len(texts) if isinstance(texts, list) else 1
                
                span = client.start_span(
                    name=name,
                    metadata={"text_count": text_count},
                )
                
                result = await func(*args, **kwargs)
                
                span.update(
                    output={"embedding_count": len(result) if result else 0},
                    metadata={
                        "latency_ms": int((time.time() - start_time) * 1000),
                    },
                )
                span.end()
                
                return result
            except Exception as e:
                logger.warning(f"Langfuse embedding observe error: {e}")
                return await func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return func
    
    return decorator


def observe_retrieval(name: str = "retrieval"):
    """Decorator to observe retrieval calls."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            client = get_langfuse()
            if not client:
                return await func(*args, **kwargs)
            
            import time
            start_time = time.time()
            
            try:
                query = kwargs.get("query", args[0] if args else "")
                
                span = client.start_span(
                    name=name,
                    input=str(query)[:500],
                )
                
                result = await func(*args, **kwargs)
                
                # Get result count
                result_count = 0
                if hasattr(result, "documents"):
                    result_count = len(result.documents)
                elif isinstance(result, list):
                    result_count = len(result)
                
                span.update(
                    output={"result_count": result_count},
                    metadata={
                        "latency_ms": int((time.time() - start_time) * 1000),
                    },
                )
                span.end()
                
                return result
            except Exception as e:
                logger.warning(f"Langfuse retrieval observe error: {e}")
                return await func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return func
    
    return decorator
