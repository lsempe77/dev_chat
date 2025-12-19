"""
DevChat v2.0 SOTA - Bibliography Parser

Parse bibliography files for metadata:
- RIS format (.ris) - EndNote, Zotero, Mendeley
- BibTeX format (.bib) - LaTeX, academic tools
- CSV format (.csv) - Spreadsheet exports

Supports fuzzy matching of bibliography entries to PDF files.
"""

import csv
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator
from pydantic import BaseModel, Field
from dataclasses import dataclass

from src.utils.logging import get_logger

logger = get_logger(__name__)


class BibliographyEntry(BaseModel):
    """Parsed bibliography entry from RIS/BibTeX/CSV."""
    
    # Core fields
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    
    # Identifiers
    doi: Optional[str] = None
    isbn: Optional[str] = None
    pmid: Optional[str] = None  # PubMed ID
    
    # Publication info
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    
    # Content
    abstract: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    
    # Links
    url: Optional[str] = None
    pdf_filename: Optional[str] = None  # For matching
    
    # Entry type
    entry_type: Optional[str] = None  # article, book, inproceedings, etc.
    
    # Source tracking
    source_format: str = "unknown"  # ris, bibtex, csv
    source_key: Optional[str] = None  # Original key/ID in bib file


class RISParser:
    """Parse RIS format bibliography files."""
    
    # RIS tag mappings
    TAG_MAP = {
        "TY": "entry_type",
        "TI": "title",
        "T1": "title",
        "AU": "author",
        "A1": "author",
        "PY": "year",
        "Y1": "year",
        "DA": "year",
        "DO": "doi",
        "JO": "journal",
        "JF": "journal",
        "T2": "journal",
        "VL": "volume",
        "IS": "issue",
        "SP": "start_page",
        "EP": "end_page",
        "PB": "publisher",
        "AB": "abstract",
        "N2": "abstract",
        "KW": "keyword",
        "UR": "url",
        "L1": "pdf_link",
        "L2": "pdf_link",
        "SN": "issn_isbn",
        "ID": "source_key",
    }
    
    # RIS type mappings
    TYPE_MAP = {
        "JOUR": "article",
        "BOOK": "book",
        "CHAP": "book-chapter",
        "CONF": "conference-paper",
        "RPRT": "report",
        "THES": "thesis",
        "ELEC": "webpage",
        "GEN": "generic",
    }
    
    def parse_file(self, filepath: Path) -> List[BibliographyEntry]:
        """Parse RIS file and return list of entries."""
        entries = []
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Split into records (ER marks end of record)
            records = re.split(r'\nER\s*-', content)
            
            for record in records:
                if record.strip():
                    entry = self._parse_record(record)
                    if entry:
                        entries.append(entry)
            
            logger.info(f"Parsed {len(entries)} entries from RIS file: {filepath.name}")
            return entries
            
        except Exception as e:
            logger.error(f"Error parsing RIS file {filepath}: {e}")
            return []
    
    def _parse_record(self, record: str) -> Optional[BibliographyEntry]:
        """Parse a single RIS record."""
        fields: Dict[str, Any] = {
            "authors": [],
            "keywords": [],
            "source_format": "ris",
        }
        
        current_tag = None
        current_value = []
        
        for line in record.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            # Check for new tag (format: "XX  - value")
            match = re.match(r'^([A-Z][A-Z0-9])\s+-\s*(.*)', line)
            
            if match:
                # Save previous tag
                if current_tag and current_value:
                    self._add_field(fields, current_tag, " ".join(current_value))
                
                current_tag = match.group(1)
                current_value = [match.group(2)] if match.group(2) else []
            else:
                # Continuation of previous value
                if current_tag:
                    current_value.append(line)
        
        # Save last tag
        if current_tag and current_value:
            self._add_field(fields, current_tag, " ".join(current_value))
        
        # Must have at least a title
        if not fields.get("title"):
            return None
        
        return BibliographyEntry(**fields)
    
    def _add_field(self, fields: Dict, tag: str, value: str) -> None:
        """Add a field value based on RIS tag."""
        value = value.strip()
        if not value:
            return
        
        field_name = self.TAG_MAP.get(tag)
        if not field_name:
            return
        
        if field_name == "author":
            # Parse author name (usually "Last, First")
            fields["authors"].append(self._parse_author(value))
        elif field_name == "keyword":
            fields["keywords"].append(value)
        elif field_name == "year":
            # Extract year from various formats
            year_match = re.search(r'(\d{4})', value)
            if year_match:
                fields["year"] = int(year_match.group(1))
        elif field_name == "entry_type":
            fields["entry_type"] = self.TYPE_MAP.get(value, value.lower())
        elif field_name == "start_page":
            fields["pages"] = value
        elif field_name == "end_page":
            if fields.get("pages"):
                fields["pages"] = f"{fields['pages']}-{value}"
            else:
                fields["pages"] = value
        elif field_name == "pdf_link":
            if not fields.get("pdf_filename"):
                # Extract filename from path
                if "/" in value or "\\" in value:
                    fields["pdf_filename"] = Path(value).name
                else:
                    fields["pdf_filename"] = value
        else:
            fields[field_name] = value
    
    def _parse_author(self, author_str: str) -> str:
        """Parse RIS author format to 'First Last'."""
        if "," in author_str:
            parts = author_str.split(",", 1)
            last = parts[0].strip()
            first = parts[1].strip() if len(parts) > 1 else ""
            return f"{first} {last}".strip()
        return author_str


