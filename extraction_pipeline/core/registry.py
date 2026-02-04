"""
Document Registry - Central source of truth for document management.

Handles:
- Document identification with proper deduplication
- Distinguishing main papers vs appendices vs language variants
- Content-based hashing for true duplicate detection
- Mapping between R2 files and canonical study identifiers

Architecture:
- Each unique study has a canonical identifier (study_id)
- Each document variant (appendix, language) has a unique doc_id
- Content hash used for true duplicate detection
- Registry persisted to JSON for fast lookups
"""
import hashlib
import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
load_dotenv()


class DocumentType(str, Enum):
    """Type of document within a study."""
    MAIN = "main"           # Primary paper
    APPENDIX = "appendix"   # Supplementary material / appendix
    SUPPLEMENT = "supplement"  # Online supplement
    TRANSLATION = "translation"  # Translated version
    PREPRINT = "preprint"   # Pre-print version
    UNKNOWN = "unknown"


class Language(str, Enum):
    """Document language."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    PORTUGUESE = "pt"
    UNKNOWN = "unknown"


@dataclass
class DocumentVariant:
    """A specific version/variant of a document."""
    doc_id: str                    # Unique document ID (content hash + name)
    filename: str                  # Original filename in R2
    r2_key: str                    # Full R2 key path
    doc_type: DocumentType         # Main, appendix, etc.
    language: Language             # Document language
    content_hash: Optional[str]    # MD5 hash of content (for dedup)
    size_bytes: int                # File size
    created_at: str                # ISO timestamp
    
    def to_dict(self) -> dict:
        return {
            **asdict(self),
            'doc_type': self.doc_type.value,
            'language': self.language.value,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DocumentVariant':
        return cls(
            doc_id=data['doc_id'],
            filename=data['filename'],
            r2_key=data['r2_key'],
            doc_type=DocumentType(data.get('doc_type', 'unknown')),
            language=Language(data.get('language', 'unknown')),
            content_hash=data.get('content_hash'),
            size_bytes=data.get('size_bytes', 0),
            created_at=data.get('created_at', ''),
        )


@dataclass
class StudyRecord:
    """A study with all its document variants."""
    study_id: str                           # Canonical study identifier
    title: Optional[str] = None             # Study title if known
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    variants: List[DocumentVariant] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    @property
    def main_document(self) -> Optional[DocumentVariant]:
        """Get the main document (prefer English main)."""
        mains = [v for v in self.variants if v.doc_type == DocumentType.MAIN]
        if not mains:
            return self.variants[0] if self.variants else None
        # Prefer English
        english = [v for v in mains if v.language == Language.ENGLISH]
        return english[0] if english else mains[0]
    
    @property
    def has_appendix(self) -> bool:
        return any(v.doc_type == DocumentType.APPENDIX for v in self.variants)
    
    @property
    def languages(self) -> Set[Language]:
        return {v.language for v in self.variants}
    
    def to_dict(self) -> dict:
        return {
            'study_id': self.study_id,
            'title': self.title,
            'authors': self.authors,
            'year': self.year,
            'variants': [v.to_dict() for v in self.variants],
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StudyRecord':
        return cls(
            study_id=data['study_id'],
            title=data.get('title'),
            authors=data.get('authors', []),
            year=data.get('year'),
            variants=[DocumentVariant.from_dict(v) for v in data.get('variants', [])],
            metadata=data.get('metadata', {}),
        )


class DocumentRegistry:
    """
    Central registry for document management.
    
    Provides:
    - Canonical study identification
    - Duplicate detection via content hash
    - Variant tracking (appendices, translations)
    - Persistent storage
    """
    
    # Patterns for extracting document metadata from filenames
    PATTERNS = {
        # Numeric study ID (e.g., 121058369)
        'numeric_id': re.compile(r'(\d{9})'),
        
        # Appendix indicators
        'appendix': re.compile(r'[_-]?(appendix|app|suppl|supplement|si|sm|supporting)[_.-]?', re.I),
        
        # Language indicators
        'spanish': re.compile(r'[_-]?(spanish|espanol|esp)[_.-]?', re.I),
        'english': re.compile(r'[_-]?(english|eng|translated)[_.-]?', re.I),
        
        # BRAC author pattern: BRAC_programs_(40)_AuthorName_(Year)
        'brac_author': re.compile(r'BRAC_programs_\(40\)_([A-Za-z]+)_?\(?(\d{4})\)?'),
        
        # Generic author year pattern
        'author_year': re.compile(r'([A-Z][a-z]+)[\s_]*\(?\s*(\d{4})\)?'),
        
        # Content hash prefix (8 hex chars)
        'content_hash': re.compile(r'^([a-f0-9]{12})_'),
    }
    
    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize registry, loading from disk if exists."""
        self.registry_path = registry_path or Path(__file__).parent / "document_registry.json"
        self.studies: Dict[str, StudyRecord] = {}
        self.doc_id_to_study: Dict[str, str] = {}  # doc_id -> study_id mapping
        self.content_hash_to_doc: Dict[str, str] = {}  # content_hash -> doc_id mapping
        
        if self.registry_path.exists():
            self.load()
    
    def load(self) -> None:
        """Load registry from disk."""
        with open(self.registry_path) as f:
            data = json.load(f)
        
        self.studies = {
            sid: StudyRecord.from_dict(sdata) 
            for sid, sdata in data.get('studies', {}).items()
        }
        
        # Rebuild indexes
        self._rebuild_indexes()
    
    def save(self) -> None:
        """Persist registry to disk."""
        data = {
            'version': '1.0',
            'updated_at': datetime.utcnow().isoformat(),
            'studies': {sid: s.to_dict() for sid, s in self.studies.items()},
        }
        
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _rebuild_indexes(self) -> None:
        """Rebuild lookup indexes from studies."""
        self.doc_id_to_study = {}
        self.content_hash_to_doc = {}
        
        for study_id, study in self.studies.items():
            for variant in study.variants:
                self.doc_id_to_study[variant.doc_id] = study_id
                if variant.content_hash:
                    self.content_hash_to_doc[variant.content_hash] = variant.doc_id
    
    def extract_metadata_from_filename(self, filename: str) -> Dict:
        """
        Extract study metadata from filename.
        
        Returns dict with:
        - study_id: Canonical study identifier
        - doc_type: DocumentType
        - language: Language
        - content_hash: If present in filename
        - authors: List of author names
        - year: Publication year
        """
        result = {
            'study_id': None,
            'doc_type': DocumentType.MAIN,
            'language': Language.UNKNOWN,
            'content_hash': None,
            'authors': [],
            'year': None,
            'raw_identifier': None,
        }
        
        # Extract content hash prefix if present
        hash_match = self.PATTERNS['content_hash'].match(filename)
        if hash_match:
            result['content_hash'] = hash_match.group(1)
            # Remove hash prefix for further parsing
            filename_clean = filename[len(hash_match.group(0)):]
        else:
            filename_clean = filename
        
        # Remove file extension
        filename_clean = re.sub(r'\.(json|pdf|md)$', '', filename_clean, flags=re.I)
        
        # Check for appendix/supplement
        if self.PATTERNS['appendix'].search(filename_clean):
            result['doc_type'] = DocumentType.APPENDIX
        
        # Check for language
        if self.PATTERNS['spanish'].search(filename_clean):
            result['language'] = Language.SPANISH
        elif self.PATTERNS['english'].search(filename_clean):
            result['language'] = Language.ENGLISH
        else:
            result['language'] = Language.ENGLISH  # Default assumption
        
        # Extract study ID
        # Priority 1: Numeric ID (most reliable)
        numeric_match = self.PATTERNS['numeric_id'].search(filename_clean)
        if numeric_match:
            result['study_id'] = numeric_match.group(1)
            result['raw_identifier'] = numeric_match.group(1)
        
        # Priority 2: BRAC author pattern
        elif 'BRAC' in filename_clean:
            brac_match = self.PATTERNS['brac_author'].search(filename_clean)
            if brac_match:
                author = brac_match.group(1)
                year = brac_match.group(2)
                result['study_id'] = f"BRAC_{author}_{year}"
                result['authors'] = [author]
                result['year'] = int(year)
                result['raw_identifier'] = result['study_id']
            else:
                # Fallback: extract any author-like pattern
                author_match = self.PATTERNS['author_year'].search(filename_clean)
                if author_match:
                    author = author_match.group(1)
                    year = author_match.group(2)
                    result['study_id'] = f"BRAC_{author}_{year}"
                    result['authors'] = [author]
                    result['year'] = int(year)
                else:
                    result['study_id'] = filename_clean
                result['raw_identifier'] = result['study_id']
        
        # Priority 3: Use cleaned filename as identifier
        else:
            # Remove common prefixes
            cleaned = re.sub(r'^PDFs_of_included_programs_', '', filename_clean)
            cleaned = re.sub(r'^Bangladesh_-_all_BRAC_programs_', '', cleaned)
            result['study_id'] = cleaned
            result['raw_identifier'] = cleaned
        
        return result
    
    def generate_doc_id(self, filename: str, content_hash: Optional[str] = None) -> str:
        """
        Generate a unique document ID.
        
        Format: {content_hash}_{sanitized_name}
        If no content_hash provided, uses filename hash.
        """
        if not content_hash:
            # Use filename-based hash as fallback
            content_hash = hashlib.md5(filename.encode()).hexdigest()[:12]
        
        # Sanitize filename
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)
        safe_name = re.sub(r'_+', '_', safe_name)[:80]  # Limit length
        
        return f"{content_hash}_{safe_name}"
    
    def register_document(
        self,
        filename: str,
        r2_key: str,
        size_bytes: int = 0,
        content_hash: Optional[str] = None,
        force: bool = False,
    ) -> Tuple[str, DocumentVariant, bool]:
        """
        Register a document in the registry.
        
        Returns:
            (study_id, variant, is_new) tuple
            - study_id: Canonical study identifier
            - variant: The DocumentVariant record
            - is_new: True if this is a new document (not duplicate)
        """
        # Check for exact content duplicate first
        if content_hash and content_hash in self.content_hash_to_doc:
            existing_doc_id = self.content_hash_to_doc[content_hash]
            existing_study_id = self.doc_id_to_study.get(existing_doc_id)
            if existing_study_id and not force:
                study = self.studies[existing_study_id]
                variant = next(v for v in study.variants if v.doc_id == existing_doc_id)
                return (existing_study_id, variant, False)
        
        # Extract metadata from filename
        meta = self.extract_metadata_from_filename(filename)
        study_id = meta['study_id']
        
        # Generate doc_id
        doc_id = self.generate_doc_id(filename, content_hash)
        
        # Check if this doc_id already registered
        if doc_id in self.doc_id_to_study and not force:
            existing_study_id = self.doc_id_to_study[doc_id]
            study = self.studies[existing_study_id]
            variant = next(v for v in study.variants if v.doc_id == doc_id)
            return (existing_study_id, variant, False)
        
        # Create new variant
        variant = DocumentVariant(
            doc_id=doc_id,
            filename=filename,
            r2_key=r2_key,
            doc_type=meta['doc_type'],
            language=meta['language'],
            content_hash=content_hash,
            size_bytes=size_bytes,
            created_at=datetime.utcnow().isoformat(),
        )
        
        # Add to or create study
        if study_id not in self.studies:
            self.studies[study_id] = StudyRecord(
                study_id=study_id,
                authors=meta.get('authors', []),
                year=meta.get('year'),
            )
        
        self.studies[study_id].variants.append(variant)
        
        # Update indexes
        self.doc_id_to_study[doc_id] = study_id
        if content_hash:
            self.content_hash_to_doc[content_hash] = doc_id
        
        return (study_id, variant, True)
    
    def get_study(self, study_id: str) -> Optional[StudyRecord]:
        """Get study by canonical ID."""
        return self.studies.get(study_id)
    
    def get_document_by_id(self, doc_id: str) -> Optional[Tuple[StudyRecord, DocumentVariant]]:
        """Get study and variant by doc_id."""
        study_id = self.doc_id_to_study.get(doc_id)
        if not study_id:
            return None
        study = self.studies[study_id]
        variant = next((v for v in study.variants if v.doc_id == doc_id), None)
        return (study, variant) if variant else None
    
    def find_duplicates(self) -> Dict[str, List[DocumentVariant]]:
        """
        Find potential duplicates across studies.
        
        Returns dict of content_hash -> list of variants with that hash.
        Only returns hashes with multiple variants (true duplicates).
        """
        hash_to_variants: Dict[str, List[DocumentVariant]] = {}
        
        for study in self.studies.values():
            for variant in study.variants:
                if variant.content_hash:
                    if variant.content_hash not in hash_to_variants:
                        hash_to_variants[variant.content_hash] = []
                    hash_to_variants[variant.content_hash].append(variant)
        
        # Return only actual duplicates
        return {h: vs for h, vs in hash_to_variants.items() if len(vs) > 1}
    
    def get_all_study_ids(self) -> List[str]:
        """Get all canonical study IDs."""
        return list(self.studies.keys())
    
    def get_main_documents(self) -> List[Tuple[str, DocumentVariant]]:
        """Get main document for each study."""
        return [
            (study_id, study.main_document)
            for study_id, study in self.studies.items()
            if study.main_document
        ]
    
    def summary(self) -> Dict:
        """Get registry summary statistics."""
        all_variants = [v for s in self.studies.values() for v in s.variants]
        
        return {
            'total_studies': len(self.studies),
            'total_documents': len(all_variants),
            'with_appendix': sum(1 for s in self.studies.values() if s.has_appendix),
            'multilingual': sum(1 for s in self.studies.values() if len(s.languages) > 1),
            'by_type': {
                t.value: sum(1 for v in all_variants if v.doc_type == t)
                for t in DocumentType
            },
            'by_language': {
                l.value: sum(1 for v in all_variants if v.language == l)
                for l in Language
            },
        }


