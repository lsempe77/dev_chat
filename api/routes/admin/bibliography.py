"""
Admin Bibliography Routes

Endpoints for importing (RIS/BibTeX/CSV) and exporting (BibTeX/RIS) citations.
"""

import csv
import io
import re
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from src.utils.logging import get_logger
from ..dependencies import is_postgres_available, get_db_session

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class ExportResponse(BaseModel):
    """Response containing exported bibliography data."""
    format: str
    count: int
    data: str
    filename: str


class ImportedEntry(BaseModel):
    """A parsed bibliography entry."""
    title: str
    authors: List[str] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    item_type: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    keywords: List[str] = []


class ImportPreviewResponse(BaseModel):
    """Preview of parsed entries before import."""
    parsed_count: int
    entries: List[ImportedEntry]
    errors: List[str]
    duplicates: List[str]  # Titles that already exist


class ImportConfirmRequest(BaseModel):
    """Confirm import of specific entries."""
    entries: List[ImportedEntry]
    skip_duplicates: bool = True
    merge_duplicates: bool = False  # Update existing records with richer metadata
    enrich_from_doi: bool = True    # Fetch metadata from CrossRef/OpenAlex if DOI present


class ImportConfirmResponse(BaseModel):
    """Result of confirmed import."""
    imported_count: int
    skipped_count: int
    updated_count: int = 0  # Records updated via merge
    enriched_count: int = 0  # Records enriched via DOI lookup
    errors: List[str]


# =============================================================================
# Export Endpoints
# =============================================================================

@router.get("/bibliography/export")
async def export_bibliography(
    format: str = Query("bibtex", description="Export format: 'bibtex' or 'ris'"),
    doc_ids: Optional[str] = Query(None, description="Comma-separated doc IDs to export (all if omitted)"),
):
    """
    Export documents as BibTeX or RIS format.
    
    - format=bibtex: Standard BibTeX (.bib)
    - format=ris: Research Information Systems (.ris)
    """
    if format not in ("bibtex", "ris"):
        raise HTTPException(status_code=400, detail="Format must be 'bibtex' or 'ris'")
    
    # Parse doc_ids if provided
    selected_ids = None
    if doc_ids:
        selected_ids = [id.strip() for id in doc_ids.split(",") if id.strip()]
    
    # Get documents from PostgreSQL
    if not is_postgres_available():
        raise HTTPException(status_code=503, detail="Database not available")
    
    db = await get_db_session()
    if not db:
        raise HTTPException(status_code=503, detail="Could not connect to database")
    
    async with db:
        from src.database.repository import DocumentRepository
        
        if selected_ids:
            docs = []
            for doc_id in selected_ids:
                doc = await DocumentRepository.get_by_id(db, doc_id)
                if doc:
                    docs.append(doc)
        else:
            # Get all documents
            docs = await DocumentRepository.get_for_review(db, filter_type="all", limit=10000)
    
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found")
    
    # Generate export
    if format == "bibtex":
        content = _generate_bibtex(docs)
        filename = f"devchat_export_{datetime.now().strftime('%Y%m%d')}.bib"
        media_type = "application/x-bibtex"
    else:
        content = _generate_ris(docs)
        filename = f"devchat_export_{datetime.now().strftime('%Y%m%d')}.ris"
        media_type = "application/x-research-info-systems"
    
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Count": str(len(docs)),
        }
    )


