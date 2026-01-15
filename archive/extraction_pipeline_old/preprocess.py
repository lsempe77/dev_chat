"""
AutoPK-Style Table Preprocessor

Implements the preprocessing steps from AutoPK (arXiv:2510.00039):
1. Expand merged header cells (colspan/rowspan)
2. Fill empty header cells with adjacent content
3. Combine multi-row headers using '^' symbol
4. Convert table to CSV text format
5. Include table caption and footnotes
"""

import re
from html.parser import HTMLParser
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TableCell:
    """Represents a cell in a table."""
    content: str
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False


@dataclass
class ParsedTable:
    """Represents a fully parsed table."""
    caption: str
    footnotes: List[str]
    headers: List[str]  # Combined multi-row headers
    rows: List[List[str]]  # Data rows
    raw_html: str
    
    def to_csv(self) -> str:
        """Convert to CSV text format."""
        lines = []
        if self.caption:
            lines.append(f"# {self.caption.strip()}")
        
        # Headers
        if self.headers:
            lines.append(",".join(f'"{h}"' for h in self.headers))
        
        # Data rows
        for row in self.rows:
            lines.append(",".join(f'"{c}"' for c in row))
        
        # Footnotes
        if self.footnotes:
            lines.append("")
            for fn in self.footnotes:
                lines.append(f"# Note: {fn.strip()}")
        
        return "\n".join(lines)
    
    def to_markdown(self) -> str:
        """Convert to Markdown table format."""
        lines = []
        if self.caption:
            lines.append(f"**{self.caption.strip()}**\n")
        
        # Determine column count
        num_cols = len(self.headers) if self.headers else (len(self.rows[0]) if self.rows else 0)
        if num_cols == 0:
            return ""
        
        # Headers
        if self.headers:
            # Normalize headers to column count
            headers = self.headers[:num_cols]
            while len(headers) < num_cols:
                headers.append("")
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * num_cols) + " |")
        
        # Data rows
        for row in self.rows:
            # Normalize row to column count
            cells = row[:num_cols]
            while len(cells) < num_cols:
                cells.append("")
            lines.append("| " + " | ".join(cells) + " |")
        
        # Footnotes
        if self.footnotes:
            lines.append("")
            for fn in self.footnotes[:3]:  # Limit to first 3 footnotes
                clean_fn = fn.replace("\n", " ").strip()[:200]
                lines.append(f"*{clean_fn}*")
        
        return "\n".join(lines)


class AdvancedHTMLTableParser(HTMLParser):
    """
    Advanced HTML table parser that handles:
    - rowspan and colspan
    - Nested tables (extracts outermost)
    - Missing <th> tags (treats first row as header)
    """
    
    def __init__(self):
        super().__init__()
        self.tables: List[List[List[TableCell]]] = []
        self.current_table: List[List[TableCell]] = []
        self.current_row: List[TableCell] = []
        self.current_cell: Optional[TableCell] = None
        self.in_table = 0  # Nesting level
        self.in_row = False
        self.in_cell = False
        self.cell_content = ""
        self.current_rowspan = 1
        self.current_colspan = 1
        self.is_header_cell = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'table':
            self.in_table += 1
            if self.in_table == 1:  # Only track outermost table
                self.current_table = []
                
        elif tag == 'tr' and self.in_table == 1:
            self.in_row = True
            self.current_row = []
            
        elif tag in ('td', 'th') and self.in_row and self.in_table == 1:
            self.in_cell = True
            self.cell_content = ""
            self.current_rowspan = int(attrs_dict.get('rowspan', 1))
            self.current_colspan = int(attrs_dict.get('colspan', 1))
            self.is_header_cell = (tag == 'th')
    
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.in_cell and self.in_table == 1:
            cell = TableCell(
                content=self.cell_content.strip(),
                rowspan=self.current_rowspan,
                colspan=self.current_colspan,
                is_header=self.is_header_cell
            )
            self.current_row.append(cell)
            self.in_cell = False
            self.cell_content = ""
            
        elif tag == 'tr' and self.in_row and self.in_table == 1:
            if self.current_row:  # Only add non-empty rows
                self.current_table.append(self.current_row)
            self.current_row = []
            self.in_row = False
            
        elif tag == 'table':
            if self.in_table == 1 and self.current_table:
                self.tables.append(self.current_table)
            self.in_table = max(0, self.in_table - 1)
    
    def handle_data(self, data):
        if self.in_cell:
            # Clean whitespace but preserve meaningful content
            cleaned = ' '.join(data.split())
            if cleaned:
                if self.cell_content:
                    self.cell_content += " " + cleaned
                else:
                    self.cell_content = cleaned


