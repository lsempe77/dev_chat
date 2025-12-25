"""
DevChat v2.0 SOTA - API Schemas

Pydantic models for API request/response validation.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Frontend-Compatible Models (Research Workbench)
# =============================================================================

class FilterInput(BaseModel):
    """A filter from the frontend."""
    type: Literal["country", "sector", "studyType", "yearRange", "confidence"]
    value: str


class SearchSettings(BaseModel):
    """Search settings from the frontend SettingsDrawer."""
    relevanceThreshold: float = Field(default=0.5, ge=0, le=1)  # User can adjust via Settings
    maxStudies: int = Field(default=10, ge=3, le=25)
    answerStyle: Literal["executive", "research", "policy", "citations"] = "executive"
    useReranking: bool = True
    minConfidence: Literal["all", "medium", "high"] = "all"
    yearCutoff: int = Field(default=2010, ge=1990, le=2030)


class QueryRequest(BaseModel):
    """Request for the main /api/query endpoint (frontend)."""
    query: str = Field(..., min_length=1, max_length=2000)
    filters: Optional[List[FilterInput]] = None
    settings: Optional[SearchSettings] = None


class StudyResponse(BaseModel):
    """A study in the format expected by the frontend."""
    id: str
    title: str
    authors: str = ""  # Can be empty string if not available
    year: Optional[int] = None  # Can be None if not available
    country: str = ""
    sector: str = ""
    studyType: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    snippet: str = ""
    score: float = 0.0
    pdfUrl: Optional[str] = None
    
    @field_validator('authors', mode='before')
    @classmethod
    def coerce_authors(cls, v):
        """Convert list to comma-separated string."""
        if isinstance(v, list):
            return ", ".join(str(a) for a in v) if v else ""
        return v or ""


class CitationResponse(BaseModel):
    """A citation in the format expected by the frontend."""
    id: int
    studyId: str
    text: str
    study: StudyResponse
    page: Optional[int] = None  # Page number for PDF navigation
    highlightText: Optional[str] = None  # Text to highlight in PDF viewer


class EvidenceHealth(BaseModel):
    """Evidence health metrics for the frontend."""
    studyCount: int
    dateRange: str
    gaps: List[str] = []
    coverageWarning: Optional[str] = None


class QueryResponse(BaseModel):
    """Response for the main /api/query endpoint (frontend)."""
    answer: str
    citations: List[CitationResponse]
    studies: List[StudyResponse]
    suggestions: List[str] = []
    evidenceHealth: EvidenceHealth


class CompareRequest(BaseModel):
    """Request for study comparison."""
    study_ids: List[str]


class CompareResponse(BaseModel):
    """Response for study comparison."""
    comparison: Dict[str, Dict[str, str]]
    conflicts: List[str] = []


class SuggestRequest(BaseModel):
    """Request for query suggestions."""
    query: str
    context: str


class SuggestResponse(BaseModel):
    """Response for query suggestions."""
    suggestions: List[str]


class FiltersResponse(BaseModel):
    """Available filter options."""
    countries: List[str]
    sectors: List[str]
    studyTypes: List[str]
    yearRange: Dict[str, int]


# =============================================================================
# Request Models (Legacy)
# =============================================================================

class ChatRequest(BaseModel):
    """Request for chat endpoint."""
    
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User's question",
        examples=["What are the effects of conditional cash transfers on education?"],
    )
    
    include_citations: bool = Field(
        default=True,
        description="Whether to include reference list",
    )
    
    stream: bool = Field(
        default=False,
        description="Whether to stream the response",
    )
    
    # Optional filters
    year_min: Optional[int] = Field(
        default=None,
        ge=1990,
        le=2030,
        description="Minimum publication year",
    )
    
    year_max: Optional[int] = Field(
        default=None,
        ge=1990,
        le=2030,
        description="Maximum publication year",
    )
    
    sectors: Optional[List[str]] = Field(
        default=None,
        description="Filter by sector (education, health, etc.)",
    )
    
    countries: Optional[List[str]] = Field(
        default=None,
        description="Filter by country",
    )


class IngestRequest(BaseModel):
    """Request for document ingestion."""
    
    source_path: str = Field(
        ...,
        description="Path to source documents",
    )
    
    collection_name: Optional[str] = Field(
        default=None,
        description="Target collection name",
    )
    
    recreate: bool = Field(
        default=False,
        description="Whether to recreate the collection",
    )


# =============================================================================
# Response Models
# =============================================================================

class Citation(BaseModel):
    """A single citation."""
    
    study_id: str
    title: str
    year: Optional[int] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    url: Optional[str] = None
    page_start: Optional[int] = Field(None, description="Starting page in PDF")
    page_end: Optional[int] = Field(None, description="Ending page in PDF")
    pages: Optional[List[int]] = Field(None, description="All pages covered by this citation")


class TimingInfo(BaseModel):
    """Timing breakdown for a request."""
    
    query_ms: float = Field(description="Query processing time")
    retrieval_ms: float = Field(description="Retrieval time")
    rerank_ms: float = Field(description="Reranking time")
    synthesis_ms: float = Field(description="LLM synthesis time")
    total_ms: float = Field(description="Total request time")


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    
    answer: str = Field(description="Generated answer")
    query_type: str = Field(description="Detected query type")
    model_used: str = Field(description="LLM model used")
    num_sources: int = Field(description="Number of sources used")
    citations: List[Citation] = Field(description="Source citations")
    timing: TimingInfo = Field(description="Timing breakdown")
    
    # Debug info (optional)
    expanded_query: Optional[str] = None
    filters_applied: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(description="Service status")
    version: str = Field(description="API version")
    timestamp: datetime = Field(description="Current timestamp")
    
    # Component health
    components: Dict[str, bool] = Field(
        description="Health status of components"
    )


class MetricsResponse(BaseModel):
    """Metrics summary response."""
    
    total_queries: int
    latency: Dict[str, float]
    query_types: Dict[str, int]
    error_rate_percent: float
    tokens: Dict[str, int]


class CollectionInfo(BaseModel):
    """Information about a vector collection."""
    
    name: str
    points_count: int
    vectors_count: int
    status: str


class IngestResponse(BaseModel):
    """Response from ingestion endpoint."""
    
    status: str
    documents_processed: int
    chunks_created: int
    collection: CollectionInfo
    elapsed_seconds: float


class ErrorResponse(BaseModel):
    """Error response."""
    
    error: str = Field(description="Error type")
    message: str = Field(description="Error message")
    detail: Optional[str] = Field(default=None, description="Additional details")
    timestamp: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Admin Panel Models
# =============================================================================

class UploadResponse(BaseModel):
    """Response after uploading a file."""
    success: bool
    filename: str
    r2_key: str
    size_bytes: int
    queued_for_processing: bool = False
    doc_id: Optional[str] = None  # Universal document ID across all systems


class ProcessingJob(BaseModel):
    """A document processing job."""
    id: str
    filename: str
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    doc_id: Optional[str] = None  # Universal document ID
    pages: Optional[int] = None
    chunks: Optional[int] = None


class ProcessingJobsResponse(BaseModel):
    """Response listing processing jobs."""
    jobs: List[ProcessingJob]
    queued_count: int
    processing_count: int
    completed_count: int
    failed_count: int


class DocumentMetadata(BaseModel):
    """Metadata for an indexed document."""
    id: str
    title: str
    filename: str
    authors: List[str] = []
    year: Optional[int] = None
    status: Literal["indexed", "pending", "error"]
    page_count: int = 0
    chunk_count: int = 0
    uploaded_at: datetime
    processed_at: Optional[datetime] = None


class DocumentMetadataDetail(BaseModel):
    """Extended metadata for document review."""
    id: str
    title: str
    filename: str
    authors: List[str] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    publisher: Optional[str] = None
    cited_by_count: Optional[int] = None
    is_open_access: Optional[bool] = False
    countries: List[str] = []
    sectors: List[str] = []
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    sdgs: List[str] = []
    keywords: List[str] = []
    metadata_source: Optional[str] = "extraction"
    metadata_confidence: float = 0.0
    needs_review: bool = True
    chunk_count: int = 0


class MetadataReviewResponse(BaseModel):
    """Response listing documents needing metadata review."""
    documents: List[DocumentMetadataDetail]
    total_count: int
    needs_review_count: int
    low_confidence_count: int


class MetadataUpdateRequest(BaseModel):
    """Request to update document metadata."""
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    countries: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    needs_review: Optional[bool] = None


class MetadataUpdateResponse(BaseModel):
    """Response after updating metadata."""
    success: bool
    document_id: str
    updated_chunks: int
    message: str


class DocumentsResponse(BaseModel):
    """Response listing indexed documents."""
    documents: List[DocumentMetadata]
    total_count: int
    total_chunks: int
    total_pages: int


class StorageStatus(BaseModel):
    """Status of cloud storage."""
    bucket: str
    input_path: str
    output_path: str
    storage_used_bytes: int
    file_count: int


class ServiceConnection(BaseModel):
    """Status of an external service connection."""
    name: str
    status: Literal["connected", "disconnected", "error"]
    details: Optional[str] = None
    latency_ms: Optional[float] = None


class AdminStatusResponse(BaseModel):
    """Admin dashboard status response."""
    storage: StorageStatus
    connections: List[ServiceConnection]
    pending_jobs: int
    active_workers: int


class TriggerProcessingRequest(BaseModel):
    """Request to trigger batch processing."""
    force_reprocess: bool = False
    specific_files: Optional[List[str]] = None
    max_documents: Optional[int] = 10


class TriggerProcessingResponse(BaseModel):
    """Response after triggering processing."""
    queued: int
    skipped: int
    message: str
