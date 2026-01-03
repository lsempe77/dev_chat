"""
Bibliography File Parsers

Parses RIS, BibTeX, and CSV files into BibliographyEntry objects.
"""

import re
import csv
import io
from typing import Optional
from .bibliography_matcher import BibliographyEntry


# =============================================================================
# RIS Parser
# =============================================================================

RIS_TAG_MAP = {
    'TI': 'title',
    'T1': 'title',
    'AU': 'author',
    'A1': 'author',
    'PY': 'year',
    'Y1': 'year',
    'DA': 'year',
    'DO': 'doi',
    'JO': 'journal',
    'JF': 'journal',
    'T2': 'journal',
    'AB': 'abstract',
    'N2': 'abstract',
    'KW': 'keyword',
    'ID': 'id',
}


def parse_ris(content: str) -> list[BibliographyEntry]:
    """
    Parse RIS format bibliography file.
    
    RIS format uses tags like:
    TY  - JOUR
    TI  - Title of the article
    AU  - Author Name
    PY  - 2020
    DO  - 10.1234/example
    ER  -
    """
    entries = []
    current = {}
    authors = []
    keywords = []
    entry_id = 0
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Parse tag and value
        match = re.match(r'^([A-Z][A-Z0-9])\s*-\s*(.*)$', line)
        if not match:
            continue
        
        tag, value = match.groups()
        value = value.strip()
        
        if tag == 'TY':  # Start of new entry
            if current:
                # Save previous entry
                entries.append(_create_entry_from_ris(
                    current, authors, keywords, entry_id
                ))
                entry_id += 1
            current = {}
            authors = []
            keywords = []
        
        elif tag == 'ER':  # End of entry
            if current:
                entries.append(_create_entry_from_ris(
                    current, authors, keywords, entry_id
                ))
                entry_id += 1
            current = {}
            authors = []
            keywords = []
        
        elif tag in ('AU', 'A1'):
            authors.append(value)
        
        elif tag == 'KW':
            keywords.append(value)
        
        elif tag in RIS_TAG_MAP:
            field = RIS_TAG_MAP[tag]
            if field not in current:
                current[field] = value
    
    # Handle last entry if no ER tag
    if current:
        entries.append(_create_entry_from_ris(
            current, authors, keywords, entry_id
        ))
    
    return entries


def _create_entry_from_ris(
    data: dict,
    authors: list[str],
    keywords: list[str],
    entry_id: int
) -> BibliographyEntry:
    """Create BibliographyEntry from parsed RIS data."""
    # Extract year from various formats
    year = None
    year_str = data.get('year', '')
    if year_str:
        year_match = re.search(r'(19|20)\d{2}', year_str)
        if year_match:
            year = int(year_match.group())
    
    return BibliographyEntry(
        id=data.get('id', f'ris_{entry_id}'),
        title=data.get('title', ''),
        authors=authors,
        year=year,
        doi=data.get('doi'),
        journal=data.get('journal'),
        abstract=data.get('abstract'),
        keywords=keywords,
        source_format='ris',
        raw_data=data
    )


# =============================================================================
# BibTeX Parser
# =============================================================================

def parse_bibtex(content: str) -> list[BibliographyEntry]:
    """
    Parse BibTeX format bibliography file.
    
    BibTeX format:
    @article{citekey,
      title = {Title of the article},
      author = {Last, First and Other, Author},
      year = {2020},
      doi = {10.1234/example}
    }
    """
    entries = []
    
    # Find all entries
    entry_pattern = r'@(\w+)\s*\{([^,]+),\s*(.*?)\n\s*\}'
    
    for match in re.finditer(entry_pattern, content, re.DOTALL):
        entry_type, cite_key, fields_str = match.groups()
        
        # Parse fields
        fields = {}
        # Match field = {value} or field = "value" or field = value
        field_pattern = r'(\w+)\s*=\s*(?:\{([^}]*)\}|"([^"]*)"|(\S+))'
        
        for field_match in re.finditer(field_pattern, fields_str):
            field_name = field_match.group(1).lower()
            # Get whichever capture group matched
            value = field_match.group(2) or field_match.group(3) or field_match.group(4) or ''
            fields[field_name] = value.strip()
        
        # Parse authors (split by "and")
        authors = []
        if 'author' in fields:
            author_str = fields['author']
            authors = [a.strip() for a in re.split(r'\s+and\s+', author_str, flags=re.IGNORECASE)]
        
        # Parse year
        year = None
        if 'year' in fields:
            year_match = re.search(r'(19|20)\d{2}', fields['year'])
            if year_match:
                year = int(year_match.group())
        
        # Parse keywords
        keywords = []
        if 'keywords' in fields:
            keywords = [k.strip() for k in fields['keywords'].split(',')]
        
        entries.append(BibliographyEntry(
            id=cite_key,
            title=fields.get('title', ''),
            authors=authors,
            year=year,
            doi=fields.get('doi'),
            journal=fields.get('journal') or fields.get('booktitle'),
            abstract=fields.get('abstract'),
            keywords=keywords,
            source_format='bibtex',
            raw_data=fields
        ))
    
    return entries