def _generate_bibtex(docs) -> str:
    """Generate BibTeX format from documents."""
    entries = []
    
    for doc in docs:
        # Determine entry type
        item_type = getattr(doc, 'item_type', None) or 'misc'
        bibtex_type = _zotero_to_bibtex_type(item_type)
        
        # Create cite key: author_year_firstword
        authors = getattr(doc, 'authors', []) or []
        year = getattr(doc, 'year', None) or 'n.d.'
        title = getattr(doc, 'title', '') or 'Untitled'
        
        first_author = authors[0].split()[-1] if authors else 'Unknown'
        first_author = re.sub(r'[^a-zA-Z]', '', first_author)
        first_word = re.sub(r'[^a-zA-Z]', '', title.split()[0]) if title.split() else 'doc'
        cite_key = f"{first_author}{year}{first_word}".lower()
        
        # Build entry
        entry_lines = [f"@{bibtex_type}{{{cite_key},"]
        
        # Required fields
        entry_lines.append(f'  title = {{{_escape_bibtex(title)}}},')
        
        if authors:
            author_str = " and ".join(authors)
            entry_lines.append(f'  author = {{{_escape_bibtex(author_str)}}},')
        
        if year and year != 'n.d.':
            entry_lines.append(f'  year = {{{year}}},')
        
        # Optional fields
        if doi := getattr(doc, 'doi', None):
            entry_lines.append(f'  doi = {{{doi}}},')
        
        if journal := getattr(doc, 'journal', None):
            entry_lines.append(f'  journal = {{{_escape_bibtex(journal)}}},')
        
        if volume := getattr(doc, 'volume', None):
            entry_lines.append(f'  volume = {{{volume}}},')
        
        if issue := getattr(doc, 'issue', None):
            entry_lines.append(f'  number = {{{issue}}},')
        
        if pages := getattr(doc, 'pages', None):
            entry_lines.append(f'  pages = {{{pages}}},')
        
        if publisher := getattr(doc, 'publisher', None):
            entry_lines.append(f'  publisher = {{{_escape_bibtex(publisher)}}},')
        
        if url := getattr(doc, 'url', None):
            entry_lines.append(f'  url = {{{url}}},')
        
        if abstract := getattr(doc, 'abstract', None):
            # Truncate very long abstracts
            abstract_text = abstract[:2000] + "..." if len(abstract) > 2000 else abstract
            entry_lines.append(f'  abstract = {{{_escape_bibtex(abstract_text)}}},')
        
        if keywords := getattr(doc, 'keywords', None):
            if keywords:
                entry_lines.append(f'  keywords = {{{", ".join(keywords)}}},')
        
        entry_lines.append("}")
        entries.append("\n".join(entry_lines))
    
    return "\n\n".join(entries)


def _generate_ris(docs) -> str:
    """Generate RIS format from documents."""
    entries = []
    
    for doc in docs:
        lines = []
        
        # Type
        item_type = getattr(doc, 'item_type', None) or 'misc'
        ris_type = _zotero_to_ris_type(item_type)
        lines.append(f"TY  - {ris_type}")
        
        # Title
        if title := getattr(doc, 'title', None):
            lines.append(f"TI  - {title}")
        
        # Authors (one per line)
        for author in (getattr(doc, 'authors', None) or []):
            lines.append(f"AU  - {author}")
        
        # Year
        if year := getattr(doc, 'year', None):
            lines.append(f"PY  - {year}")
        
        # DOI
        if doi := getattr(doc, 'doi', None):
            lines.append(f"DO  - {doi}")
        
        # Journal
        if journal := getattr(doc, 'journal', None):
            lines.append(f"JO  - {journal}")
        
        # Volume
        if volume := getattr(doc, 'volume', None):
            lines.append(f"VL  - {volume}")
        
        # Issue
        if issue := getattr(doc, 'issue', None):
            lines.append(f"IS  - {issue}")
        
        # Pages
        if pages := getattr(doc, 'pages', None):
            if "-" in pages:
                sp, ep = pages.split("-", 1)
                lines.append(f"SP  - {sp.strip()}")
                lines.append(f"EP  - {ep.strip()}")
            else:
                lines.append(f"SP  - {pages}")
        
        # Publisher
        if publisher := getattr(doc, 'publisher', None):
            lines.append(f"PB  - {publisher}")
        
        # URL
        if url := getattr(doc, 'url', None):
            lines.append(f"UR  - {url}")
        
        # Abstract
        if abstract := getattr(doc, 'abstract', None):
            lines.append(f"AB  - {abstract}")
        
        # Keywords
        for kw in (getattr(doc, 'keywords', None) or []):
            lines.append(f"KW  - {kw}")
        
        # End record
        lines.append("ER  - ")
        
        entries.append("\n".join(lines))
    
    return "\n\n".join(entries)