def expand_merged_cells(table: List[List[TableCell]]) -> List[List[str]]:
    """
    Expand cells with rowspan/colspan into a regular grid.
    This is key to AutoPK's preprocessing step.
    """
    if not table:
        return []
    
    # Calculate grid dimensions
    num_rows = len(table)
    num_cols = 0
    for row in table:
        col_count = sum(cell.colspan for cell in row)
        num_cols = max(num_cols, col_count)
    
    # Create grid filled with None
    grid: List[List[Optional[str]]] = [[None] * num_cols for _ in range(num_rows)]
    
    # Fill in cells respecting rowspan/colspan
    for row_idx, row in enumerate(table):
        col_idx = 0
        for cell in row:
            # Find next available column
            while col_idx < num_cols and grid[row_idx][col_idx] is not None:
                col_idx += 1
            
            if col_idx >= num_cols:
                break
            
            # Fill in cell content for all spanned positions
            for r_offset in range(cell.rowspan):
                for c_offset in range(cell.colspan):
                    target_row = row_idx + r_offset
                    target_col = col_idx + c_offset
                    if target_row < num_rows and target_col < num_cols:
                        if grid[target_row][target_col] is None:
                            # For expanded cells, use ^ notation as per AutoPK
                            if r_offset > 0 or c_offset > 0:
                                grid[target_row][target_col] = f"^{cell.content}"
                            else:
                                grid[target_row][target_col] = cell.content
            
            col_idx += cell.colspan
    
    # Replace None with empty string
    result = []
    for row in grid:
        result.append([cell if cell is not None else "" for cell in row])
    
    return result


def combine_multi_row_headers(rows: List[List[str]], num_header_rows: int = 1) -> Tuple[List[str], List[List[str]]]:
    """
    Combine multiple header rows into single headers using '^' notation.
    Returns (combined_headers, data_rows).
    """
    if not rows:
        return [], []
    
    if num_header_rows <= 0:
        num_header_rows = 1
    
    num_header_rows = min(num_header_rows, len(rows))
    header_rows = rows[:num_header_rows]
    data_rows = rows[num_header_rows:]
    
    # Combine headers
    num_cols = max(len(row) for row in rows) if rows else 0
    combined_headers = []
    
    for col_idx in range(num_cols):
        parts = []
        for row in header_rows:
            if col_idx < len(row):
                cell = row[col_idx]
                # Skip if it's just a reference to previous row
                if cell and not cell.startswith('^'):
                    parts.append(cell)
        
        if parts:
            combined_headers.append(' ^ '.join(parts))
        else:
            combined_headers.append("")
    
    return combined_headers, data_rows


def detect_header_rows(rows: List[List[str]]) -> int:
    """
    Heuristically detect how many rows are headers.
    Headers typically contain text while data rows have numbers.
    """
    if not rows or len(rows) < 2:
        return 1
    
    def row_has_numbers(row: List[str]) -> bool:
        """Check if row contains numeric data."""
        num_count = 0
        for cell in row:
            # Look for patterns like: 0.15, (0.05), -1.23, 1,234
            if re.search(r'[\d]+\.[\d]+|[\d]+,[\d]+|\([\d.]+\)', cell):
                num_count += 1
        return num_count >= len(row) * 0.3  # 30% threshold
    
    # Find first row with significant numeric content
    for i, row in enumerate(rows):
        if row_has_numbers(row) and i > 0:
            return i
    
    return 1  # Default to 1 header row


