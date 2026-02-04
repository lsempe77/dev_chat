"""
Structured Error Handling for Extraction Pipeline
=================================================

Provides:
- Typed exceptions for different failure modes
- Warning accumulator for soft failures
- Stage-aware logging with context (study_id, table_number, stage)
- Strict vs permissive mode support
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
from loguru import logger


class ExtractionStage(str, Enum):
    """Pipeline stages for error attribution."""
    LOADING = "loading"
    METADATA = "metadata"
    TABLE_CLASSIFICATION = "table_classification"
    TABLE_PARSING = "table_parsing"
    PROSE_EXTRACTION = "prose_extraction"
    FIGURE_EXTRACTION = "figure_extraction"
    CONTEXT_ENRICHMENT = "context_enrichment"
    OUTCOME_CLASSIFICATION = "outcome_classification"
    ANALYSIS_CLASSIFICATION = "analysis_classification"
    EFFECT_SIZE_CALCULATION = "effect_size_calculation"
    SCHEMA_CONVERSION = "schema_conversion"
    OUTPUT = "output"


class ErrorSeverity(str, Enum):
    """Severity levels for errors/warnings."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LLMFailureType(str, Enum):
    """Types of LLM failures for better diagnostics."""
    UNAVAILABLE = "unavailable"           # API error, timeout
    EMPTY_RESPONSE = "empty_response"     # LLM returned nothing
    MALFORMED_JSON = "malformed_json"     # JSON parsing failed
    SCHEMA_VIOLATION = "schema_violation" # Response doesn't match expected format
    NO_SIGNAL = "no_signal"               # LLM couldn't find relevant info
    RATE_LIMITED = "rate_limited"         # API rate limit


@dataclass
class ExtractionError(Exception):
    """
    Structured extraction error with full context.
    
    Attributes:
        message: Human-readable error description
        stage: Which pipeline stage failed
        study_id: Study being processed
        table_number: Table number if applicable
        details: Additional context (dict)
        severity: Error severity level
        recoverable: Whether pipeline can continue
        llm_failure_type: If LLM-related, what kind of failure
    """
    message: str
    stage: ExtractionStage
    study_id: Optional[str] = None
    table_number: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    severity: ErrorSeverity = ErrorSeverity.ERROR
    recoverable: bool = False
    llm_failure_type: Optional[LLMFailureType] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def __str__(self) -> str:
        parts = [f"[{self.stage.value}]"]
        if self.study_id:
            parts.append(f"study={self.study_id}")
        if self.table_number:
            parts.append(f"table={self.table_number}")
        parts.append(self.message)
        if self.llm_failure_type:
            parts.append(f"(LLM: {self.llm_failure_type.value})")
        return " ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "stage": self.stage.value,
            "study_id": self.study_id,
            "table_number": self.table_number,
            "details": self.details,
            "severity": self.severity.value,
            "recoverable": self.recoverable,
            "llm_failure_type": self.llm_failure_type.value if self.llm_failure_type else None,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ExtractionWarning:
    """
    Structured warning for soft failures that don't stop processing.
    
    Examples:
    - LLM returned no classification (defaulting to 'results')
    - Missing SE for one row (continuing with partial data)
    - Ambiguous table orientation (using best guess)
    """
    message: str
    stage: ExtractionStage
    study_id: Optional[str] = None
    table_number: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    llm_failure_type: Optional[LLMFailureType] = None
    default_used: Optional[str] = None  # What default was applied
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def __str__(self) -> str:
        parts = [f"[WARN:{self.stage.value}]"]
        if self.study_id:
            parts.append(f"study={self.study_id}")
        if self.table_number:
            parts.append(f"table={self.table_number}")
        parts.append(self.message)
        if self.default_used:
            parts.append(f"(defaulting to: {self.default_used})")
        return " ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "stage": self.stage.value,
            "study_id": self.study_id,
            "table_number": self.table_number,
            "details": self.details,
            "llm_failure_type": self.llm_failure_type.value if self.llm_failure_type else None,
            "default_used": self.default_used,
            "timestamp": self.timestamp.isoformat(),
        }


