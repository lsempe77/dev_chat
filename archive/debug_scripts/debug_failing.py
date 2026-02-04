"""Debug a failing study to understand table structure."""
from extraction_pipeline.pipeline import load_mineru_json, classify_table
from bs4 import BeautifulSoup

# Check multiple failing studies
failing_studies = ['121378379', '121475071', '121336027', '121294873']

for study_id in failing_studies:
    doc = load_mineru_json(study_id)
    if not doc:
        print(f"Failed to load {study_id}")
        continue
        
    tables = doc.get('tables', [])
    print(f"\n{'='*60}")
    print(f"Study {study_id}: {len(tables)} tables")
    print(f"Title: {doc.get('title', '')[:50]}...")
    
    # Find tables with coefficient patterns
    for i, t in enumerate(tables[:15]):
        caption_raw = ' '.join(t.get('table_caption', []))
        html = t.get('table_body', '')
        
        soup = BeautifulSoup(html, 'html.parser')
        rows = soup.find_all('tr')
        
        has_coef = '***' in html or '**' in html or '(0.' in html
        
        if has_coef:
            print(f"\n  Table {i}: {caption_raw[:50]}")
            
            if rows:
                # Header row
                header = rows[0].find_all('td')
                headers = [c.get_text(strip=True)[:20] for c in header[:5]]
                print(f"    Headers: {headers}")
                
                # Row labels (first column of each row)
                labels = []
                for row in rows[1:8]:
                    cells = row.find_all('td')
                    if cells:
                        labels.append(cells[0].get_text(strip=True)[:25])
                print(f"    Row labels: {labels}")