def _escape_bibtex(text: str) -> str:
    """Escape special characters for BibTeX."""
    if not text:
        return ""
    # Escape special BibTeX characters
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("&", "\\&")
    text = text.replace("%", "\\%")
    text = text.replace("$", "\\$")
    text = text.replace("#", "\\#")
    text = text.replace("_", "\\_")
    return text


def _zotero_to_bibtex_type(item_type: str) -> str:
    """Convert Zotero item type to BibTeX entry type."""
    mapping = {
        "journalArticle": "article",
        "book": "book",
        "bookSection": "inbook",
        "conferencePaper": "inproceedings",
        "report": "techreport",
        "thesis": "phdthesis",
        "manuscript": "unpublished",
        "webpage": "online",
        "document": "misc",
    }
    return mapping.get(item_type, "misc")


def _zotero_to_ris_type(item_type: str) -> str:
    """Convert Zotero item type to RIS type."""
    mapping = {
        "journalArticle": "JOUR",
        "book": "BOOK",
        "bookSection": "CHAP",
        "conferencePaper": "CONF",
        "report": "RPRT",
        "thesis": "THES",
        "manuscript": "UNPB",
        "webpage": "ELEC",
        "document": "GEN",
    }
    return mapping.get(item_type, "GEN")


# =============================================================================
# Import Endpoints
# =============================================================================

@router.post("/bibliography/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(..., description="RIS, BibTeX, or CSV file"),
):
    """
    Parse a bibliography file and preview entries before importing.
    
    Supports:
    - RIS (.ris)
    - BibTeX (.bib)
    - CSV with columns: title, authors, year, doi, abstract, etc.
    """
    # Read file content
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    
    filename = file.filename or "unknown"
    
    # Detect format and parse
    if filename.endswith(".ris") or text.strip().startswith("TY  -"):
        entries, errors = _parse_ris(text)
    elif filename.endswith(".bib") or "@" in text[:100]:
        entries, errors = _parse_bibtex(text)
    elif filename.endswith(".csv"):
        entries, errors = _parse_csv(text)
    else:
        raise HTTPException(status_code=400, detail="Unknown file format. Supported: .ris, .bib, .csv")
    
    # Fast duplicate check: single DB query, then in-memory O(1) lookups
    duplicates = []
    if is_postgres_available():
        db = await get_db_session()
        if db:
            try:
                async with db:
                    from src.database.repository import DocumentRepository
                    # Single query to get all existing titles
                    existing_docs = await DocumentRepository.list_all(db, limit=50000)
                    existing_titles = {doc.title.lower().strip() for doc in existing_docs if doc.title}
                    existing_dois = {doc.doi.lower().strip() for doc in existing_docs if doc.doi}
                    
                    # O(1) in-memory lookup for each entry
                    for entry in entries:
                        title_normalized = entry.title.lower().strip()
                        doi_normalized = (entry.doi or "").lower().strip()
                        
                        if title_normalized in existing_titles:
                            duplicates.append(entry.title)
                        elif doi_normalized and doi_normalized in existing_dois:
                            duplicates.append(f"{entry.title} (DOI match)")
            except Exception as e:
                errors.append(f"Warning: Could not check for duplicates: {str(e)}")
    
    return ImportPreviewResponse(
        parsed_count=len(entries),
        entries=entries,
        errors=errors,
        duplicates=duplicates,
    )


async def _enrich_from_doi(entry: ImportedEntry) -> ImportedEntry:
    """Enrich entry metadata using DOI lookup from CrossRef."""
    if not entry.doi:
        return entry
    
    try:
        from src.ingestion.metadata.crossref_client import CrossRefClient
        
        client = CrossRefClient()
        work = await client.get_by_doi(entry.doi)
        
        if work:
            # Fill in missing fields from CrossRef
            if not entry.abstract and work.abstract:
                entry.abstract = work.abstract
            if not entry.year and work.year:
                entry.year = work.year
            if not entry.journal and work.journal:
                entry.journal = work.journal
            if not entry.publisher and work.publisher:
                entry.publisher = work.publisher
            if not entry.authors and work.authors:
                entry.authors = work.authors
            if not entry.url and work.url:
                entry.url = work.url
            # Add subjects as keywords if we don't have any
            if not entry.keywords and work.subject:
                entry.keywords = work.subject[:10]  # Limit to 10
            
            return entry
    except Exception as e:
        logger.warning(f"DOI enrichment failed for {entry.doi}: {e}")
    
    return entry


