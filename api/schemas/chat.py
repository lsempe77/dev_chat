"""
DevChat v2.0 SOTA - Chat & Query Schema Models

Models for chat/query endpoints - both frontend-compatible and legacy.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .common import TimingInfo


# =============================================================================
# Frontend-Compatible Models (Research Workbench)
# =============================================================================

class FilterInput(BaseModel):
    """A filter from the frontend."""
    type: Literal["country", "sector", "studyType", "yearRange", "confidence"]
    value: str


class SearchSettings(BaseModel):
    """Search settings from the frontend SettingsDrawer."""
    relevanceThreshold: float = Field(default=0.5, ge=0, le=1)
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
    session_id: Optional[str] = Field(None, description="Session ID for conversation memory")
    collection: Optional[str] = Field(None, description="Qdrant collection name for multi-tenant RAGs")
    project_id: Optional[str] = Field(None, description="RAG project ID for model config lookup")


class StudyResponse(BaseModel):
    """A study in the format expected by the frontend."""
    id: str
    title: str
    authors: str = ""
    year: Optional[int] = None
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
    page: Optional[int] = None
    highlightText: Optional[str] = None


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
# Feature Suggestions Models
# =============================================================================

class FeatureSuggestionRequest(BaseModel):
    """Request for feature suggestions generation."""
    project_name: str = Field(default="DevChat RAG Project", description="Name of the RAG project")
    document_count: int = Field(default=0, ge=0, description="Number of documents in the project")
    query_count: int = Field(default=0, ge=0, description="Total queries made")
    common_topics: Optional[List[str]] = Field(None, description="List of common topics/sectors")
    user_feedback: Optional[str] = Field(None, description="User feedback or pain points")


class FeatureSuggestionItem(BaseModel):
    """A single feature suggestion."""
    id: str = Field(..., description="Unique identifier for the suggestion")
    title: str = Field(..., description="Short, catchy feature name")
    description: str = Field(..., description="One-sentence description of the feature")
    category: Literal[
        "retrieval", "analysis", "visualization", "export",
        "collaboration", "automation", "quality", "integration"
    ] = Field(..., description="Feature category")
    impact: Literal["high", "medium", "low"] = Field(..., description="Expected user value")
    effort: Literal["high", "medium", "low"] = Field(..., description="Implementation complexity")
    rationale: str = Field(..., description="Why this feature would help users")


class FeatureSuggestionsResponse(BaseModel):
    """Response containing feature suggestions."""
    suggestions: List[FeatureSuggestionItem] = Field(..., description="List of 10 feature suggestions")
    generated_at: str = Field(..., description="Timestamp of generation")
    project_context: Dict[str, Any] = Field(default_factory=dict, description="Context used for generation")


# =============================================================================
# Legacy Chat Models
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
    
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation memory",
    )
    
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


# =============================================================================
# Ingestion Models
# =============================================================================

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


class IngestResponse(BaseModel):
    """Response from ingestion endpoint."""
    
    status: str
    documents_processed: int
    chunks_created: int
    collection: "CollectionInfo"
    elapsed_seconds: float


# Import for type reference
from .common import CollectionInfo