# =============================================================================
# CSV Parser
# =============================================================================

# Common column name variations
CSV_COLUMN_MAP = {
    'title': ['title', 'name', 'document title', 'article title'],
    'authors': ['authors', 'author', 'creator', 'by'],
    'year': ['year', 'publication year', 'pub year', 'date', 'publication date'],
    'doi': ['doi', 'digital object identifier'],
    'journal': ['journal', 'publication', 'source', 'container'],
    'abstract': ['abstract', 'summary', 'description'],
    'keywords': ['keywords', 'tags', 'subjects'],
}


def _find_column(headers: list[str], field: str) -> Optional[int]:
    """Find the index of a column by trying common variations."""
    variations = CSV_COLUMN_MAP.get(field, [field])
    headers_lower = [h.lower().strip() for h in headers]
    
    for var in variations:
        if var.lower() in headers_lower:
            return headers_lower.index(var.lower())
    
    return None


def parse_csv(content: str) -> list[BibliographyEntry]:
    """
    Parse CSV format bibliography file.
    
    Attempts to detect column mappings automatically.
    """
    entries = []
    
    # Parse CSV
    reader = csv.reader(io.StringIO(content))
    headers = next(reader, None)
    
    if not headers:
        return entries
    
    # Find column indices
    title_idx = _find_column(headers, 'title')
    authors_idx = _find_column(headers, 'authors')
    year_idx = _find_column(headers, 'year')
    doi_idx = _find_column(headers, 'doi')
    journal_idx = _find_column(headers, 'journal')
    abstract_idx = _find_column(headers, 'abstract')
    keywords_idx = _find_column(headers, 'keywords')
    
    for i, row in enumerate(reader):
        if not row:
            continue
        
        def get_cell(idx):
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return None
        
        # Parse authors (comma or semicolon separated)
        authors = []
        authors_str = get_cell(authors_idx)
        if authors_str:
            authors = [a.strip() for a in re.split(r'[;,]', authors_str) if a.strip()]
        
        # Parse year
        year = None
        year_str = get_cell(year_idx)
        if year_str:
            year_match = re.search(r'(19|20)\d{2}', year_str)
            if year_match:
                year = int(year_match.group())
        
        # Parse keywords
        keywords = []
        keywords_str = get_cell(keywords_idx)
        if keywords_str:
            keywords = [k.strip() for k in re.split(r'[;,]', keywords_str) if k.strip()]
        
        # Create raw data dict
        raw_data = {headers[j]: row[j] for j in range(min(len(headers), len(row)))}
        
        entries.append(BibliographyEntry(
            id=f'csv_{i}',
            title=get_cell(title_idx) or '',
            authors=authors,
            year=year,
            doi=get_cell(doi_idx),
            journal=get_cell(journal_idx),
            abstract=get_cell(abstract_idx),
            keywords=keywords,
            source_format='csv',
            raw_data=raw_data
        ))
    
    return entries


# =============================================================================
# Auto-detect and Parse
# =============================================================================

def detect_format(content: str, filename: str = '') -> str:
    """Detect bibliography file format."""
    filename_lower = filename.lower()
    
    if filename_lower.endswith('.ris'):
        return 'ris'
    elif filename_lower.endswith('.bib'):
        return 'bibtex'
    elif filename_lower.endswith('.csv'):
        return 'csv'
    
    # Try to detect from content
    if re.search(r'^TY\s+-\s+', content, re.MULTILINE):
        return 'ris'
    elif re.search(r'@\w+\s*\{', content):
        return 'bibtex'
    elif ',' in content.split('\n')[0]:
        return 'csv'
    
    return 'unknown'


def parse_bibliography(content: str, filename: str = '') -> list[BibliographyEntry]:
    """
    Auto-detect format and parse bibliography file.
    
    Args:
        content: File content as string
        filename: Original filename (helps with format detection)
    
    Returns:
        List of BibliographyEntry objects
    """
    format_type = detect_format(content, filename)
    
    if format_type == 'ris':
        return parse_ris(content)
    elif format_type == 'bibtex':
        return parse_bibtex(content)
    elif format_type == 'csv':
        return parse_csv(content)
    else:
        raise ValueError(f"Could not detect bibliography format for: {filename}")