def _merge_metadata(existing_doc, entry: ImportedEntry) -> dict:
    """
    Merge metadata from import entry into existing document.
    Only updates fields that are empty/missing in existing doc.
    Returns dict of fields to update.
    """
    updates = {}
    
    # Only update if existing is empty and import has value
    if not existing_doc.doi and entry.doi:
        updates["doi"] = entry.doi
    if not existing_doc.abstract and entry.abstract:
        updates["abstract"] = entry.abstract
    if not existing_doc.year and entry.year:
        updates["year"] = entry.year
    if not existing_doc.journal and entry.journal:
        updates["journal"] = entry.journal
    if not existing_doc.publisher and entry.publisher:
        updates["publisher"] = entry.publisher
    if not existing_doc.volume and entry.volume:
        updates["volume"] = entry.volume
    if not existing_doc.issue and entry.issue:
        updates["issue"] = entry.issue
    if not existing_doc.pages and entry.pages:
        updates["pages"] = entry.pages
    if not existing_doc.url and entry.url:
        updates["url"] = entry.url
    if (not existing_doc.authors or len(existing_doc.authors) == 0) and entry.authors:
        updates["authors"] = entry.authors
    if (not existing_doc.keywords or len(existing_doc.keywords) == 0) and entry.keywords:
        updates["keywords"] = entry.keywords
    
    return updates


@router.post("/bibliography/import/confirm", response_model=ImportConfirmResponse)
async def confirm_import(request: ImportConfirmRequest):
    """
    Confirm and execute import of bibliography entries.
    
    Options:
    - skip_duplicates: Skip entries that match existing titles/DOIs
    - merge_duplicates: Update existing records with richer metadata from import
    - enrich_from_doi: Fetch metadata from CrossRef for entries with DOI
    """
    if not is_postgres_available():
        raise HTTPException(status_code=503, detail="Database not available")
    
    db = await get_db_session()
    if not db:
        raise HTTPException(status_code=503, detail="Could not connect to database")
    
    imported = 0
    skipped = 0
    updated = 0
    enriched = 0
    errors = []
    
    async with db:
        from src.database.repository import DocumentRepository
        import uuid
        
        # Get all existing docs for duplicate check and merge
        existing_docs = await DocumentRepository.list_all(db, limit=50000)
        existing_by_title = {doc.title.lower().strip(): doc for doc in existing_docs if doc.title}
        existing_by_doi = {doc.doi.lower().strip(): doc for doc in existing_docs if doc.doi}
        
        for entry in request.entries:
            try:
                title_normalized = entry.title.lower().strip()
                doi_normalized = (entry.doi or "").lower().strip()
                
                # Find existing duplicate
                existing_doc = existing_by_title.get(title_normalized)
                if not existing_doc and doi_normalized:
                    existing_doc = existing_by_doi.get(doi_normalized)
                
                if existing_doc:
                    # Handle duplicate
                    if request.merge_duplicates:
                        # Enrich entry from DOI first if enabled
                        if request.enrich_from_doi and entry.doi:
                            entry = await _enrich_from_doi(entry)
                            enriched += 1
                        
                        # Merge metadata into existing doc
                        updates = _merge_metadata(existing_doc, entry)
                        if updates:
                            await DocumentRepository.update(db, existing_doc.id, updates)
                            updated += 1
                        else:
                            skipped += 1  # No new data to merge
                    else:
                        skipped += 1
                    continue
                
                # New entry - enrich from DOI if enabled
                if request.enrich_from_doi and entry.doi:
                    entry = await _enrich_from_doi(entry)
                    enriched += 1
                
                # Create new document record
                doc_data = {
                    "id": str(uuid.uuid4()),
                    "title": entry.title,
                    "filename": f"imported_{uuid.uuid4().hex[:8]}.bib",
                    "authors": entry.authors,
                    "year": entry.year,
                    "doi": entry.doi,
                    "abstract": entry.abstract,
                    "item_type": entry.item_type or "journalArticle",
                    "journal": entry.journal,
                    "volume": entry.volume,
                    "issue": entry.issue,
                    "pages": entry.pages,
                    "publisher": entry.publisher,
                    "url": entry.url,
                    "keywords": entry.keywords,
                    "metadata_source": "bibliography_import",
                    "metadata_confidence": 0.95 if entry.doi else 0.9,
                    "needs_review": False,
                    "chunk_count": 0,
                    "page_count": 0,
                    "status": "pending",
                }
                
                await DocumentRepository.create(db, doc_data)
                imported += 1
                
            except Exception as e:
                errors.append(f"Error processing '{entry.title[:50]}...': {str(e)}")
    
    return ImportConfirmResponse(
        imported_count=imported,
        skipped_count=skipped,
        updated_count=updated,
        enriched_count=enriched,
        errors=errors,
    )


