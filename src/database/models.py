"""
DevChat v2.0 SOTA - Database Models

SQLAlchemy models for document metadata storage.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    ARRAY,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Document(Base):
    """
    Document metadata model.
    
    Stores all metadata about documents indexed in Qdrant.
    This enables instant queries without scanning vector payloads.
    """
    __tablename__ = "documents"

    # Primary identifier (matches Qdrant doc_id)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    
    # Core metadata
    title: Mapped[str] = mapped_column(Text, nullable=False, default="Untitled")
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Academic metadata
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    journal: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_by_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_open_access: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Classification metadata
    countries: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    sectors: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    study_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    intervention_type: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sdgs: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    
    # Processing metadata
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Metadata quality
    metadata_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # crossref, openalex, llm
    metadata_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="indexed", index=True)
    
    # Extra fields (JSON for flexibility)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Document(id='{self.id}', title='{self.title[:50]}...')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "authors": self.authors or [],
            "year": self.year,
            "doi": self.doi,
            "journal": self.journal,
            "publisher": self.publisher,
            "abstract": self.abstract,
            "cited_by_count": self.cited_by_count,
            "is_open_access": self.is_open_access,
            "countries": self.countries or [],
            "sectors": self.sectors or [],
            "study_type": self.study_type,
            "intervention_type": self.intervention_type,
            "sdgs": self.sdgs or [],
            "keywords": self.keywords or [],
            "chunk_count": self.chunk_count,
            "page_count": self.page_count,
            "metadata_source": self.metadata_source,
            "metadata_confidence": self.metadata_confidence,
            "needs_review": self.needs_review,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
