"""Debug table extraction."""
from extraction_pipeline.pipeline import load_mineru_json, classify_table, extract_results_table
from bs4 import BeautifulSoup
import json

# Load the document
study_id = '121336027'
doc = load_mineru_json(study_id)
tables = doc.get('tables', [])
print(f"Found {len(tables)} tables")
print(f"Content length: {len(doc.get('content', ''))}")

# Look at ALL tables
print("\n" + "="*70)
for i, t in enumerate(tables):
    caption_raw = ' '.join(t.get('table_caption', []))
    html = t.get('table_body', '')
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    # Get row labels
    row_labels = []
    for row in rows[:8]:
        cells = row.find_all('td')
        if cells:
            row_labels.append(cells[0].get_text(strip=True)[:50])
    
    print(f"\n--- Table {i+1} ---")
    print(f"Caption: {caption_raw[:80]}")
    print(f"Row count: {len(rows)}")
    print(f"Row labels: {row_labels}")
    print(f"Has coefficients: {'***' in html or '**' in html or '(0.' in html}")
    print(f"HTML snippet: {html[:300]}...")
