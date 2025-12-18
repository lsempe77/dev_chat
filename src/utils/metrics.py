"""
DevChat v2.0 SOTA - Metrics Tracking

Track and report metrics:
- Latency (p50, p95, p99)
- Token usage
- Query types distribution
- Error rates
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class QueryMetrics:
    """Metrics for a single query."""
    query_id: str
    timestamp: datetime
    query_type: str
    
    # Timing (milliseconds)
    query_processing_ms: float = 0.0
    retrieval_ms: float = 0.0
    reranking_ms: float = 0.0
    synthesis_ms: float = 0.0
    total_ms: float = 0.0
    
    # Counts
    retrieval_count: int = 0
    reranked_count: int = 0
    sources_used: int = 0
    
    # Model info
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    
    # Status
    success: bool = True
    error_message: Optional[str] = None


class MetricsTracker:
    """
    Track and aggregate metrics across queries.
    """
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics: List[QueryMetrics] = []
        self._query_counter = 0
    
    def start_query(self) -> str:
        """Start tracking a new query, return query ID."""
        self._query_counter += 1
        return f"q_{self._query_counter}_{int(time.time())}"
    
    def record(self, metrics: QueryMetrics) -> None:
        """Record metrics for a query."""
        self.metrics.append(metrics)
        
        # Trim history if needed
        if len(self.metrics) > self.max_history:
            self.metrics = self.metrics[-self.max_history:]
    
    def get_summary(self, last_n: Optional[int] = None) -> Dict:
        """
        Get aggregated metrics summary.
        
        Args:
            last_n: Only consider last N queries
        """
        data = self.metrics[-last_n:] if last_n else self.metrics
        
        if not data:
            return {"message": "No metrics recorded yet"}
        
        # Calculate latency percentiles
        total_times = sorted([m.total_ms for m in data])
        
        def percentile(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            idx = int(len(values) * p / 100)
            return values[min(idx, len(values) - 1)]
        
        # Query type distribution
        type_counts = defaultdict(int)
        for m in data:
            type_counts[m.query_type] += 1
        
        # Model usage
        model_counts = defaultdict(int)
        for m in data:
            if m.model_used:
                model_counts[m.model_used] += 1
        
        # Error rate
        errors = [m for m in data if not m.success]
        error_rate = len(errors) / len(data) * 100
        
        # Token usage
        total_input = sum(m.input_tokens for m in data)
        total_output = sum(m.output_tokens for m in data)
        
        return {
            "total_queries": len(data),
            "latency": {
                "p50_ms": percentile(total_times, 50),
                "p95_ms": percentile(total_times, 95),
                "p99_ms": percentile(total_times, 99),
                "avg_ms": sum(total_times) / len(total_times),
            },
            "breakdown_avg_ms": {
                "query_processing": sum(m.query_processing_ms for m in data) / len(data),
                "retrieval": sum(m.retrieval_ms for m in data) / len(data),
                "reranking": sum(m.reranking_ms for m in data) / len(data),
                "synthesis": sum(m.synthesis_ms for m in data) / len(data),
            },
            "query_types": dict(type_counts),
            "models_used": dict(model_counts),
            "error_rate_percent": error_rate,
            "tokens": {
                "total_input": total_input,
                "total_output": total_output,
                "avg_input_per_query": total_input / len(data),
                "avg_output_per_query": total_output / len(data),
            },
            "retrieval": {
                "avg_retrieved": sum(m.retrieval_count for m in data) / len(data),
                "avg_reranked": sum(m.reranked_count for m in data) / len(data),
                "avg_sources": sum(m.sources_used for m in data) / len(data),
            },
        }
    
    def get_recent_errors(self, n: int = 10) -> List[Dict]:
        """Get recent error details."""
        errors = [m for m in self.metrics if not m.success]
        recent = errors[-n:]
        
        return [
            {
                "query_id": m.query_id,
                "timestamp": m.timestamp.isoformat(),
                "error": m.error_message,
            }
            for m in recent
        ]
    
    def clear(self) -> None:
        """Clear all metrics."""
        self.metrics = []


class Timer:
    """Simple context manager for timing operations."""
    
    def __init__(self):
        self.start_time = None
        self.elapsed_ms = 0.0
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args):
        self.elapsed_ms = (time.time() - self.start_time) * 1000
        return False


# Global metrics tracker
_global_metrics = MetricsTracker()


def get_metrics_tracker() -> MetricsTracker:
    """Get the global metrics tracker."""
    return _global_metrics
