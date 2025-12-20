"""
DevChat v2.0 - Circuit Breaker Pattern for Production Resilience

Prevents cascade failures when external services (LLM APIs, Qdrant, etc.) fail.
Provides graceful degradation instead of hanging requests.

Usage:
    breaker = CircuitBreaker("openrouter_llm", failure_threshold=3, recovery_timeout=60)
    
    async with breaker:
        result = await llm.acomplete(prompt)
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Optional, TypeVar, Generic
from functools import wraps

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for external service calls.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast with fallback
    - HALF_OPEN: Testing recovery, allow one request through
    
    Args:
        name: Identifier for this breaker (for logging)
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before trying again
        fallback_response: Optional response when circuit is open
    """
    name: str
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    fallback_response: Optional[str] = None
    
    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for recovery timeout."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state
    
    @property
    def is_available(self) -> bool:
        """Check if requests should be allowed."""
        return self.state != CircuitState.OPEN
    
    async def record_success(self):
        """Record a successful call, reset failure count."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit breaker '{self.name}' closing after successful recovery")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
    
    async def record_failure(self, error: Exception):
        """Record a failed call, potentially open circuit."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        f"Circuit breaker '{self.name}' OPENING after {self._failure_count} failures. "
                        f"Last error: {error}"
                    )
                self._state = CircuitState.OPEN
    
    async def __aenter__(self):
        """Check if request should proceed."""
        current_state = self.state
        
        if current_state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open due to repeated failures. "
                f"Retry after {int(self.recovery_timeout - (time.time() - self._last_failure_time))} seconds."
            )
        
        if current_state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit breaker '{self.name}' is half-open, allowing test request")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Record result of the request."""
        if exc_type is None:
            await self.record_success()
        else:
            await self.record_failure(exc_val)
        return False  # Don't suppress exceptions
    
    def get_status(self) -> Dict:
        """Get circuit breaker status for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure": self._last_failure_time,
            "recovery_timeout": self.recovery_timeout,
        }


class CircuitOpenError(Exception):
    """Raised when circuit is open and request should fail fast."""
    pass


# Global circuit breakers for different services
_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _breakers[name]


def get_all_breaker_status() -> Dict[str, Dict]:
    """Get status of all circuit breakers for monitoring."""
    return {name: breaker.get_status() for name, breaker in _breakers.items()}


# Decorator for automatic circuit breaker
T = TypeVar('T')


def with_circuit_breaker(
    breaker_name: str,
    failure_threshold: int = 3,
    recovery_timeout: float = 60.0,
    fallback: Optional[Callable[[], T]] = None,
):
    """
    Decorator to wrap async function with circuit breaker.
    
    Example:
        @with_circuit_breaker("llm_api", failure_threshold=3, fallback=lambda: "Service unavailable")
        async def call_llm(prompt: str) -> str:
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            breaker = get_circuit_breaker(breaker_name, failure_threshold, recovery_timeout)
            
            try:
                async with breaker:
                    return await func(*args, **kwargs)
            except CircuitOpenError:
                if fallback:
                    logger.warning(f"Circuit '{breaker_name}' open, using fallback for {func.__name__}")
                    return fallback()
                raise
        
        return wrapper
    return decorator


# Health check integration
async def check_service_health(name: str, check_func: Callable) -> Dict:
    """
    Check service health and update circuit breaker.
    
    Args:
        name: Service name (used as circuit breaker name)
        check_func: Async function that checks service health
        
    Returns:
        Health status dict
    """
    breaker = get_circuit_breaker(name)
    
    try:
        async with breaker:
            await check_func()
        return {
            "name": name,
            "healthy": True,
            "circuit_state": breaker.state.value,
        }
    except Exception as e:
        return {
            "name": name,
            "healthy": False,
            "error": str(e),
            "circuit_state": breaker.state.value,
        }