class ErrorAccumulator:
    """
    Accumulates errors and warnings during pipeline execution.
    
    Features:
    - Collects all issues without stopping execution (permissive mode)
    - Can switch to strict mode to raise on first error
    - Provides summary statistics
    - Logs all issues with proper context
    - Exports to JSON for debugging
    
    Usage:
        accumulator = ErrorAccumulator(study_id="12345", strict=False)
        
        # Record a warning
        accumulator.warn(
            message="LLM classification returned empty",
            stage=ExtractionStage.TABLE_CLASSIFICATION,
            table_number="3",
            default_used="results"
        )
        
        # Check if we had issues
        if accumulator.has_errors:
            print(accumulator.summary())
    """
    
    def __init__(
        self, 
        study_id: Optional[str] = None, 
        strict: bool = False,
        log_level: str = "INFO"
    ):
        self.study_id = study_id
        self.strict = strict
        self.errors: List[ExtractionError] = []
        self.warnings: List[ExtractionWarning] = []
        self._stage_counts: Dict[ExtractionStage, Dict[str, int]] = {}
        self._llm_call_count = 0
        self._llm_failure_count = 0
        
        # Configure logger for this accumulator
        self.log_level = log_level
        
    def set_study(self, study_id: str) -> None:
        """Set/update study ID for subsequent errors."""
        self.study_id = study_id
    
    def error(
        self,
        message: str,
        stage: ExtractionStage,
        table_number: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = False,
        llm_failure_type: Optional[LLMFailureType] = None,
    ) -> None:
        """
        Record an error. Raises immediately in strict mode.
        """
        err = ExtractionError(
            message=message,
            stage=stage,
            study_id=self.study_id,
            table_number=table_number,
            details=details,
            recoverable=recoverable,
            llm_failure_type=llm_failure_type,
        )
        
        self.errors.append(err)
        self._increment_stage_count(stage, "errors")
        
        # Log with full context
        logger.error(str(err))
        if details:
            logger.debug(f"  Details: {details}")
        
        if self.strict and not recoverable:
            raise err
    
    def warn(
        self,
        message: str,
        stage: ExtractionStage,
        table_number: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        llm_failure_type: Optional[LLMFailureType] = None,
        default_used: Optional[str] = None,
    ) -> None:
        """
        Record a warning (soft failure).
        """
        warn = ExtractionWarning(
            message=message,
            stage=stage,
            study_id=self.study_id,
            table_number=table_number,
            details=details,
            llm_failure_type=llm_failure_type,
            default_used=default_used,
        )
        
        self.warnings.append(warn)
        self._increment_stage_count(stage, "warnings")
        
        # Log 
        logger.warning(str(warn))
    
    def record_llm_call(self, success: bool) -> None:
        """Track LLM call statistics."""
        self._llm_call_count += 1
        if not success:
            self._llm_failure_count += 1
    
    def _increment_stage_count(self, stage: ExtractionStage, kind: str) -> None:
        if stage not in self._stage_counts:
            self._stage_counts[stage] = {"errors": 0, "warnings": 0}
        self._stage_counts[stage][kind] += 1
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    @property
    def error_count(self) -> int:
        return len(self.errors)
    
    @property
    def warning_count(self) -> int:
        return len(self.warnings)
    
    @property
    def llm_success_rate(self) -> float:
        if self._llm_call_count == 0:
            return 1.0
        return 1 - (self._llm_failure_count / self._llm_call_count)
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"\n{'='*60}",
            f"EXTRACTION SUMMARY: study {self.study_id}",
            f"{'='*60}",
            f"Errors:   {self.error_count}",
            f"Warnings: {self.warning_count}",
            f"LLM calls: {self._llm_call_count} ({100*self.llm_success_rate:.1f}% success)",
        ]
        
        if self._stage_counts:
            lines.append("\nIssues by stage:")
            for stage, counts in self._stage_counts.items():
                if counts["errors"] or counts["warnings"]:
                    lines.append(f"  {stage.value}: {counts['errors']} errors, {counts['warnings']} warnings")
        
        if self.errors:
            lines.append("\nErrors:")
            for err in self.errors[:10]:  # Show first 10
                lines.append(f"  - {err}")
            if len(self.errors) > 10:
                lines.append(f"  ... and {len(self.errors) - 10} more")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export to dictionary for JSON serialization."""
        return {
            "study_id": self.study_id,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "llm_calls": self._llm_call_count,
            "llm_failures": self._llm_failure_count,
            "stage_counts": {
                stage.value: counts 
                for stage, counts in self._stage_counts.items()
            },
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


# Global accumulator for convenience (can be replaced per-run)
_global_accumulator: Optional[ErrorAccumulator] = None


def get_accumulator() -> ErrorAccumulator:
    """Get or create global error accumulator."""
    global _global_accumulator
    if _global_accumulator is None:
        _global_accumulator = ErrorAccumulator()
    return _global_accumulator


def set_accumulator(accumulator: ErrorAccumulator) -> None:
    """Set the global error accumulator."""
    global _global_accumulator
    _global_accumulator = accumulator


def reset_accumulator() -> None:
    """Reset the global accumulator."""
    global _global_accumulator
    _global_accumulator = None
