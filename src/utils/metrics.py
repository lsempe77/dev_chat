"""
DevChat v2.0 SOTA - Metrics Tracking

Track and report metrics:
- Latency (p50, p95, p99)
- Token usage
- Query types distribution
- Error rates
- Retrieval quality (Recall@K, NDCG, MRR)
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Retrieval Quality Metrics
# ============================================================================

def recall_at_k(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
    k: int = 10,
) -> float:
    """
    Calculate Recall@K: proportion of relevant items retrieved in top K.
    
    Recall@K = |retrieved_top_k ∩ relevant| / |relevant|
    
    Args:
        retrieved_ids: List of retrieved document IDs (in rank order)
        relevant_ids: Set of truly relevant document IDs
        k: Number of top results to consider
        
    Returns:
        Recall@K score (0.0 to 1.0)
        
    Example:
        >>> recall_at_k(['a', 'b', 'c'], {'a', 'c', 'd'}, k=2)
        0.333...  # Only 'a' is in top 2, 1/3 relevant found
    """
    if not relevant_ids:
        return 1.0  # If nothing is relevant, consider it perfect
    
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


def precision_at_k(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
    k: int = 10,
) -> float:
    """
    Calculate Precision@K: proportion of top K that are relevant.
    
    Precision@K = |retrieved_top_k ∩ relevant| / K
    
    Args:
        retrieved_ids: List of retrieved document IDs (in rank order)
        relevant_ids: Set of truly relevant document IDs
        k: Number of top results to consider
        
    Returns:
        Precision@K score (0.0 to 1.0)
    """
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / len(top_k)


def mean_reciprocal_rank(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR): 1/rank of first relevant result.
    
    MRR = 1 / rank_of_first_relevant
    
    Args:
        retrieved_ids: List of retrieved document IDs (in rank order)
        relevant_ids: Set of truly relevant document IDs
        
    Returns:
        MRR score (0.0 to 1.0), 0 if no relevant found
        
    Example:
        >>> mean_reciprocal_rank(['a', 'b', 'c'], {'b', 'd'})
        0.5  # First relevant 'b' is at rank 2, so 1/2
    """
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    retrieved_ids: List[str],
    relevance_scores: Dict[str, float],
    k: int = 10,
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain (NDCG@K).
    
    NDCG measures ranking quality, penalizing relevant items ranked lower.
    
    DCG@K = Σ (relevance_i / log2(i + 1)) for i in 1..K
    NDCG@K = DCG@K / IDCG@K (ideal DCG)
    
    Args:
        retrieved_ids: List of retrieved document IDs (in rank order)
        relevance_scores: Dict mapping doc_id -> relevance score (0.0 to 1.0)
        k: Number of top results to consider
        
    Returns:
        NDCG@K score (0.0 to 1.0)
        
    Example:
        >>> ndcg_at_k(['a', 'b', 'c'], {'a': 1.0, 'c': 0.5}, k=3)
        # DCG = 1.0/log2(2) + 0/log2(3) + 0.5/log2(4) = 1.0 + 0 + 0.25 = 1.25
        # IDCG (ideal: c, a, b) = 1.0/log2(2) + 0.5/log2(3) = 1.0 + 0.315 = 1.315
        # NDCG = 1.25 / 1.315 ≈ 0.95
    """
    def dcg(ids: List[str], scores: Dict[str, float], k: int) -> float:
        """Calculate Discounted Cumulative Gain."""
        result = 0.0
        for i, doc_id in enumerate(ids[:k], start=1):
            rel = scores.get(doc_id, 0.0)
            result += rel / math.log2(i + 1)
        return result
    
    # Calculate DCG for actual ranking
    actual_dcg = dcg(retrieved_ids, relevance_scores, k)
    
    # Calculate IDCG (ideal DCG) - sorted by relevance descending
    ideal_order = sorted(relevance_scores.keys(), key=lambda x: relevance_scores[x], reverse=True)
    ideal_dcg = dcg(ideal_order, relevance_scores, k)
    
    if ideal_dcg == 0:
        return 1.0 if actual_dcg == 0 else 0.0
    
    return actual_dcg / ideal_dcg


@dataclass
class RetrievalQualityMetrics:
    """Retrieval quality metrics for a single query."""
    query_id: str
    timestamp: datetime
    
    # Core metrics
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    recall_at_20: float = 0.0
    precision_at_5: float = 0.0
    precision_at_10: float = 0.0
    mrr: float = 0.0
    ndcg_at_10: float = 0.0
    
    # Context
    num_retrieved: int = 0
    num_relevant: int = 0
    num_reranked: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "recall@5": round(self.recall_at_5, 3),
            "recall@10": round(self.recall_at_10, 3),
            "recall@20": round(self.recall_at_20, 3),
            "precision@5": round(self.precision_at_5, 3),
            "precision@10": round(self.precision_at_10, 3),
            "mrr": round(self.mrr, 3),
            "ndcg@10": round(self.ndcg_at_10, 3),
            "num_retrieved": self.num_retrieved,
            "num_relevant": self.num_relevant,
        }


def compute_retrieval_metrics(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
    relevance_scores: Optional[Dict[str, float]] = None,
    query_id: str = "",
) -> RetrievalQualityMetrics:
    """
    Compute all retrieval quality metrics for a query.
    
    Args:
        retrieved_ids: List of retrieved document IDs (in rank order)
        relevant_ids: Set of truly relevant document IDs
        relevance_scores: Optional graded relevance (for NDCG). If None, binary.
        query_id: Query identifier for tracking
        
    Returns:
        RetrievalQualityMetrics object with all computed metrics
    """
    # Default to binary relevance if no scores provided
    if relevance_scores is None:
        relevance_scores = {doc_id: 1.0 for doc_id in relevant_ids}
    
    return RetrievalQualityMetrics(
        query_id=query_id,
        timestamp=datetime.now(),
        recall_at_5=recall_at_k(retrieved_ids, relevant_ids, k=5),
        recall_at_10=recall_at_k(retrieved_ids, relevant_ids, k=10),
        recall_at_20=recall_at_k(retrieved_ids, relevant_ids, k=20),
        precision_at_5=precision_at_k(retrieved_ids, relevant_ids, k=5),
        precision_at_10=precision_at_k(retrieved_ids, relevant_ids, k=10),
        mrr=mean_reciprocal_rank(retrieved_ids, relevant_ids),
        ndcg_at_10=ndcg_at_k(retrieved_ids, relevance_scores, k=10),
        num_retrieved=len(retrieved_ids),
        num_relevant=len(relevant_ids),
    )


# ============================================================================
# Query Metrics (existing)
# ============================================================================


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


# ============================================================================
# Retrieval Metrics Tracking
# ============================================================================

class RetrievalMetricsTracker:
    """
    Track retrieval quality metrics across queries.
    
    Stores metrics history and provides aggregation.
    Optionally logs to Langfuse for observability.
    """
    
    def __init__(self, max_history: int = 500):
        self.max_history = max_history
        self.metrics: List[RetrievalQualityMetrics] = []
    
    def record(self, metrics: RetrievalQualityMetrics) -> None:
        """Record retrieval quality metrics for a query."""
        self.metrics.append(metrics)
        
        if len(self.metrics) > self.max_history:
            self.metrics = self.metrics[-self.max_history:]
        
        logger.debug(f"Retrieval metrics: {metrics.to_dict()}")
    
    def get_summary(self, last_n: Optional[int] = None) -> Dict:
        """Get aggregated retrieval quality summary."""
        data = self.metrics[-last_n:] if last_n else self.metrics
        
        if not data:
            return {
                "total_queries": 0,
                "averages": {
                    "recall_at_5": 0.0,
                    "recall_at_10": 0.0,
                    "recall_at_20": 0.0,
                    "precision_at_5": 0.0,
                    "precision_at_10": 0.0,
                    "mrr": 0.0,
                    "ndcg_at_10": 0.0,
                },
                "message": "No retrieval metrics recorded yet"
            }
        
        def avg(values: List[float]) -> float:
            return sum(values) / len(values) if values else 0.0
        
        return {
            "total_queries": len(data),
            "averages": {
                "recall_at_5": round(avg([m.recall_at_5 for m in data]), 3),
                "recall_at_10": round(avg([m.recall_at_10 for m in data]), 3),
                "recall_at_20": round(avg([m.recall_at_20 for m in data]), 3),
                "precision_at_5": round(avg([m.precision_at_5 for m in data]), 3),
                "precision_at_10": round(avg([m.precision_at_10 for m in data]), 3),
                "mrr": round(avg([m.mrr for m in data]), 3),
                "ndcg_at_10": round(avg([m.ndcg_at_10 for m in data]), 3),
            },
            "counts": {
                "avg_retrieved": round(avg([m.num_retrieved for m in data]), 1),
                "avg_relevant": round(avg([m.num_relevant for m in data]), 1),
            },
        }
    
    def clear(self) -> None:
        """Clear all metrics."""
        self.metrics = []


# Global retrieval metrics tracker
_retrieval_metrics = RetrievalMetricsTracker()


def get_retrieval_metrics_tracker() -> RetrievalMetricsTracker:
    """Get the global retrieval metrics tracker."""
    return _retrieval_metrics


def log_retrieval_metrics_to_langfuse(
    metrics: RetrievalQualityMetrics,
    trace=None,
    span_name: str = "retrieval_quality",
) -> None:
    """
    Log retrieval quality metrics to Langfuse.
    
    Creates a span with all retrieval metrics as metadata.
    
    Args:
        metrics: RetrievalQualityMetrics object
        trace: Langfuse trace object (optional)
        span_name: Name for the Langfuse span
    """
    try:
        from src.utils.langfuse_client import add_span_to_trace, is_langfuse_enabled
        
        if not is_langfuse_enabled():
            return
        
        add_span_to_trace(
            trace=trace,
            name=span_name,
            output_data=metrics.to_dict(),
            metadata={
                "query_id": metrics.query_id,
                "recall@10": metrics.recall_at_10,
                "mrr": metrics.mrr,
                "ndcg@10": metrics.ndcg_at_10,
            },
        )
        
        logger.debug(f"Logged retrieval metrics to Langfuse: {metrics.query_id}")
        
    except Exception as e:
        logger.warning(f"Failed to log retrieval metrics to Langfuse: {e}")


def track_retrieval_quality(
    retrieved_ids: List[str],
    relevant_ids: Set[str],
    relevance_scores: Optional[Dict[str, float]] = None,
    query_id: str = "",
    trace=None,
    log_to_langfuse: bool = True,
) -> RetrievalQualityMetrics:
    """
    Convenience function to compute, record, and optionally log retrieval metrics.
    
    This is the main entry point for tracking retrieval quality.
    
    Args:
        retrieved_ids: List of retrieved document IDs (in rank order)
        relevant_ids: Set of truly relevant document IDs
        relevance_scores: Optional graded relevance scores
        query_id: Query identifier
        trace: Langfuse trace object
        log_to_langfuse: Whether to log to Langfuse
        
    Returns:
        Computed retrieval quality metrics
        
    Example:
        from src.utils.metrics import track_retrieval_quality
        
        # After retrieval
        retrieved_ids = [r.node_id for r in results]
        
        # Define what's "relevant" (e.g., reranked results or ground truth)
        relevant_ids = {r.node_id for r in reranked_results}
        
        # Track metrics
        metrics = track_retrieval_quality(
            retrieved_ids=retrieved_ids,
            relevant_ids=relevant_ids,
            query_id=query_id,
            trace=langfuse_trace,
        )
    """
    metrics = compute_retrieval_metrics(
        retrieved_ids=retrieved_ids,
        relevant_ids=relevant_ids,
        relevance_scores=relevance_scores,
        query_id=query_id,
    )
    
    # Record in global tracker
    tracker = get_retrieval_metrics_tracker()
    tracker.record(metrics)
    
    # Log to Langfuse if enabled
    if log_to_langfuse:
        log_retrieval_metrics_to_langfuse(metrics, trace)
    
    return metrics
