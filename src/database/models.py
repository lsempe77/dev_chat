"""
DevChat v2.0 SOTA - Database Models

SQLAlchemy models for document metadata storage.
Zotero-compatible field structure for bibliographic metadata.
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
    ForeignKey,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ============================================================================
# Conversation Memory Models
# ============================================================================

class ChatSession(Base):
    """
    Represents a conversation session.
    
    Each session can have multiple messages and persists across page reloads.
    """
    __tablename__ = "chat_sessions"
    
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Session metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to messages
    messages: Mapped[List["ChatMessage"]] = relationship("ChatMessage", back_populates="session", order_by="ChatMessage.created_at")
    
    def __repr__(self) -> str:
        return f"<ChatSession(id='{self.id}', title='{self.title}')>"


class ChatMessage(Base):
    """
    Individual message in a conversation.
    
    Stores both user queries and assistant responses with full context.
    """
    __tablename__ = "chat_messages"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    
    # Message content
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Metadata for assistant messages
    query_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    num_sources: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    citations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Timing and performance
    total_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship to session
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
    
    # Index for efficient message retrieval
    __table_args__ = (
        Index('ix_chat_messages_session_created', 'session_id', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role='{self.role}', session='{self.session_id}')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "query_type": self.query_type,
            "model_used": self.model_used,
            "num_sources": self.num_sources,
            "citations": self.citations,
            "total_time_ms": self.total_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================================
# Document Metadata Model
# ============================================================================

class Document(Base):
    """
    Document metadata model.
    
    Stores all metadata about documents indexed in Qdrant.
    Uses Zotero-compatible field names for bibliographic metadata.
    
    Field organization:
    - Core fields: Always present regardless of item_type
    - Bibliographic fields: Standard Zotero fields for publications
    - Classification fields: 3ie-specific research classification
    - Processing fields: Indexing and quality metadata
    - Extra (JSON): Item-type-specific fields (report_number, thesis_type, etc.)
    """
    __tablename__ = "documents"

    # Primary identifier (matches Qdrant doc_id)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    
    # === CORE FIELDS ===
    title: Mapped[str] = mapped_column(Text, nullable=False, default="Untitled")
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # === ZOTERO ITEM TYPE ===
    # journalArticle, book, bookSection, report, thesis, conferencePaper, 
    # workingPaper, manuscript, webpage, dataset, preprint
    item_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # === BIBLIOGRAPHIC FIELDS (Zotero-compatible) ===
    # Identifiers
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    isbn: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    issn: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Publication info
    publication: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Journal/Magazine name (Zotero: publicationTitle)
    journal: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Alias for publication (backward compat)
    volume: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    issue: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pages: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    edition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Publisher info
    publisher: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    place: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Publication place
    
    # Series info
    series: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Series title
    series_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Book-specific
    book_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # For bookSection
    num_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Total pages in book/thesis
    
    # Report/Thesis specific (also stored in extra for flexibility)
    institution: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Report institution or thesis university
    report_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    report_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "Technical Report", "Working Paper"
    thesis_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "PhD Dissertation", "Master's Thesis"
    
    # Conference-specific
    conference_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    proceedings_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Access info
    accessed_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Date accessed for web resources
    
    # Citation metrics
    cited_by_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_open_access: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # === CLASSIFICATION FIELDS (3ie-specific) ===
    countries: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    sectors: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    study_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # RCT, Quasi-experimental, etc.
    intervention_type: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sdgs: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    
    # === PROCESSING METADATA ===
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
    
    # Extra fields (JSON for additional Zotero fields not in main schema)
    # Can include: language, rights, archive, archive_location, call_number, 
    # short_title, editors, translators, etc.
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
            "abstract": self.abstract,
            "item_type": self.item_type,
            # Identifiers
            "doi": self.doi,
            "isbn": self.isbn,
            "issn": self.issn,
            "url": self.url,
            # Publication
            "publication": self.publication,
            "journal": self.journal,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "edition": self.edition,
            # Publisher
            "publisher": self.publisher,
            "place": self.place,
            # Series
            "series": self.series,
            "series_number": self.series_number,
            # Book
            "book_title": self.book_title,
            "num_pages": self.num_pages,
            # Report/Thesis
            "institution": self.institution,
            "report_number": self.report_number,
            "report_type": self.report_type,
            "thesis_type": self.thesis_type,
            # Conference
            "conference_name": self.conference_name,
            "proceedings_title": self.proceedings_title,
            # Access
            "accessed_date": self.accessed_date,
            # Metrics
            "cited_by_count": self.cited_by_count,
            "is_open_access": self.is_open_access,
            # Classification
            "countries": self.countries or [],
            "sectors": self.sectors or [],
            "study_type": self.study_type,
            "intervention_type": self.intervention_type,
            "sdgs": self.sdgs or [],
            "keywords": self.keywords or [],
            # Processing
            "chunk_count": self.chunk_count,
            "page_count": self.page_count,
            "metadata_source": self.metadata_source,
            "metadata_confidence": self.metadata_confidence,
            "needs_review": self.needs_review,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "extra": self.extra,
        }