class BibTeXParser:
    """Parse BibTeX format bibliography files."""
    
    def parse_file(self, filepath: Path) -> List[BibliographyEntry]:
        """Parse BibTeX file and return list of entries."""
        entries = []
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Find all entries: @type{key, ... }
            entry_pattern = r'@(\w+)\s*\{([^,]+),([^@]*(?:\{[^}]*\}[^@]*)*)\}'
            
            for match in re.finditer(entry_pattern, content, re.DOTALL):
                entry_type = match.group(1).lower()
                entry_key = match.group(2).strip()
                entry_body = match.group(3)
                
                entry = self._parse_entry(entry_type, entry_key, entry_body)
                if entry:
                    entries.append(entry)
            
            logger.info(f"Parsed {len(entries)} entries from BibTeX file: {filepath.name}")
            return entries
            
        except Exception as e:
            logger.error(f"Error parsing BibTeX file {filepath}: {e}")
            return []
    
    def _parse_entry(self, entry_type: str, key: str, body: str) -> Optional[BibliographyEntry]:
        """Parse a single BibTeX entry."""
        fields = {
            "entry_type": entry_type,
            "source_key": key,
            "source_format": "bibtex",
            "authors": [],
            "keywords": [],
        }
        
        # Parse fields: field = {value} or field = "value"
        field_pattern = r'(\w+)\s*=\s*(?:\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}|"([^"]*)")'
        
        for match in re.finditer(field_pattern, body):
            field_name = match.group(1).lower()
            value = match.group(2) or match.group(3) or ""
            value = value.strip()
            
            if field_name == "title":
                # Remove LaTeX formatting
                fields["title"] = self._clean_latex(value)
            elif field_name == "author":
                # BibTeX uses "and" to separate authors
                for author in value.split(" and "):
                    fields["authors"].append(self._parse_author(author.strip()))
            elif field_name == "year":
                try:
                    fields["year"] = int(value)
                except ValueError:
                    pass
            elif field_name == "doi":
                fields["doi"] = value
            elif field_name in ("journal", "journaltitle"):
                fields["journal"] = self._clean_latex(value)
            elif field_name == "volume":
                fields["volume"] = value
            elif field_name == "number":
                fields["issue"] = value
            elif field_name == "pages":
                fields["pages"] = value.replace("--", "-")
            elif field_name == "publisher":
                fields["publisher"] = self._clean_latex(value)
            elif field_name == "abstract":
                fields["abstract"] = self._clean_latex(value)
            elif field_name in ("keywords", "keyword"):
                for kw in re.split(r'[,;]', value):
                    if kw.strip():
                        fields["keywords"].append(kw.strip())
            elif field_name == "url":
                fields["url"] = value
            elif field_name == "file":
                # Mendeley/Zotero file path format
                parts = value.split(":")
                for part in parts:
                    if part.endswith(".pdf"):
                        fields["pdf_filename"] = Path(part).name
                        break
            elif field_name == "isbn":
                fields["isbn"] = value
        
        if not fields.get("title"):
            return None
        
        return BibliographyEntry(**fields)
    
    def _parse_author(self, author_str: str) -> str:
        """Parse BibTeX author format to 'First Last'."""
        # Handle "Last, First" format
        if "," in author_str:
            parts = author_str.split(",", 1)
            last = parts[0].strip()
            first = parts[1].strip() if len(parts) > 1 else ""
            return f"{first} {last}".strip()
        return self._clean_latex(author_str)
    
    def _clean_latex(self, text: str) -> str:
        """Remove LaTeX formatting from text."""
        # Remove braces
        text = re.sub(r'\{([^{}]*)\}', r'\1', text)
        # Remove common LaTeX commands
        text = re.sub(r'\\[a-zA-Z]+\s*', '', text)
        # Remove escapes
        text = text.replace("\\", "")
        return text.strip()


