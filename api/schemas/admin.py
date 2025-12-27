"""
DevChat v2.0 SOTA - Admin Panel Schema Models

Models for admin dashboard, document management, and metadata review.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from .common import ServiceConnection


# =============================================================================
# Upload & Processing Models
# =============================================================================

class UploadResponse(BaseModel):
    """Response after uploading a file."""
    success: bool
    filename: str
    r2_key: str
    size_bytes: int
    queued_for_processing: bool = False
    doc_id: Optional[str] = None


class ProcessingJob(BaseModel):
    """A document processing job."""
    id: str
    filename: str
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    doc_id: Optional[str] = None
    pages: Optional[int] = None
    chunks: Optional[int] = None


class ProcessingJobsResponse(BaseModel):
    """Response listing processing jobs."""
    jobs: List[ProcessingJob]
    queued_count: int
    processing_count: int
    completed_count: int
    failed_count: int


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


# =============================================================================
# Document Models
# =============================================================================

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


class DocumentsResponse(BaseModel):
    """Response listing indexed documents."""
    documents: List[DocumentMetadata]
    total_count: int
    total_chunks: int
    total_pages: int


# =============================================================================
# Metadata Review Models (Zotero-Compatible)
# =============================================================================

class DocumentMetadataDetail(BaseModel):
    """
    Extended metadata for document review.
    Zotero-compatible field structure for bibliographic metadata.
    """
    id: str
    title: str
    filename: str
    authors: List[str] = []
    year: Optional[int] = None
    abstract: Optional[str] = None
    
    # Zotero item type
    item_type: Optional[str] = None
    
    # Identifiers
    doi: Optional[str] = None
    isbn: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None
    
    # Publication info
    publication: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    edition: Optional[str] = None
    
    # Publisher info
    publisher: Optional[str] = None
    place: Optional[str] = None
    
    # Series info
    series: Optional[str] = None
    series_number: Optional[str] = None
    
    # Book-specific
    book_title: Optional[str] = None
    num_pages: Optional[int] = None
    
    # Report/Thesis specific
    institution: Optional[str] = None
    report_number: Optional[str] = None
    report_type: Optional[str] = None
    thesis_type: Optional[str] = None
    
    # Conference-specific
    conference_name: Optional[str] = None
    proceedings_title: Optional[str] = None
    
    # Access info
    accessed_date: Optional[str] = None
    
    # Citation metrics
    cited_by_count: Optional[int] = None
    is_open_access: Optional[bool] = False
    
    # 3ie Classification
    countries: List[str] = []
    sectors: List[str] = []
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    sdgs: List[str] = []
    keywords: List[str] = []
    
    # Processing metadata
    metadata_source: Optional[str] = "extraction"
    metadata_confidence: float = 0.0
    needs_review: bool = True
    chunk_count: int = 0
    page_count: int = 0
    
    # Extra fields (JSON)
    extra: Optional[Dict[str, Any]] = None


class MetadataReviewResponse(BaseModel):
    """Response listing documents needing metadata review."""
    documents: List[DocumentMetadataDetail]
    total_count: int
    needs_review_count: int
    low_confidence_count: int


class MetadataUpdateRequest(BaseModel):
    """
    Request to update document metadata.
    Zotero-compatible field structure.
    """
    # Core
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    
    # Item type
    item_type: Optional[str] = None
    
    # Identifiers
    doi: Optional[str] = None
    isbn: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None
    
    # Publication
    publication: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    edition: Optional[str] = None
    
    # Publisher
    publisher: Optional[str] = None
    place: Optional[str] = None
    
    # Series
    series: Optional[str] = None
    series_number: Optional[str] = None
    
    # Book
    book_title: Optional[str] = None
    num_pages: Optional[int] = None
    
    # Report/Thesis
    institution: Optional[str] = None
    report_number: Optional[str] = None
    report_type: Optional[str] = None
    thesis_type: Optional[str] = None
    
    # Conference
    conference_name: Optional[str] = None
    proceedings_title: Optional[str] = None
    
    # Access
    accessed_date: Optional[str] = None
    
    # 3ie Classification
    countries: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    
    # Review status
    needs_review: Optional[bool] = None
    
    # Extra fields
    extra: Optional[Dict[str, Any]] = None


class MetadataUpdateResponse(BaseModel):
    """Response after updating metadata."""
    success: bool
    document_id: str
    updated_chunks: int
    message: str


# =============================================================================
# Admin Dashboard Models
# =============================================================================

class StorageStatus(BaseModel):
    """Status of cloud storage."""
    bucket: str
    input_path: str
    output_path: str
    storage_used_bytes: int
    file_count: int


class AdminStatusResponse(BaseModel):
    """Admin dashboard status response."""
    storage: StorageStatus
    connections: List[ServiceConnection]
    pending_jobs: int
    active_workers: int
