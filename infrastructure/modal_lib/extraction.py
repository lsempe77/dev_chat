"""
PDF Extraction Module

Contains MinerU extraction logic and text extraction helpers.

MinerU Configuration Notes (as of 2.7.x):
- MINERU_TABLE_MERGE_ENABLE: Enables table merging for split tables (default: true)
- MINERU_TABLE_ENABLE: Enables table parsing (default: true)
- Backend options: pipeline (faster), hybrid-* (more accurate), vlm-* (VLM-based)
- Category IDs in model.json: 3=Figure, 5=Table, 6=Table caption
"""

import copy
import json
import os
import re
import shutil
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# Ensure table merge is enabled (MinerU's built-in split table handling)
os.environ.setdefault("MINERU_TABLE_MERGE_ENABLE", "true")
os.environ.setdefault("MINERU_TABLE_ENABLE", "true")


# ============================================================================
# Table Filtering Helpers (Level 1 - During Extraction)
# ============================================================================

# Pattern to detect figures mislabeled as tables
FIGURE_CAPTION_PATTERN = re.compile(r'\b(figure|fig\.?)\s*\d', re.IGNORECASE)

# Minimum rows for a valid table (single-row often = diagram/legend)
MIN_TABLE_ROWS = 2


def _get_table_caption(item: dict) -> str:
    """Extract caption text from table item."""
    caption_list = item.get("table_caption", [])
    if caption_list and isinstance(caption_list, list):
        return caption_list[0] if caption_list else ""
    return str(caption_list) if caption_list else ""


def _is_likely_figure(item: dict) -> bool:
    """Check if a 'table' is actually a figure based on caption."""
    caption = _get_table_caption(item)
    return bool(FIGURE_CAPTION_PATTERN.search(caption))


def _count_table_rows(body: str) -> int:
    """Count rows in table HTML."""
    if not body:
        return 0
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body, 'html.parser')
        return len(soup.find_all('tr'))
    except Exception:
        # Fallback: count <tr> tags manually
        return body.lower().count('<tr')


def _is_empty_table(item: dict) -> bool:
    """Check if table has empty or trivial body."""
    body = item.get("table_body", "")
    if not body or not body.strip():
        return True
    # Check for empty table HTML
    if body.strip() in ["<table></table>", "<html><body><table></table></body></html>"]:
        return True
    return False