def parse_table(
    html: str,
    caption: str = "",
    footnotes: List[str] = None
) -> Optional[ParsedTable]:
    """
    Parse HTML table with AutoPK-style preprocessing.
    
    Steps:
    1. Parse HTML preserving rowspan/colspan
    2. Expand merged cells into grid
    3. Detect and combine multi-row headers
    4. Return structured ParsedTable
    """
    if footnotes is None:
        footnotes = []
    
    # Parse HTML
    parser = AdvancedHTMLTableParser()
    try:
        parser.feed(html)
    except Exception as e:
        print(f"    Error parsing HTML: {e}")
        return None
    
    if not parser.tables:
        return None
    
    # Use first (outermost) table
    raw_table = parser.tables[0]
    
    # Expand merged cells
    expanded_rows = expand_merged_cells(raw_table)
    
    if not expanded_rows:
        return None
    
    # Detect number of header rows
    num_header_rows = detect_header_rows(expanded_rows)
    
    # Combine multi-row headers
    headers, data_rows = combine_multi_row_headers(expanded_rows, num_header_rows)
    
    return ParsedTable(
        caption=caption,
        footnotes=footnotes,
        headers=headers,
        rows=data_rows,
        raw_html=html
    )


def preprocess_mineru_table(table_data: dict) -> Optional[ParsedTable]:
    """
    Preprocess a table from MineRU output.
    
    MineRU format:
    {
        "type": "table",
        "table_body": "<table>...</table>",
        "table_caption": ["Caption text"],
        "table_footnote": ["Footnote text"],
        ...
    }
    """
    # Extract HTML
    if isinstance(table_data, dict):
        html = (
            table_data.get("table_body") or
            table_data.get("html") or
            table_data.get("content") or
            ""
        )
        caption = ""
        if table_data.get("table_caption"):
            caption = " ".join(table_data["table_caption"])
        
        footnotes = table_data.get("table_footnote", [])
        if isinstance(footnotes, str):
            footnotes = [footnotes]
    elif isinstance(table_data, str):
        html = table_data
        caption = ""
        footnotes = []
    else:
        return None
    
    if not html:
        return None
    
    return parse_table(html, caption, footnotes)


def preprocess_all_tables(tables: List) -> List[ParsedTable]:
    """Preprocess all tables from MineRU output."""
    parsed = []
    for i, table in enumerate(tables):
        result = preprocess_mineru_table(table)
        if result:
            parsed.append(result)
    return parsed


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test with sample HTML that has merged cells
    test_html = """
    <table>
        <tr>
            <td rowspan="2">Variable name</td>
            <td rowspan="2">Description</td>
            <td colspan="2">2002</td>
            <td colspan="2">2005</td>
        </tr>
        <tr>
            <td>Treated</td>
            <td>Control</td>
            <td>Treated</td>
            <td>Control</td>
        </tr>
        <tr>
            <td>cowbull_a</td>
            <td>Number of cow/bulls</td>
            <td>0.035***</td>
            <td>0.189</td>
            <td>1.599***</td>
            <td>0.223</td>
        </tr>
        <tr>
            <td>goatsheep_a</td>
            <td>Number of goats/sheep</td>
            <td>0.098**</td>
            <td>0.131</td>
            <td>0.513***</td>
            <td>0.158</td>
        </tr>
    </table>
    """
    
    result = parse_table(
        test_html, 
        caption="Table 1: Summary statistics",
        footnotes=["*, **, *** reflect significance at 1, 5, 10% level"]
    )
    
    if result:
        print("=" * 60)
        print("PARSED TABLE")
        print("=" * 60)
        print(f"Caption: {result.caption}")
        print(f"Headers: {result.headers}")
        print(f"Data rows: {len(result.rows)}")
        for i, row in enumerate(result.rows):
            print(f"  Row {i}: {row}")
        print(f"Footnotes: {result.footnotes}")
        
        print("\n" + "=" * 60)
        print("MARKDOWN OUTPUT")
        print("=" * 60)
        print(result.to_markdown())
        
        print("\n" + "=" * 60)
        print("CSV OUTPUT")
        print("=" * 60)
        print(result.to_csv())
