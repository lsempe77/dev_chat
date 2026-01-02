"""
Smart MinerU Post-Processing Module

Cleans and enhances MinerU markdown output for better RAG retrieval and grounding.

Features:
- Section detection & normalization
- Reference section removal (reduces citation noise)
- OCR artifact cleanup
- Sentence boundary repair
- Table validation

This module is called after MinerU extraction and before chunking.
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from src.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class DocumentSection:
    """Represents a detected section in the document."""
    type: str  # abstract, introduction, methods, results, discussion, references
    title: str
    content: str
    start_line: int
    end_line: int
    confidence: float = 0.8


# ============================================================================
# Section Detection Patterns
# ============================================================================

SECTION_PATTERNS = {
    "abstract": r"(?i)^#{1,3}\s*abstract\s*$|^abstract\s*$",
    "introduction": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:introduction|background)\s*$",
    "literature": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:literature\s+review|related\s+work|previous\s+research)\s*$",
    "methods": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:method(?:ology|s)?|research\s+design|data(?:\s+and\s+methods)?|sample|approach)\s*$",
    "results": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:results?|findings|empirical\s+results?)\s*$",
    "discussion": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:discussion|analysis)\s*$",
    "conclusion": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:conclusions?|implications|summary)\s*$",
    "references": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:references?|bibliography|works\s+cited|literature\s+cited)\s*$",
    "appendix": r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:appendi(?:x|ces)|supplementary|supporting\s+information)\s*$",
    "acknowledgments": r"(?i)^#{1,3}\s*(?:acknowledgment|acknowledgement)s?\s*$",
}


# ============================================================================
# Section Detection
# ============================================================================

def detect_sections(markdown: str) -> List[DocumentSection]:
    """
    Detect academic paper sections in markdown content.
    
    Args:
        markdown: The full markdown document
        
    Returns:
        List of DocumentSection objects with type, title, content, and positions
    """
    sections = []
    lines = markdown.split("\n")
    
    current_section = None
    current_title = ""
    current_content = []
    current_start = 0
    
    for i, line in enumerate(lines):
        matched_type = None
        
        # Check if line matches a section header
        for section_type, pattern in SECTION_PATTERNS.items():
            if re.match(pattern, line.strip()):
                matched_type = section_type
                break
        
        if matched_type:
            # Save previous section
            if current_section is not None:
                sections.append(DocumentSection(
                    type=current_section,
                    title=current_title,
                    content="\n".join(current_content),
                    start_line=current_start,
                    end_line=i - 1,
                    confidence=0.8
                ))
            
            current_section = matched_type
            current_title = line.strip()
            current_content = []
            current_start = i
        else:
            current_content.append(line)
    
    # Don't forget last section
    if current_section is not None:
        sections.append(DocumentSection(
            type=current_section,
            title=current_title,
            content="\n".join(current_content),
            start_line=current_start,
            end_line=len(lines) - 1,
            confidence=0.8
        ))
    
    logger.debug(f"Detected {len(sections)} sections: {[s.type for s in sections]}")
    return sections


# ============================================================================
# Reference Section Removal
# ============================================================================

def remove_references_section(markdown: str) -> str:
    """
    Remove the references/bibliography section to prevent citation noise in retrieval.
    
    References often match queries (they contain titles and keywords) but don't
    contain useful content for answering questions.
    
    Args:
        markdown: The full markdown document
        
    Returns:
        Markdown with references section removed
    """
    # Pattern to match reference section headers
    ref_pattern = r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:references?|bibliography|works\s+cited|literature\s+cited)\s*$"
    
    lines = markdown.split("\n")
    result_lines = []
    in_references = False
    next_section_pattern = r"^#{1,3}\s+\w"  # Any header that starts a new section
    
    for line in lines:
        if re.match(ref_pattern, line.strip()):
            in_references = True
            logger.debug(f"Found references section at: {line.strip()[:50]}")
            continue
        
        if in_references:
            # Check if we've hit another main section (appendix, acknowledgments)
            if re.match(next_section_pattern, line.strip()):
                # Check if it's NOT just a reference-related header
                if not re.match(ref_pattern, line.strip()):
                    in_references = False
                    result_lines.append(line)
            # Otherwise, skip reference content
        else:
            result_lines.append(line)
    
    removed_lines = len(lines) - len(result_lines)
    if removed_lines > 0:
        logger.info(f"Removed {removed_lines} lines from references section")
    
    return "\n".join(result_lines)


# ============================================================================
# OCR Artifact Cleanup
# ============================================================================

# Common OCR error patterns: (pattern, replacement, flags)
OCR_CLEANUP_PATTERNS = [
    # Fix common character substitutions
    (r"\bl(?=\d)", "1"),  # l -> 1 when followed by digit (e.g., "l23" -> "123")
    (r"(?<=\d)l\b", "1"),  # l -> 1 when preceded by digit
    (r"\bO(?=\d)", "0"),  # O -> 0 when followed by digit
    (r"(?<=\d)O\b", "0"),  # O -> 0 when preceded by digit
    
    # Fix hyphenation across lines (word-\nword -> wordword)
    (r"(\w+)-\s*\n\s*(\w+)", r"\1\2"),
    
    # Remove standalone page numbers
    (r"^\s*\d{1,4}\s*$", ""),  # Lines with just numbers 1-9999
    (r"^.*Page \d+ of \d+.*$", ""),  # "Page X of Y"
    (r"^-\s*\d+\s*-$", ""),  # "- 42 -" style page numbers
    
    # Fix spacing issues
    (r"  +", " "),  # Multiple spaces -> single space
    (r"\n{4,}", "\n\n\n"),  # More than 3 newlines -> 3
    
    # Fix common symbol errors from OCR
    (r"¬", "-"),  # Logical not -> hyphen
    (r"­", ""),  # Soft hyphen -> remove
    (r"ﬁ", "fi"),  # Ligature fi
    (r"ﬂ", "fl"),  # Ligature fl
    (r"ﬀ", "ff"),  # Ligature ff
    (r"ﬃ", "ffi"),  # Ligature ffi
    (r"ﬄ", "ffl"),  # Ligature ffl
    
    # Remove garbage characters common in OCR
    (r"[^\x00-\x7F\u00A0-\u024F\u0370-\u03FF\u2000-\u206F\u2070-\u209F\u20A0-\u20CF\u2100-\u214F\u2190-\u21FF\u2200-\u22FF\n\t]", ""),
]


def clean_ocr_artifacts(text: str) -> str:
    """
    Clean common OCR artifacts from MinerU output.
    
    Args:
        text: Raw text with potential OCR errors
        
    Returns:
        Cleaned text
    """
    result = text
    total_changes = 0
    
    for pattern, replacement, *flags in OCR_CLEANUP_PATTERNS:
        flag = flags[0] if flags else re.MULTILINE
        before_len = len(result)
        result = re.sub(pattern, replacement, result, flags=flag)
        changes = before_len - len(result)
        if changes != 0:
            total_changes += abs(changes)
    
    if total_changes > 0:
        logger.debug(f"OCR cleanup: {total_changes} characters modified")
    
    return result


# ============================================================================
# Sentence Boundary Repair
# ============================================================================

def repair_sentence_boundaries(text: str) -> str:
    """
    Repair sentences broken by page breaks or column switches.
    
    Looks for sentences that end mid-word or lines that start with lowercase
    (indicating they continue from the previous line).
    
    Args:
        text: Text with potentially broken sentences
        
    Returns:
        Text with repaired sentence boundaries
    """
    lines = text.split("\n")
    repaired = []
    buffer = ""
    
    for line in lines:
        stripped = line.strip()
        
        # Empty line - flush buffer and keep blank line
        if not stripped:
            if buffer:
                repaired.append(buffer)
                buffer = ""
            repaired.append("")
            continue
        
        # Skip markdown headers and formatting
        if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("-"):
            if buffer:
                repaired.append(buffer)
                buffer = ""
            repaired.append(line)
            continue
        
        # Check if we should join with previous line
        if buffer:
            # Previous line didn't end with sentence-ending punctuation
            last_char = buffer.rstrip()[-1] if buffer.rstrip() else ""
            ends_sentence = last_char in ".!?:;"
            
            # Current line starts with lowercase (continuation)
            starts_lower = stripped[0].islower() if stripped else False
            
            if not ends_sentence and starts_lower:
                # Join lines - this is a broken sentence
                buffer = buffer.rstrip() + " " + stripped
                continue
        
        # Start new buffer or add to repaired
        if buffer:
            repaired.append(buffer)
        buffer = line
    
    # Flush remaining buffer
    if buffer:
        repaired.append(buffer)
    
    return "\n".join(repaired)


# ============================================================================
# Table Handling
# ============================================================================

def is_table_malformed(table_text: str) -> bool:
    """
    Check if a markdown table appears malformed.
    
    Args:
        table_text: The markdown table text
        
    Returns:
        True if table seems broken, False if OK
    """
    lines = [l for l in table_text.strip().split("\n") if l.strip()]
    
    if len(lines) < 2:
        return True  # Tables need at least header + separator
    
    # Count columns (pipes) per line
    col_counts = [line.count("|") for line in lines]
    
    # If column counts vary wildly, table is broken
    if max(col_counts) - min(col_counts) > 2:
        return True
    
    # Check for separator row (should have dashes)
    has_separator = any("-" * 3 in line and "|" in line for line in lines[:3])
    if not has_separator:
        return True
    
    return False


def convert_table_to_text(table_text: str, caption: str = None) -> str:
    """
    Convert a markdown table to readable text for better RAG retrieval.
    
    Tables often don't retrieve well because queries don't match table syntax.
    Converting to prose helps with semantic matching.
    
    Args:
        table_text: Markdown table
        caption: Optional table caption
        
    Returns:
        Text description of the table
    """
    lines = [l.strip() for l in table_text.strip().split("\n") if l.strip()]
    
    if len(lines) < 2:
        return table_text  # Not a valid table
    
    # Extract headers
    header_line = lines[0]
    headers = [h.strip() for h in header_line.split("|") if h.strip()]
    
    # Skip separator row
    data_start = 1
    for i, line in enumerate(lines[1:], 1):
        if re.match(r"^[\|\-:\s]+$", line):
            data_start = i + 1
            break
    
    # Build text representation
    text_parts = []
    if caption:
        text_parts.append(f"**Table: {caption}**")
    
    # Describe each row
    for line in lines[data_start:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) == len(headers):
            row_desc = ", ".join(f"{headers[i]}: {cells[i]}" for i in range(len(cells)))
            text_parts.append(f"- {row_desc}")
        elif cells:  # Partial row
            text_parts.append(f"- {', '.join(cells)}")
    
    return "\n".join(text_parts)


def normalize_tables(markdown: str, convert_to_text: bool = False) -> str:
    """
    Normalize tables in markdown: either mark malformed ones or convert to text.
    
    Args:
        markdown: Full document markdown
        convert_to_text: If True, convert all tables to text descriptions
        
    Returns:
        Markdown with normalized tables
    """
    # Pattern to find markdown tables
    table_pattern = r"(\|[^\n]+\|(?:\n\|[^\n]+\|)+)"
    
    def process_table(match):
        table = match.group(1)
        
        if is_table_malformed(table):
            logger.debug(f"Marked malformed table ({len(table)} chars)")
            return f"\n<!-- MALFORMED_TABLE: Content removed for RAG quality -->\n"
        
        if convert_to_text:
            return "\n" + convert_table_to_text(table) + "\n"
        
        return table
    
    return re.sub(table_pattern, process_table, markdown)


def mark_malformed_tables(markdown: str) -> str:
    """
    Find and mark malformed tables so they're excluded from retrieval.
    
    Rather than trying to fix tables (which requires LLM), we mark them
    so they don't pollute search results.
    
    Args:
        markdown: Full document markdown
        
    Returns:
        Markdown with malformed tables marked
    """
    return normalize_tables(markdown, convert_to_text=False)


# ============================================================================
# Running Headers/Footers Removal
# ============================================================================

def remove_running_headers(markdown: str, title: str = None) -> str:
    """
    Remove running headers and footers that appear on every page.
    
    Academic PDFs often have the paper title or journal name repeated
    on every page, which clutters the extracted text.
    
    Args:
        markdown: Document markdown
        title: Document title (used to detect running headers)
        
    Returns:
        Cleaned markdown
    """
    lines = markdown.split("\n")
    cleaned_lines = []
    
    # Common running header/footer patterns
    patterns = [
        r"^\s*\d+\s*$",  # Just a page number
        r"^-\s*\d+\s*-$",  # "- 42 -" style
        r"^\s*Page\s+\d+\s*$",  # "Page 42"
        r"^\s*\d+\s+of\s+\d+\s*$",  # "42 of 100"
        r"^.*\bPREPRINT\b.*$",  # Preprint markers
        r"^.*\bDRAFT\b.*$",  # Draft markers
        r"^.*\bCONFIDENTIAL\b.*$",  # Confidential markers
        r"^\s*Downloaded from\s+.*$",  # Download notices
        r"^\s*https?://.*$",  # Bare URLs (often watermarks)
    ]
    
    # If we have a title, add pattern to match it repeated
    if title and len(title) > 20:
        # Escape special regex chars and make it fuzzy
        escaped_title = re.escape(title[:30])
        patterns.append(f"^.*{escaped_title}.*$")
    
    combined_pattern = "|".join(f"({p})" for p in patterns)
    
    for line in lines:
        # Skip lines that match running header patterns
        if re.match(combined_pattern, line.strip(), re.IGNORECASE):
            continue
        cleaned_lines.append(line)
    
    removed = len(lines) - len(cleaned_lines)
    if removed > 0:
        logger.debug(f"Removed {removed} running header/footer lines")
    
    return "\n".join(cleaned_lines)


# ============================================================================
# Figure Caption Extraction
# ============================================================================

def extract_figure_captions(markdown: str) -> Tuple[str, List[Dict]]:
    """
    Extract figure captions and consolidate them for better retrieval.
    
    Figure captions often contain key findings but get separated from
    their context during chunking.
    
    Args:
        markdown: Document markdown
        
    Returns:
        Tuple of (cleaned_markdown, list_of_figures)
    """
    figures = []
    
    # Pattern to match figure captions
    # Common formats: "Figure 1:", "Fig. 1.", "Figure 1 –", etc.
    caption_pattern = r"(?:^|\n)((?:Figure|Fig\.?)\s*\d+[.:–-]\s*[^\n]+(?:\n(?![A-Z#\|])[^\n]+)*)"
    
    def extract_and_mark(match):
        caption = match.group(1).strip()
        # Extract figure number
        fig_num_match = re.match(r"(?:Figure|Fig\.?)\s*(\d+)", caption)
        fig_num = fig_num_match.group(1) if fig_num_match else "?"
        
        figures.append({
            "number": fig_num,
            "caption": caption,
        })
        
        # Keep a shortened version in place
        return f"\n**[Figure {fig_num}]** {caption[:200]}{'...' if len(caption) > 200 else ''}\n"
    
    cleaned = re.sub(caption_pattern, extract_and_mark, markdown, flags=re.IGNORECASE)
    
    if figures:
        logger.debug(f"Extracted {len(figures)} figure captions")
    
    return cleaned, figures


# ============================================================================
# Equation/Formula Cleanup  
# ============================================================================

def clean_equations(markdown: str) -> str:
    """
    Clean up malformed equations and LaTeX fragments.
    
    MinerU sometimes produces broken LaTeX that clutters the text.
    
    Args:
        markdown: Document with equations
        
    Returns:
        Cleaned markdown
    """
    # Remove broken LaTeX that spans multiple lines incorrectly
    # Pattern: $$ followed by garbage
    markdown = re.sub(r"\$\$[^$]{500,}\$\$", "[Complex equation removed]", markdown)
    
    # Fix common LaTeX issues
    markdown = re.sub(r"\\begin\{equation\}.*?\\end\{equation\}", "[Equation]", markdown, flags=re.DOTALL)
    markdown = re.sub(r"\\begin\{align\}.*?\\end\{align\}", "[Equation]", markdown, flags=re.DOTALL)
    
    # Remove inline math that's clearly broken (very long or has newlines)
    def check_inline_math(match):
        content = match.group(1)
        if len(content) > 200 or "\n" in content:
            return "[Math expression]"
        return match.group(0)
    
    markdown = re.sub(r"\$([^$]+)\$", check_inline_math, markdown)
    
    return markdown


# ============================================================================
# Document Header Enhancement
# ============================================================================

def add_document_header(
    markdown: str,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    pdf_name: Optional[str] = None,
) -> str:
    """
    Add a structured header to the document for better context.
    
    This helps the LLM understand what document a chunk comes from.
    
    Args:
        markdown: The document content
        title: Document title
        authors: List of author names
        year: Publication year
        pdf_name: Source PDF filename
        
    Returns:
        Markdown with header prepended
    """
    header_parts = []
    
    if title:
        header_parts.append(f"# {title}")
    
    metadata_items = []
    if authors:
        # Take first 3 authors + "et al." if more
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."
        metadata_items.append(f"**Authors:** {author_str}")
    
    if year:
        metadata_items.append(f"**Year:** {year}")
    
    if pdf_name:
        metadata_items.append(f"**Source:** {pdf_name}")
    
    if metadata_items:
        header_parts.append(" | ".join(metadata_items))
    
    if header_parts:
        header_parts.append("\n---\n")
        return "\n".join(header_parts) + markdown
    
    return markdown


# ============================================================================
# Footnote & Endnote Cleanup
# ============================================================================

def clean_footnotes(markdown: str) -> str:
    """
    Clean up footnote markers and inline footnotes that clutter the text.
    
    Args:
        markdown: Document with footnotes
        
    Returns:
        Cleaned document
    """
    # Remove superscript footnote numbers [1], [2], etc. that are just references
    # But keep citation-style references like [Author, 2020]
    result = re.sub(r"\[\d{1,3}\](?!\()", "", markdown)
    
    # Remove footnote definitions at bottom (lines starting with [1]: or similar)
    result = re.sub(r"^\[\d+\]:\s*.*$", "", result, flags=re.MULTILINE)
    
    return result


# ============================================================================
# Master Post-Processing Pipeline
# ============================================================================

def post_process_mineru_output(
    raw_markdown: str,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    pdf_name: Optional[str] = None,
    remove_refs: bool = True,
    add_header: bool = True,
    convert_tables_to_text: bool = False,
    clean_equations_flag: bool = True,
    remove_headers_footers: bool = True,
) -> Tuple[str, Dict]:
    """
    Complete post-processing pipeline for MinerU output.
    
    Applies all cleaning and enhancement steps in the correct order.
    
    Args:
        raw_markdown: Raw MinerU markdown output
        title: Document title (for header)
        authors: Author list (for header)
        year: Publication year (for header)
        pdf_name: Source PDF name (for header)
        remove_refs: Whether to remove references section (default: True)
        add_header: Whether to add document header (default: True)
        convert_tables_to_text: Convert tables to prose descriptions (default: False)
        clean_equations_flag: Clean up malformed LaTeX equations (default: True)
        remove_headers_footers: Remove running headers/footers (default: True)
        
    Returns:
        Tuple of (enhanced_markdown, stats_dict)
    """
    stats = {
        "original_length": len(raw_markdown),
        "sections_detected": [],
        "references_removed": False,
        "ocr_cleaned": False,
        "sentences_repaired": False,
        "malformed_tables": 0,
        "equations_cleaned": False,
        "headers_footers_removed": False,
        "figures_extracted": 0,
    }
    
    # Step 1: Clean OCR artifacts first (operates on raw text)
    cleaned = clean_ocr_artifacts(raw_markdown)
    if len(cleaned) != len(raw_markdown):
        stats["ocr_cleaned"] = True
    
    # Step 2: Remove running headers/footers (before other processing)
    if remove_headers_footers:
        before_len = len(cleaned)
        cleaned = remove_running_headers(cleaned, title=title)
        if len(cleaned) < before_len:
            stats["headers_footers_removed"] = True
    
    # Step 3: Repair sentence boundaries
    cleaned = repair_sentence_boundaries(cleaned)
    stats["sentences_repaired"] = True
    
    # Step 4: Detect sections (for logging/metadata)
    sections = detect_sections(cleaned)
    stats["sections_detected"] = [s.type for s in sections]
    
    # Step 5: Remove references section (prevents citation noise)
    if remove_refs:
        before_len = len(cleaned)
        cleaned = remove_references_section(cleaned)
        if len(cleaned) < before_len:
            stats["references_removed"] = True
    
    # Step 6: Clean footnote clutter
    cleaned = clean_footnotes(cleaned)
    
    # Step 7: Handle tables (mark malformed or convert to text)
    before_tables = cleaned.count("<!-- MALFORMED_TABLE")
    cleaned = normalize_tables(cleaned, convert_to_text=convert_tables_to_text)
    stats["malformed_tables"] = cleaned.count("<!-- MALFORMED_TABLE") - before_tables
    
    # Step 8: Clean up equations/formulas
    if clean_equations_flag:
        before_len = len(cleaned)
        cleaned = clean_equations(cleaned)
        if len(cleaned) != before_len:
            stats["equations_cleaned"] = True
    
    # Step 9: Extract figure captions (consolidate for context)
    cleaned, figures = extract_figure_captions(cleaned)
    stats["figures_extracted"] = len(figures)
    
    # Step 10: Add document header (for context)
    if add_header and (title or authors or year):
        cleaned = add_document_header(
            cleaned,
            title=title,
            authors=authors,
            year=year,
            pdf_name=pdf_name,
        )
    
    stats["final_length"] = len(cleaned)
    stats["length_reduction"] = f"{(1 - len(cleaned) / len(raw_markdown)) * 100:.1f}%"
    
    logger.info(
        f"Post-processing complete: {stats['original_length']} -> {stats['final_length']} chars "
        f"({stats['length_reduction']} reduction), "
        f"sections={stats['sections_detected']}, "
        f"refs_removed={stats['references_removed']}"
    )
    
    return cleaned, stats


# ============================================================================
# Validation
# ============================================================================

def validate_enhancement(raw: str, enhanced: str) -> Tuple[bool, List[str]]:
    """
    Validate that enhancement didn't remove important content.
    
    Args:
        raw: Original markdown
        enhanced: Post-processed markdown
        
    Returns:
        Tuple of (is_valid, list_of_warnings)
    """
    warnings = []
    
    # Check we didn't lose too much content
    if len(enhanced) < len(raw) * 0.3:
        warnings.append(f"Enhanced content is only {len(enhanced)/len(raw)*100:.0f}% of original")
    
    # Check key sections are preserved
    raw_sections = detect_sections(raw)
    enhanced_sections = detect_sections(enhanced)
    
    important_sections = ["abstract", "methods", "results"]
    for section_type in important_sections:
        raw_has = any(s.type == section_type for s in raw_sections)
        enhanced_has = any(s.type == section_type for s in enhanced_sections)
        if raw_has and not enhanced_has:
            warnings.append(f"Lost '{section_type}' section in enhancement")
    
    is_valid = len(warnings) == 0
    return is_valid, warnings


# ============================================================================
# Convenience Function for Modal Integration
# ============================================================================

def enhance_for_rag(
    content: str,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    pdf_name: Optional[str] = None,
) -> str:
    """
    Convenience function for Modal pipeline integration.
    
    This is the main entry point for post-processing in the ingestion pipeline.
    Returns only the enhanced content (not stats) for simpler integration.
    
    Args:
        content: Raw MinerU markdown
        title, authors, year, pdf_name: Document metadata
        
    Returns:
        Enhanced markdown ready for chunking
    """
    enhanced, stats = post_process_mineru_output(
        raw_markdown=content,
        title=title,
        authors=authors,
        year=year,
        pdf_name=pdf_name,
        remove_refs=True,
        add_header=True,
    )
    
    # Validate and log any concerns
    is_valid, warnings = validate_enhancement(content, enhanced)
    if not is_valid:
        for warning in warnings:
            logger.warning(f"Enhancement warning: {warning}")
        # Fall back to raw if enhancement is too aggressive
        if len(enhanced) < len(content) * 0.3:
            logger.error("Enhancement too aggressive, using raw content")
            return content
    
    return enhanced