def _get_extraction_metadata(item: dict) -> dict:
    """Generate metadata about the extracted table for debugging/post-processing."""
    body = item.get("table_body", "")
    caption = _get_table_caption(item)
    
    row_count = _count_table_rows(body)
    
    # Try to get column count
    col_count = 0
    text_length = 0
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body, 'html.parser')
        rows = soup.find_all('tr')
        if rows:
            col_count = max(len(row.find_all(['td', 'th'])) for row in rows)
        text_length = len(soup.get_text(strip=True))
    except Exception:
        col_count = body.count('</td>') + body.count('</th>')
        text_length = len(re.sub(r'<[^>]+>', '', body))
    
    return {
        "row_count": row_count,
        "col_count": col_count,
        "text_length": text_length,
        "caption_length": len(caption),
        "is_figure_caption": _is_likely_figure(item),
        "extraction_timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# MinerU Extraction
# ============================================================================

def run_mineru(pdf_path: Path, save_debug_output: bool = False) -> dict:
    """
    Run MinerU extraction on a PDF file using MinerU 2.6.x+ API.
    
    Args:
        pdf_path: Path to PDF file
        save_debug_output: If True, save model.json for debugging layout detection
    
    Returns:
        dict with extraction results including:
        - tables: List of valid tables (filtered for empty/figures)
        - figures_detected: Tables that were actually figures
        - artifacts_filtered: Tables filtered as artifacts
        - model_output: Raw model.json if save_debug_output=True
    """
    print(f"  Running MinerU on {pdf_path.name}...")
    print(f"    MINERU_TABLE_MERGE_ENABLE={os.environ.get('MINERU_TABLE_MERGE_ENABLE', 'not set')}")
    
    try:
        # MinerU 2.6.x+ imports
        from mineru.cli.common import prepare_env, read_fn
        from mineru.data.data_reader_writer import FileBasedDataWriter
        from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import union_make as pipeline_union_make
        from mineru.backend.pipeline.model_json_to_middle_json import result_to_middle_json as pipeline_result_to_middle_json
        from mineru.utils.enum_class import MakeMode
        
        # Read PDF bytes
        pdf_bytes = read_fn(str(pdf_path))
        pdf_file_name = pdf_path.stem
        
        # Create output directory
        output_dir = tempfile.mkdtemp(prefix="mineru_")
        
        # Run pipeline analysis with table and formula extraction
        # NOTE: For higher accuracy, consider using hybrid-auto-engine backend
        # which uses VLM but requires more GPU resources
        infer_results, all_image_lists, all_pdf_docs, lang_list, ocr_enabled_list = pipeline_doc_analyze(
            [pdf_bytes],
            ["en"],  # Language - improves OCR accuracy
            parse_method="auto",  # auto, txt, or ocr
            formula_enable=True,
            table_enable=True,
        )
        
        if not infer_results:
            return {"success": False, "error": "No results from pipeline analysis"}
        
        # Process first (and only) PDF
        model_list = infer_results[0]
        images_list = all_image_lists[0]
        pdf_doc = all_pdf_docs[0]
        _lang = lang_list[0]
        _ocr_enable = ocr_enabled_list[0]
        
        # Save raw model output for debugging if requested
        # model.json contains category_id: 3=Figure, 5=Table, 6=Table caption
        model_output = None
        if save_debug_output:
            model_output = copy.deepcopy(model_list)
        
        # Prepare output directories
        local_image_dir, local_md_dir = prepare_env(output_dir, pdf_file_name, "auto")
        image_writer = FileBasedDataWriter(local_image_dir)
        
        # Convert to middle JSON
        middle_json = pipeline_result_to_middle_json(
            model_list, images_list, pdf_doc, image_writer, _lang, _ocr_enable, True
        )
        
        pdf_info = middle_json["pdf_info"]
        
        # Get page count
        page_count = len(pdf_info) if isinstance(pdf_info, list) else pdf_info.get("page_num", 0)
        
        # Generate markdown content
        image_dir = os.path.basename(local_image_dir)
        md_content = pipeline_union_make(pdf_info, MakeMode.MM_MD, image_dir)
        
        # Generate content list for structured extraction
        content_list = pipeline_union_make(pdf_info, MakeMode.CONTENT_LIST, image_dir)
        
        # ================================================================
        # LEVEL 1 TABLE FILTERING (During Extraction)
        # Filter out artifacts before storing to save processing time
        # ================================================================
        tables = []
        figures_detected = []  # Track figures mislabeled as tables
        artifacts_filtered = []  # Track filtered artifacts for debugging
        
        if isinstance(content_list, list):
            for item in content_list:
                if not isinstance(item, dict) or item.get("type") != "table":
                    continue
                
                caption = _get_table_caption(item)
                page_idx = item.get("page_idx", "?")
                
                # Check 1: Skip empty tables
                if _is_empty_table(item):
                    print(f"    [L1 Filter] Empty table on page {page_idx}")
                    artifacts_filtered.append({
                        "reason": "empty_body",
                        "page_idx": page_idx,
                        "caption": caption[:50] if caption else None,
                    })
                    continue
                
                # Check 2: Detect figures mislabeled as tables
                if _is_likely_figure(item):
                    print(f"    [L1 Filter] Figure detected: '{caption[:50]}...'")
                    figures_detected.append(item)
                    continue
                
                # Check 3: Skip single-row artifacts (unless caption says "Table N")
                row_count = _count_table_rows(item.get("table_body", ""))
                has_table_caption = bool(re.match(r'Table\s*\d', caption, re.IGNORECASE))
                
                if row_count < MIN_TABLE_ROWS and not has_table_caption:
                    print(f"    [L1 Filter] Single-row artifact on page {page_idx}: {row_count} rows")
                    artifacts_filtered.append({
                        "reason": "single_row",
                        "page_idx": page_idx,
                        "row_count": row_count,
                        "caption": caption[:50] if caption else None,
                    })
                    continue
                
                # Add extraction metadata for post-processing
                item["_extraction_meta"] = _get_extraction_metadata(item)
                tables.append(item)
        
        print(f"    Tables extracted: {len(tables)} valid, {len(figures_detected)} figures, {len(artifacts_filtered)} artifacts filtered")
        
        # Extract formulas from content list
        formulas = []
        if isinstance(content_list, list):
            for item in content_list:
                if isinstance(item, dict) and item.get("type") in ["equation", "formula"]:
                    formulas.append(item)
        
        # Clean up temp directory
        shutil.rmtree(output_dir, ignore_errors=True)
        
        return {
            "success": True,
            "content": md_content if isinstance(md_content, str) else str(md_content),
            "content_list": content_list,  # Full structured content with page info
            "tables": tables,  # Filtered valid tables
            "figures_detected": figures_detected,  # Tables that were actually figures
            "artifacts_filtered": artifacts_filtered,  # Metadata about filtered items
            "formulas": formulas,
            "page_count": page_count,
            "title": extract_title(md_content if isinstance(md_content, str) else ""),
            "authors": extract_authors_from_text(md_content if isinstance(md_content, str) else ""),
            "year": extract_year_from_text(md_content if isinstance(md_content, str) else ""),
            "abstract": extract_abstract(md_content if isinstance(md_content, str) else ""),
            "model_output": model_output,  # Raw model.json if debug enabled
            "extraction_config": {
                "table_merge_enabled": os.environ.get("MINERU_TABLE_MERGE_ENABLE", "true"),
                "min_table_rows": MIN_TABLE_ROWS,
                "backend": "pipeline",  # Document which backend was used
            },
        }
        
    except Exception as e:
        import traceback
        error_msg = f"{e}\n{traceback.format_exc()}"
        print(f"  MinerU failed: {error_msg}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Text Extraction Helpers
# ============================================================================

def extract_title(content: str) -> Optional[str]:
    """Extract title from first lines of content."""
    if not content:
        return None
    
    lines = content.strip().split("\n")
    
    # Strategy 1: Look for markdown header
    for line in lines[:10]:
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            if 10 < len(title) < 300:
                return title
    
    # Strategy 2: First substantive line that looks like a title
    skip_patterns = [
        r'^abstract', r'^introduction', r'^copyright', r'^©',
        r'^doi:', r'^https?://', r'^table of contents', r'^contents',
        r'^\d+\.', r'^vol\.?\s*\d', r'^issue\s*\d',
    ]
    
    for line in lines[:15]:
        line = line.strip().strip("#").strip()
        if not line or len(line) < 10 or len(line) > 300:
            continue
        
        line_lower = line.lower()
        if any(re.match(p, line_lower) for p in skip_patterns):
            continue
        
        return line
    
    return None


def extract_authors_from_text(content: str) -> List[str]:
    """Extract author names from content using patterns."""
    if not content:
        return []
    
    authors = []
    lines = content.split("\n")[:30]
    
    author_patterns = [
        r'^(?:by|authors?|written by)[:\s]+(.+)',
        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)*)',
    ]
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        
        if any(skip in line.lower() for skip in ['abstract', 'introduction', 'university', 'department', '@']):
            continue
        
        for pattern in author_patterns[:1]:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                author_str = match.group(1)
                parts = re.split(r',\s*|\s+and\s+', author_str)
                for part in parts:
                    part = part.strip()
                    if 3 < len(part) < 50:
                        authors.append(part)
                if authors:
                    return authors
    
    return authors