def _parse_ris(text: str) -> Tuple[List[ImportedEntry], List[str]]:
    """Parse RIS format."""
    entries = []
    errors = []
    
    # Split into records
    records = re.split(r'\n\s*\n', text.strip())
    
    for record in records:
        if not record.strip():
            continue
        
        try:
            entry = ImportedEntry(title="")
            authors = []
            keywords = []
            
            for line in record.split("\n"):
                if "  - " not in line:
                    continue
                    
                tag, value = line.split("  - ", 1)
                tag = tag.strip()
                value = value.strip()
                
                if tag == "TI" or tag == "T1":
                    entry.title = value
                elif tag == "AU" or tag == "A1":
                    authors.append(value)
                elif tag == "PY" or tag == "Y1":
                    try:
                        entry.year = int(value[:4])
                    except ValueError:
                        pass
                elif tag == "DO":
                    entry.doi = value
                elif tag == "AB":
                    entry.abstract = value
                elif tag == "TY":
                    entry.item_type = _ris_to_zotero_type(value)
                elif tag == "JO" or tag == "JF":
                    entry.journal = value
                elif tag == "VL":
                    entry.volume = value
                elif tag == "IS":
                    entry.issue = value
                elif tag == "SP":
                    entry.pages = value
                elif tag == "EP":
                    if entry.pages:
                        entry.pages = f"{entry.pages}-{value}"
                elif tag == "PB":
                    entry.publisher = value
                elif tag == "UR":
                    entry.url = value
                elif tag == "KW":
                    keywords.append(value)
            
            entry.authors = authors
            entry.keywords = keywords
            
            if entry.title:
                entries.append(entry)
                
        except Exception as e:
            errors.append(f"Error parsing RIS record: {str(e)}")
    
    return entries, errors


