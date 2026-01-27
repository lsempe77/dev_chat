"""
DevChat v2.0 SOTA - API Schemas

Pydantic models for API request/response validation.

This package is organized into:
- common.py: Base models, health, errors, timing
- chat.py: Chat/query models (frontend and legacy)
- admin.py: Admin panel models (documents, metadata, jobs)
"""

# Common models
from .common import (
    CollectionInfo,
    ErrorResponse,
    HealthResponse,
    MetricsResponse,
    ServiceConnection,
    TimingInfo,
)

# Chat/Query models
from .chat import (
    # Frontend-compatible
    CitationResponse,
    CompareRequest,
    CompareResponse,
    EvidenceHealth,
    FilterInput,
    FiltersResponse,
    QueryRequest,
    QueryResponse,
    SearchSettings,
    StudyResponse,
    SuggestRequest,
    SuggestResponse,
    # Feature Suggestions
    FeatureSuggestionItem,
    FeatureSuggestionRequest,
    FeatureSuggestionsResponse,
    # Legacy
    ChatRequest,
    ChatResponse,
    Citation,
    IngestRequest,
    IngestResponse,
)

# Admin models
from .admin import (
    AdminStatusResponse,
    DocumentMetadata,
    DocumentMetadataDetail,
    DocumentsResponse,
    DocumentSyncRequest,
    DocumentSyncResponse,
    MetadataReviewResponse,
    MetadataUpdateRequest,
    MetadataUpdateResponse,
    ProcessingJob,
    ProcessingJobsResponse,
    StorageStatus,
    TriggerProcessingRequest,
    TriggerProcessingResponse,
    UploadResponse,
)

__all__ = [
    # Common
    "CollectionInfo",
    "ErrorResponse",
    "HealthResponse",
    "MetricsResponse",
    "ServiceConnection",
    "TimingInfo",
    # Chat/Query - Frontend
    "CitationResponse",
    "CompareRequest",
    "CompareResponse",
    "EvidenceHealth",
    "FilterInput",
    "FiltersResponse",
    "QueryRequest",
    "QueryResponse",
    "SearchSettings",
    "StudyResponse",
    "SuggestRequest",
    "SuggestResponse",
    # Feature Suggestions
    "FeatureSuggestionItem",
    "FeatureSuggestionRequest",
    "FeatureSuggestionsResponse",
    # Chat/Query - Legacy
    "ChatRequest",
    "ChatResponse",
    "Citation",
    "IngestRequest",
    "IngestResponse",
    # Admin
    "AdminStatusResponse",
    "DocumentMetadata",
    "DocumentMetadataDetail",
    "DocumentsResponse",
    "DocumentSyncRequest",
    "DocumentSyncResponse",
    "MetadataReviewResponse",
    "MetadataUpdateRequest",
    "MetadataUpdateResponse",
    "ProcessingJob",
    "ProcessingJobsResponse",
    "StorageStatus",
    "TriggerProcessingRequest",
    "TriggerProcessingResponse",
    "UploadResponse",
]