def extract_year_from_text(content: str) -> Optional[int]:
    """Extract publication year from content using patterns."""
    if not content:
        return None
    
    lines = content.split("\n")[:50]
    text = " ".join(lines)
    
    year_patterns = [
        r'(?:published|publication date|date)[:\s]+(?:\w+\s+)?(\d{4})',
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
        r'©\s*(\d{4})',
        r'copyright\s+(\d{4})',
        r'working paper[^,]*,?\s*(\d{4})',
        r'\((\d{4})\)',
        r'\b(20[0-2]\d|19[89]\d)\b',
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            year = int(match.group(1))
            if 1980 <= year <= 2030:
                return year
    
    return None


def extract_abstract(content: str) -> Optional[str]:
    """Extract abstract if present."""
    if not content:
        return None
        
    content_lower = content.lower()
    if "abstract" in content_lower[:2000]:
        start = content_lower.find("abstract")
        end = min(start + 3000, len(content))
        for marker in ["\n#", "\n1.", "\nintroduction", "\n1 introduction"]:
            pos = content_lower.find(marker, start + 50)
            if pos > start:
                end = min(end, pos)
        return content[start:end].strip()
    return None


# ============================================================================
# Post-Processing
# ============================================================================

def post_process_content(
    content: str,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    pdf_name: Optional[str] = None,
) -> str:
    """
    Clean and enhance MinerU markdown output for better RAG retrieval.
    
    Improvements:
    1. Remove noisy reference sections that pollute retrieval
    2. Clean OCR artifacts and formatting issues
    3. Add document header with metadata for better context
    4. Normalize whitespace and structure
    """
    if not content:
        return ""
    
    # 1. Remove reference sections (usually at the end, very long, low value for RAG)
    ref_patterns = [
        r'\n#{1,3}\s*References?\s*\n.*',
        r'\n#{1,3}\s*Bibliography\s*\n.*',
        r'\n#{1,3}\s*Works Cited\s*\n.*',
        r'\nReferences\s*\n(?:\[\d+\].*\n?)+',
    ]
    
    for pattern in ref_patterns:
        content = re.sub(pattern, '\n\n[References section removed for RAG]\n', content, flags=re.IGNORECASE | re.DOTALL)
    
    # 2. Clean OCR artifacts
    content = re.sub(r'[^\S\n]+', ' ', content)  # Normalize spaces
    content = re.sub(r'\n{4,}', '\n\n\n', content)  # Max 3 newlines
    content = re.sub(r'(\w)-\n(\w)', r'\1\2', content)  # Fix hyphenation
    
    # 3. Add document header for better retrieval context
    header_parts = []
    if title:
        header_parts.append(f"# {title}")
    if authors:
        if isinstance(authors, list):
            header_parts.append(f"**Authors:** {', '.join(authors)}")
        else:
            header_parts.append(f"**Authors:** {authors}")
    if year:
        header_parts.append(f"**Year:** {year}")
    if pdf_name:
        header_parts.append(f"**Source:** {pdf_name}")
    
    if header_parts:
        header = "\n".join(header_parts) + "\n\n---\n\n"
        # Only add header if content doesn't already start with title
        if not content.strip().startswith("# "):
            content = header + content
    
    return content.strip()