# =============================================================================
# Global Registry Instance (Singleton)
# =============================================================================

_registry_instance: Optional[DocumentRegistry] = None


def get_registry(registry_path: Optional[Path] = None) -> DocumentRegistry:
    """
    Get the global DocumentRegistry instance (singleton).
    
    Creates the registry on first call, reuses it afterward.
    Thread-safe for read operations.
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = DocumentRegistry(registry_path)
    return _registry_instance


def register_upload(
    original_filename: str,
    r2_key: str,
    content_hash: str,
    size_bytes: int,
    project_id: str,
    save: bool = True,
) -> Dict:
    """
    Register a document upload from the frontend.
    
    This is the main entry point for integrating with the API upload flow.
    
    Args:
        original_filename: The user's original filename
        r2_key: Full R2 key where file was uploaded
        content_hash: SHA-256 hash (truncated) of file content
        size_bytes: File size in bytes
        project_id: The RAG project this belongs to
        save: Whether to persist registry to disk
    
    Returns:
        Dict with:
        - study_id: Canonical study identifier
        - doc_id: Unique document identifier
        - doc_type: main, appendix, translation, etc.
        - language: en, es, etc.
        - is_new: Whether this is a new document (not duplicate)
        - is_duplicate: True if exact content already exists
        - existing_doc_id: If duplicate, the existing document's ID
    """
    registry = get_registry()
    
    # Check for content duplicate first
    if content_hash in registry.content_hash_to_doc:
        existing_doc_id = registry.content_hash_to_doc[content_hash]
        existing_study_id = registry.doc_id_to_study.get(existing_doc_id)
        return {
            'study_id': existing_study_id,
            'doc_id': existing_doc_id,
            'doc_type': 'duplicate',
            'language': 'unknown',
            'is_new': False,
            'is_duplicate': True,
            'existing_doc_id': existing_doc_id,
            'project_id': project_id,
        }
    
    # Register the document
    study_id, variant, is_new = registry.register_document(
        filename=original_filename,
        r2_key=r2_key,
        size_bytes=size_bytes,
        content_hash=content_hash,
    )
    
    # Save registry if requested
    if save:
        registry.save()
    
    return {
        'study_id': study_id,
        'doc_id': variant.doc_id,
        'doc_type': variant.doc_type.value,
        'language': variant.language.value,
        'is_new': is_new,
        'is_duplicate': not is_new,
        'existing_doc_id': variant.doc_id if not is_new else None,
        'project_id': project_id,
    }


def check_duplicate(content_hash: str) -> Optional[Dict]:
    """
    Check if a document with this content hash already exists.
    
    Args:
        content_hash: SHA-256 hash (truncated) of file content
    
    Returns:
        Dict with study_id, doc_id if duplicate exists, else None
    """
    registry = get_registry()
    
    if content_hash in registry.content_hash_to_doc:
        existing_doc_id = registry.content_hash_to_doc[content_hash]
        existing_study_id = registry.doc_id_to_study.get(existing_doc_id)
        return {
            'study_id': existing_study_id,
            'doc_id': existing_doc_id,
            'is_duplicate': True,
        }
    return None


# =============================================================================
# Utility Functions
# =============================================================================

def compute_content_hash(content: bytes) -> str:
    """Compute MD5 hash of content (first 12 chars for compact IDs)."""
    return hashlib.md5(content).hexdigest()[:12]


def compute_file_hash(filepath: Path) -> str:
    """Compute MD5 hash of a file."""
    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            md5.update(chunk)
    return md5.hexdigest()[:12]


# =============================================================================
# CLI for testing
# =============================================================================

if __name__ == '__main__':
    # Test filename parsing
    test_files = [
        '9aa551090ac0_PDFs_of_included_programs_121058369_appendix.json',
        'c6f56d86e783_PDFs_of_included_programs_121058369.json',
        '3d1065d6b553_PDFs_of_included_programs_121498842_translated_into_English.json',
        'df1588ddee86_PDFs_of_included_programs_121498842_Spanish.json',
        '107e85be2bad_PDFs_of_included_programs_Bangladesh_-_all_BRAC_programs_BRAC_programs_(40)_Ahmed_(2009)_Capability_Development.json',
        '57a79c24c074_PDFs_of_included_programs_Bangladesh_-_all_BRAC_programs_BRAC_programs_(40)_Ahmed_(2009)_The_impact_of_asset_transfer.json',
    ]
    
    registry = DocumentRegistry()
    
    print("=" * 70)
    print("FILENAME PARSING TEST")
    print("=" * 70)
    
    for filename in test_files:
        meta = registry.extract_metadata_from_filename(filename)
        print(f"\n{filename[:60]}...")
        print(f"  study_id: {meta['study_id']}")
        print(f"  doc_type: {meta['doc_type'].value}")
        print(f"  language: {meta['language'].value}")
        print(f"  content_hash: {meta['content_hash']}")