class CSVParser:
    """Parse CSV format bibliography files."""
    
    # Common column name mappings
    COLUMN_MAP = {
        "title": ["title", "Title", "TITLE", "paper_title", "article_title"],
        "authors": ["authors", "author", "Author", "AUTHORS", "creator"],
        "year": ["year", "Year", "YEAR", "publication_year", "pub_year", "date"],
        "doi": ["doi", "DOI", "Doi"],
        "journal": ["journal", "Journal", "JOURNAL", "publication", "source"],
        "abstract": ["abstract", "Abstract", "ABSTRACT", "description"],
        "keywords": ["keywords", "Keywords", "KEYWORDS", "tags"],
        "url": ["url", "URL", "link"],
        "pdf_filename": ["pdf", "PDF", "filename", "file", "pdf_file"],
    }
    
    def parse_file(self, filepath: Path) -> List[BibliographyEntry]:
        """Parse CSV file and return list of entries."""
        entries = []
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                # Detect delimiter
                sample = f.read(4096)
                f.seek(0)
                
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample)
                except csv.Error:
                    dialect = csv.excel
                
                reader = csv.DictReader(f, dialect=dialect)
                
                # Map columns
                column_mapping = self._map_columns(reader.fieldnames or [])
                
                for row in reader:
                    entry = self._parse_row(row, column_mapping)
                    if entry:
                        entries.append(entry)
            
            logger.info(f"Parsed {len(entries)} entries from CSV file: {filepath.name}")
            return entries
            
        except Exception as e:
            logger.error(f"Error parsing CSV file {filepath}: {e}")
            return []
    
    def _map_columns(self, fieldnames: List[str]) -> Dict[str, str]:
        """Map CSV column names to standard field names."""
        mapping = {}
        
        for field, variants in self.COLUMN_MAP.items():
            for variant in variants:
                if variant in fieldnames:
                    mapping[field] = variant
                    break
        
        return mapping
    
    def _parse_row(self, row: Dict[str, str], mapping: Dict[str, str]) -> Optional[BibliographyEntry]:
        """Parse a single CSV row."""
        title_col = mapping.get("title")
        if not title_col or not row.get(title_col):
            return None
        
        fields = {
            "title": row[title_col],
            "source_format": "csv",
            "authors": [],
            "keywords": [],
        }
        
        # Parse authors
        authors_col = mapping.get("authors")
        if authors_col and row.get(authors_col):
            # Try different separators
            authors_str = row[authors_col]
            if ";" in authors_str:
                fields["authors"] = [a.strip() for a in authors_str.split(";") if a.strip()]
            elif " and " in authors_str.lower():
                fields["authors"] = [a.strip() for a in re.split(r'\s+and\s+', authors_str, flags=re.IGNORECASE) if a.strip()]
            elif "," in authors_str and authors_str.count(",") > 1:
                # Multiple commas likely means comma-separated
                fields["authors"] = [a.strip() for a in authors_str.split(",") if a.strip()]
            else:
                fields["authors"] = [authors_str.strip()]
        
        # Parse year
        year_col = mapping.get("year")
        if year_col and row.get(year_col):
            year_match = re.search(r'(\d{4})', row[year_col])
            if year_match:
                fields["year"] = int(year_match.group(1))
        
        # Parse other fields
        for field in ["doi", "journal", "abstract", "url", "pdf_filename"]:
            col = mapping.get(field)
            if col and row.get(col):
                fields[field] = row[col].strip()
        
        # Parse keywords
        kw_col = mapping.get("keywords")
        if kw_col and row.get(kw_col):
            for kw in re.split(r'[,;]', row[kw_col]):
                if kw.strip():
                    fields["keywords"].append(kw.strip())
        
        return BibliographyEntry(**fields)


class BibliographyParser:
    """
    Unified bibliography parser supporting multiple formats.
    
    Automatically detects format from file extension.
    """
    
    def __init__(self):
        self.ris_parser = RISParser()
        self.bibtex_parser = BibTeXParser()
        self.csv_parser = CSVParser()
    
    def parse_file(self, filepath: Path) -> List[BibliographyEntry]:
        """
        Parse bibliography file (auto-detect format).
        
        Args:
            filepath: Path to .ris, .bib, or .csv file
            
        Returns:
            List of BibliographyEntry objects
        """
        suffix = filepath.suffix.lower()
        
        if suffix == ".ris":
            return self.ris_parser.parse_file(filepath)
        elif suffix in (".bib", ".bibtex"):
            return self.bibtex_parser.parse_file(filepath)
        elif suffix == ".csv":
            return self.csv_parser.parse_file(filepath)
        else:
            logger.warning(f"Unknown bibliography format: {suffix}")
            # Try to detect from content
            return self._parse_with_detection(filepath)
    
    def _parse_with_detection(self, filepath: Path) -> List[BibliographyEntry]:
        """Try to detect format from file content."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(1000)
            
            if "TY  -" in content or "ER  -" in content:
                return self.ris_parser.parse_file(filepath)
            elif content.strip().startswith("@"):
                return self.bibtex_parser.parse_file(filepath)
            elif "," in content and "\n" in content:
                return self.csv_parser.parse_file(filepath)
            else:
                logger.error(f"Could not detect bibliography format: {filepath}")
                return []
                
        except Exception as e:
            logger.error(f"Error detecting format for {filepath}: {e}")
            return []
    
    def parse_directory(self, directory: Path) -> List[BibliographyEntry]:
        """Parse all bibliography files in a directory."""
        entries = []
        
        for ext in [".ris", ".bib", ".bibtex", ".csv"]:
            for filepath in directory.glob(f"*{ext}"):
                entries.extend(self.parse_file(filepath))
        
        return entries


# Convenience functions
def parse_bibliography(filepath: Path) -> List[BibliographyEntry]:
    """Parse a bibliography file."""
    parser = BibliographyParser()
    return parser.parse_file(filepath)