def _parse_bibtex(text: str) -> Tuple[List[ImportedEntry], List[str]]:
    """Parse BibTeX format."""
    entries = []
    errors = []
    
    # More robust BibTeX parsing - find entries by @ followed by type and brace
    # Then find matching closing brace by counting braces
    entry_starts = []
    for match in re.finditer(r'@(\w+)\s*\{', text):
        entry_starts.append((match.start(), match.end(), match.group(1)))
    
    for i, (start, content_start, entry_type) in enumerate(entry_starts):
        try:
            # Find the matching closing brace by counting
            brace_count = 1
            pos = content_start
            while pos < len(text) and brace_count > 0:
                if text[pos] == '{':
                    brace_count += 1
                elif text[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            if brace_count != 0:
                errors.append(f"Unmatched braces in entry at position {start}")
                continue
            
            entry_text = text[content_start:pos-1]
            
            # Get cite key (first thing before comma)
            if ',' not in entry_text:
                continue
            cite_key, fields_text = entry_text.split(',', 1)
            
            # Parse fields using a more robust approach
            # Match field = {value} or field = "value" or field = number
            field_pattern = r'(\w+)\s*=\s*(?:\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}|"([^"]*)"|(\d+))'
            fields = {}
            for field_match in re.finditer(field_pattern, fields_text):
                key = field_match.group(1).lower()
                # Value could be in group 2 (braces), 3 (quotes), or 4 (number)
                value = field_match.group(2) or field_match.group(3) or field_match.group(4) or ""
                value = value.strip()
                # Unescape BibTeX
                value = value.replace("\\{", "{").replace("\\}", "}")
                value = value.replace("\\&", "&").replace("\\_", "_")
                value = value.replace("\\%", "%").replace("\\$", "$")
                fields[key] = value
            
            # Parse authors
            authors = []
            if "author" in fields:
                author_str = fields["author"]
                # Split on " and "
                authors = [a.strip() for a in re.split(r'\s+and\s+', author_str)]
            
            # Parse year
            year = None
            if "year" in fields:
                try:
                    year = int(fields["year"][:4])
                except (ValueError, IndexError):
                    pass
            
            # Parse keywords
            keywords = []
            if "keywords" in fields:
                keywords = [k.strip() for k in fields["keywords"].split(",")]
            
            entry = ImportedEntry(
                title=fields.get("title", ""),
                authors=authors,
                year=year,
                doi=fields.get("doi"),
                abstract=fields.get("abstract"),
                item_type=_bibtex_to_zotero_type(entry_type.lower()),
                journal=fields.get("journal"),
                volume=fields.get("volume"),
                issue=fields.get("number"),
                pages=fields.get("pages"),
                publisher=fields.get("publisher"),
                url=fields.get("url"),
                keywords=keywords,
            )
            
            if entry.title:
                entries.append(entry)
                
        except Exception as e:
            errors.append(f"Error parsing BibTeX entry: {str(e)}")
    
    return entries, errors


def _parse_csv(text: str) -> Tuple[List[ImportedEntry], List[str]]:
    """Parse CSV format."""
    entries = []
    errors = []
    
    try:
        reader = csv.DictReader(io.StringIO(text))
        
        for row in reader:
            # Normalize column names (lowercase, strip)
            row = {k.lower().strip(): v for k, v in row.items()}
            
            # Parse authors (comma or semicolon separated)
            authors = []
            if "authors" in row and row["authors"]:
                sep = ";" if ";" in row["authors"] else ","
                authors = [a.strip() for a in row["authors"].split(sep)]
            elif "author" in row and row["author"]:
                authors = [row["author"].strip()]
            
            # Parse year
            year = None
            if "year" in row and row["year"]:
                try:
                    year = int(row["year"])
                except ValueError:
                    pass
            
            # Parse keywords
            keywords = []
            if "keywords" in row and row["keywords"]:
                sep = ";" if ";" in row["keywords"] else ","
                keywords = [k.strip() for k in row["keywords"].split(sep)]
            
            entry = ImportedEntry(
                title=row.get("title", ""),
                authors=authors,
                year=year,
                doi=row.get("doi"),
                abstract=row.get("abstract"),
                item_type=row.get("item_type") or row.get("type") or "journalArticle",
                journal=row.get("journal"),
                volume=row.get("volume"),
                issue=row.get("issue"),
                pages=row.get("pages"),
                publisher=row.get("publisher"),
                url=row.get("url"),
                keywords=keywords,
            )
            
            if entry.title:
                entries.append(entry)
                
    except Exception as e:
        errors.append(f"Error parsing CSV: {str(e)}")
    
    return entries, errors


def _ris_to_zotero_type(ris_type: str) -> str:
    """Convert RIS type to Zotero item type."""
    mapping = {
        "JOUR": "journalArticle",
        "BOOK": "book",
        "CHAP": "bookSection",
        "CONF": "conferencePaper",
        "RPRT": "report",
        "THES": "thesis",
        "UNPB": "manuscript",
        "ELEC": "webpage",
        "GEN": "document",
    }
    return mapping.get(ris_type, "document")


def _bibtex_to_zotero_type(bibtex_type: str) -> str:
    """Convert BibTeX entry type to Zotero item type."""
    mapping = {
        "article": "journalArticle",
        "book": "book",
        "inbook": "bookSection",
        "incollection": "bookSection",
        "inproceedings": "conferencePaper",
        "conference": "conferencePaper",
        "techreport": "report",
        "phdthesis": "thesis",
        "mastersthesis": "thesis",
        "unpublished": "manuscript",
        "online": "webpage",
        "misc": "document",
    }
    return mapping.get(bibtex_type, "document")
