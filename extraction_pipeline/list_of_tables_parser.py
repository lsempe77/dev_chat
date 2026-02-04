"""
List of Tables Parser for MinerU Post-Processing

Extracts the "List of Tables" section from academic papers and uses it to:
1. Validate detected tables against expected tables
2. Repair corrupted or missing captions
3. Identify artifacts (figures misclassified as tables)
4. Detect missing tables that weren't extracted

Author: DevChat Team
Date: Feb 2, 2026
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TableEntry:
    """A single entry from the List of Tables."""
    table_num: int
    caption: str
    page: int
    
    def full_caption(self) -> str:
        return f"Table {self.table_num}: {self.caption}"


@dataclass 
class ListOfTablesResult:
    """Results from parsing the List of Tables section."""
    entries: list[TableEntry] = field(default_factory=list)
    found_section: bool = False
    section_text: str = ""
    
    @property
    def expected_table_count(self) -> int:
        return len(self.entries)
    
    def get_entry_by_page(self, page: int) -> Optional[TableEntry]:
        """Get table entry for a specific page."""
        for entry in self.entries:
            if entry.page == page:
                return entry
        return None
    
    def get_entry_by_number(self, table_num: int) -> Optional[TableEntry]:
        """Get table entry by table number."""
        for entry in self.entries:
            if entry.table_num == table_num:
                return entry
        return None


@dataclass
class TableMatchResult:
    """Results from matching detected tables to List of Tables."""
    matched: list[tuple[int, TableEntry]] = field(default_factory=list)  # (detected_idx, lot_entry)
    unmatched_detected: list[int] = field(default_factory=list)  # Indices of likely artifacts
    missing_tables: list[TableEntry] = field(default_factory=list)  # Tables not detected
    caption_repairs: list[dict] = field(default_factory=list)  # Caption repair suggestions


def parse_list_of_tables(md_content: str) -> ListOfTablesResult:
    """
    Extract List of Tables from markdown content.
    
    Handles various formats:
    - "List of Tables" / "LIST OF TABLES"
    - "Tables" section in front matter
    - Table entries like "Table 14: Household income...35"
    
    Args:
        md_content: Full markdown content of the document
        
    Returns:
        ListOfTablesResult with parsed entries
    """
    result = ListOfTablesResult()
    
    # Try multiple patterns for finding the List of Tables section
    lot_patterns = [
        # Standard "List of Tables" section (capture until List of Figures or similar)
        r'(List of Tables|LIST OF TABLES|List of tables)\s*\n(.*?)(?=List of Figures|LIST OF FIGURES|List of figures|APPENDIX|Appendix|\n# |\n## |\Z)',
        # Just "Tables" heading
        r'(?:^|\n)(Tables)\s*\n(.*?)(?=Figures|FIGURES|# |## |\n\n\n)',
    ]
    
    lot_text = None
    for pattern in lot_patterns:
        match = re.search(pattern, md_content[:20000], re.IGNORECASE | re.DOTALL)
        if match:
            lot_text = match.group(2) if len(match.groups()) > 1 else match.group(1)
            result.found_section = True
            result.section_text = lot_text[:3000]  # Store first 3000 chars for debugging
            break
    
    if not lot_text:
        return result
    
    # Parse entries line by line for better accuracy
    lines = lot_text.split('\n')
    
    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue
            
        # Look for "Table N:" pattern at start of line
        # Handles: "Table 1: Treatment and control group assignment, by barangay......... .......16"
        table_match = re.match(r'Table\s+(\d+)[:\.]?\s*(.+)', line, re.IGNORECASE)
        
        if table_match:
            table_num = int(table_match.group(1))
            rest = table_match.group(2)
            
            # Extract page number from end - it's usually after dots/spaces
            # The format has dots, spaces, and sometimes special chars before page number
            # Clean up the line: remove dots, bullets, special chars from the end
            cleaned = re.sub(r'[\.•·\s]+$', '', rest)  # Remove trailing dots/bullets
            
            # Now find the page number at the end
            page_match = re.search(r'(\d+)\s*$', cleaned)
            
            if page_match:
                page = int(page_match.group(1))
                # Caption is everything before the page number, cleaned up
                caption_part = cleaned[:page_match.start()]
                # Remove trailing dots, spaces, special chars from caption
                caption = re.sub(r'[\.•·…\s\-]+$', '', caption_part).strip()
                # Also remove common OCR artifacts
                caption = re.sub(r'[\$\=]+', '', caption).strip()
                
                # Validate: page should be reasonable (1-200)
                if 1 <= page <= 200 and len(caption) > 3:
                    # Avoid duplicates
                    if not any(e.table_num == table_num for e in result.entries):
                        entry = TableEntry(table_num=table_num, caption=caption, page=page)
                        result.entries.append(entry)
    
    # Sort by table number
    result.entries.sort(key=lambda e: e.table_num)
    
    return result


def match_tables_to_list(
    detected_tables: list[dict],
    lot: ListOfTablesResult,
    page_tolerance: int = 1
) -> TableMatchResult:
    """
    Match detected tables to List of Tables entries.
    
    Args:
        detected_tables: List of table dicts from MinerU
        lot: Parsed List of Tables
        page_tolerance: Allow page mismatch of +/- this many pages
        
    Returns:
        TableMatchResult with matching analysis
    """
    result = TableMatchResult()
    
    if not lot.found_section or not lot.entries:
        # No List of Tables - mark all as unmatched
        result.unmatched_detected = list(range(len(detected_tables)))
        return result
    
    # Build page index for LOT entries
    lot_by_page: dict[int, TableEntry] = {}
    for entry in lot.entries:
        for p in range(entry.page - page_tolerance, entry.page + page_tolerance + 1):
            if p not in lot_by_page:  # First match wins
                lot_by_page[p] = entry
    
    matched_lot_nums = set()
    
    for i, table in enumerate(detected_tables):
        # Get page (0-indexed in MinerU, convert to 1-indexed)
        page_idx = table.get("page_idx", -1)
        page = page_idx + 1 if isinstance(page_idx, int) else -1
        
        # Get current caption
        caption_list = table.get("table_caption", [])
        current_caption = caption_list[0] if caption_list else ""
        
        # Try to match by page
        lot_entry = lot_by_page.get(page)
        
        if lot_entry:
            result.matched.append((i, lot_entry))
            matched_lot_nums.add(lot_entry.table_num)
            
            # Check if caption needs repair
            expected_start = f"Table {lot_entry.table_num}"
            if current_caption and not current_caption.startswith("Table"):
                result.caption_repairs.append({
                    "detected_idx": i,
                    "page": page,
                    "current_caption": current_caption[:100],
                    "expected_caption": lot_entry.full_caption(),
                    "reason": "caption_doesnt_start_with_table"
                })
            elif not current_caption:
                result.caption_repairs.append({
                    "detected_idx": i, 
                    "page": page,
                    "current_caption": "[No caption]",
                    "expected_caption": lot_entry.full_caption(),
                    "reason": "missing_caption"
                })
        else:
            # Check if this looks like a figure or artifact
            if re.search(r'\b(figure|fig\.?)\s*\d', current_caption, re.IGNORECASE):
                result.unmatched_detected.append(i)
            elif not current_caption:
                result.unmatched_detected.append(i)
            else:
                # Has caption but not in LOT - might be appendix table
                result.unmatched_detected.append(i)
    
    # Find missing tables
    for entry in lot.entries:
        if entry.table_num not in matched_lot_nums:
            result.missing_tables.append(entry)
    
    return result


def repair_table_captions(
    tables: list[dict],
    match_result: TableMatchResult
) -> list[dict]:
    """
    Apply caption repairs to tables.
    
    Args:
        tables: Original table list
        match_result: Results from match_tables_to_list
        
    Returns:
        Tables with repaired captions (mutates original)
    """
    # Build repair map
    repairs_by_idx = {r["detected_idx"]: r for r in match_result.caption_repairs}
    
    for i, table in enumerate(tables):
        if i in repairs_by_idx:
            repair = repairs_by_idx[i]
            original_caption = (table.get("table_caption", []) or [""])[0]
            
            # Store original and apply repair
            table["_original_caption"] = original_caption
            table["_caption_repaired"] = True
            table["_repair_reason"] = repair["reason"]
            table["table_caption"] = [repair["expected_caption"]]
    
    return tables


def analyze_tables_with_lot(
    tables: list[dict],
    md_content: str,
    verbose: bool = True
) -> dict:
    """
    Complete analysis pipeline using List of Tables.
    
    Args:
        tables: Detected tables from MinerU
        md_content: Full markdown content
        verbose: Print analysis summary
        
    Returns:
        {
            "lot": ListOfTablesResult,
            "match_result": TableMatchResult,
            "repaired_tables": list[dict],
            "artifacts": list[int],  # Indices of likely artifacts
            "summary": str,
        }
    """
    # Parse List of Tables
    lot = parse_list_of_tables(md_content)
    
    if verbose:
        print(f"\n{'='*60}")
        print("LIST OF TABLES ANALYSIS")
        print(f"{'='*60}")
        print(f"Found section: {lot.found_section}")
        print(f"Expected tables: {lot.expected_table_count}")
        if lot.entries:
            print(f"Table range: {lot.entries[0].table_num} - {lot.entries[-1].table_num}")
    
    # Match detected to expected
    match_result = match_tables_to_list(tables, lot)
    
    if verbose:
        print(f"\nDetected tables: {len(tables)}")
        print(f"Matched to LOT: {len(match_result.matched)}")
        print(f"Unmatched (artifacts?): {len(match_result.unmatched_detected)}")
        print(f"Missing tables: {len(match_result.missing_tables)}")
        print(f"Captions to repair: {len(match_result.caption_repairs)}")
    
    # Apply repairs
    repaired = repair_table_captions(tables, match_result)
    
    # Build summary
    summary_lines = [
        f"List of Tables found: {lot.found_section}",
        f"Expected: {lot.expected_table_count} tables",
        f"Detected: {len(tables)} tables", 
        f"Matched: {len(match_result.matched)}",
        f"Artifacts: {len(match_result.unmatched_detected)}",
        f"Missing: {len(match_result.missing_tables)}",
        f"Captions repaired: {len(match_result.caption_repairs)}",
    ]
    
    if match_result.missing_tables and verbose:
        print(f"\nMissing tables:")
        for entry in match_result.missing_tables[:10]:
            print(f"  - Table {entry.table_num}: {entry.caption[:50]}... (page {entry.page})")
    
    if match_result.caption_repairs and verbose:
        print(f"\nCaption repairs:")
        for repair in match_result.caption_repairs[:5]:
            print(f"  - Page {repair['page']}: '{repair['current_caption'][:40]}...'")
            print(f"    → '{repair['expected_caption'][:60]}'")
    
    return {
        "lot": lot,
        "match_result": match_result,
        "repaired_tables": repaired,
        "artifacts": match_result.unmatched_detected,
        "summary": "\n".join(summary_lines),
    }


if __name__ == "__main__":
    # Test with 122182713
    from dotenv import load_dotenv
    load_dotenv()
    import boto3
    import json
    import os
    
    account_id = os.environ.get('R2_ACCOUNT_ID')
    endpoint_url = f'https://{account_id}.r2.cloudflarestorage.com'
    
    s3 = boto3.client('s3',
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto'
    )
    
    # Get JSON and MD
    obj_json = s3.get_object(
        Bucket='devchat-pdfs',
        Key='rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/0cb609fbf433_PDFs_of_included_programs_122182713.json'
    )
    data = json.loads(obj_json['Body'].read())
    tables = data.get('tables', [])
    
    obj_md = s3.get_object(
        Bucket='devchat-pdfs', 
        Key='rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/md/0cb609fbf433_PDFs_of_included_programs_122182713.md'
    )
    md_content = obj_md['Body'].read().decode('utf-8')
    
    # Run analysis
    result = analyze_tables_with_lot(tables, md_content, verbose=True)
    
    print(f"\n{'='*60}")
    print("REPAIRED TABLES")
    print(f"{'='*60}")
    for i, t in enumerate(result["repaired_tables"]):
        if t.get("_caption_repaired"):
            caption = t.get("table_caption", [""])[0]
            original = t.get("_original_caption", "")
            print(f"\n{i+1}. REPAIRED:")
            print(f"   Original: {original[:60]}")
            print(f"   Fixed:    {caption[:60]}")
