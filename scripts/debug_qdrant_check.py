"""Debug why check_qdrant_indexed is returning False for indexed documents."""
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import os
from dotenv import load_dotenv
load_dotenv()

c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])

# Known indexed document
pdf_name_no_ext = '033d4e4c_121058373'
pdf_name_with_ext = '033d4e4c_121058373.pdf'

print("="*60)
print("TESTING QDRANT pdf_name FILTERING")
print("="*60)

# Test 1: WITHOUT .pdf extension  
try:
    r = c.count(
        'devchat_v2',
        count_filter=Filter(must=[FieldCondition(key='pdf_name', match=MatchValue(value=pdf_name_no_ext))])
    )
    print(f"Filter pdf_name='{pdf_name_no_ext}': count={r.count}")
except Exception as e:
    print(f"Filter failed: {e}")

# Test 2: WITH .pdf extension
try:
    r = c.count(
        'devchat_v2',
        count_filter=Filter(must=[FieldCondition(key='pdf_name', match=MatchValue(value=pdf_name_with_ext))])
    )
    print(f"Filter pdf_name='{pdf_name_with_ext}': count={r.count}")
except Exception as e:
    print(f"Filter failed: {e}")

# Test 3: What is actually stored?
print("\nActual stored pdf_name values (sample):")
pts, _ = c.scroll('devchat_v2', limit=5, with_payload=['pdf_name'])
for p in pts:
    print(f"  '{p.payload.get('pdf_name')}'")

# Test 4: Check orchestrate's logic
print("\n" + "="*60)
print("SIMULATING ORCHESTRATE'S check_qdrant_indexed()")
print("="*60)

# In orchestrate, pdf_name = Path(pdf_key).stem (no .pdf)
# But what does check_qdrant_indexed receive?
from pathlib import Path
sample_pdf_key = "input-pdfs/033d4e4c_121058373.pdf"
pdf_name_as_sent = Path(sample_pdf_key).stem
print(f"pdf_key: '{sample_pdf_key}'")
print(f"Path(pdf_key).stem: '{pdf_name_as_sent}'")

# The check searches for pdf_name WITHOUT .pdf
# But Qdrant stores WITH .pdf
print(f"\nBUG: orchestrate searches for '{pdf_name_as_sent}'")
print(f"     but Qdrant stores '{pdf_name_as_sent}.pdf'")
print(f"     MISMATCH = Document appears not indexed = RE-PROCESSED!")
