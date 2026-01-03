import asyncio
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(supabase_url, supabase_key)

PROJECT_ID = "0816e8d3-ab23-417c-bf3f-e45531411c73"

async def main():
    print(f"Starting enrichment for project {PROJECT_ID}...")
    
    # Import clients (assuming they are in the python path)
    # We need to make sure src is in path
    import sys
    sys.path.append(os.getcwd())
    
    from src.ingestion.metadata.crossref_client import CrossRefClient
    from src.ingestion.metadata.openalex_client import OpenAlexClient
    
    crossref = CrossRefClient()
    openalex = OpenAlexClient()
    
    # Get all documents
    response = supabase.table("documents").select("*").eq("rag_project_id", PROJECT_ID).execute()
    documents = response.data
    
    print(f"Found {len(documents)} documents.")
    
    enriched_count = 0
    failed_count = 0
    skipped_count = 0
    
    for doc in documents:
        doc_id = doc["id"]
        current_metadata = doc.get("metadata", {}) or {}
        doi = current_metadata.get("doi")
        original_filename = doc.get("original_filename", "")
        
        # Skip if already enriched with high confidence (optional, but maybe we want to re-check everything?)
        # The user said "run the processing of all of them again", so let's NOT skip unless it's perfect.
        # But to save time, if we have a DOI and source is crossref, it's probably fine.
        # However, the user complained about hallucinations, so maybe we should re-verify everything that was "openalex" without DOI.
        
        # Let's just process everything that doesn't have a DOI or has low confidence.
        
        try:
            enriched = {**current_metadata}
            source = None
            
            # Try to extract DOI from filename if not present
            if not doi:
                doi_match = re.search(r'10\.\d{4,}/[^\s]+', original_filename.replace('_', '/'))
                if doi_match:
                    doi = doi_match.group(0)
                    print(f"Extracted DOI from filename: {doi}")
            
            if doi:
                # Try CrossRef
                work = await crossref.get_by_doi(doi)
                if work:
                    enriched.update({
                        "doi": doi,
                        "title": work.title or enriched.get("title"),
                        "authors": work.authors or enriched.get("authors", []),
                        "year": work.year or enriched.get("year"),
                        "journal": work.journal or enriched.get("journal"),
                        "publisher": work.publisher or enriched.get("publisher"),
                        "item_type": work.type or enriched.get("item_type"),
                    })
                    source = "crossref"
                
                # Also try OpenAlex for additional data
                oa_work = await openalex.get_by_doi(doi)
                if oa_work:
                    if oa_work.abstract and not enriched.get("abstract"):
                        enriched["abstract"] = oa_work.abstract
                    if oa_work.concepts:
                        enriched["keywords"] = [c["name"] for c in oa_work.concepts[:10] if c.get("name")]
                    if not source:
                        source = "openalex"
            else:
                # Search by title from filename
                search_title = original_filename.replace('.pdf', '').replace('_', ' ')
                search_title = re.sub(r'^[a-f0-9]{10,}_', '', search_title)
                
                # Fetch top 3 results
                works = await openalex.search(title=search_title, per_page=3)
                
                if works and len(works) > 0:
                    # Check similarity to avoid hallucinations
                    def similarity(a, b):
                        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
                    
                    best_match = None
                    best_score = 0.0
                    
                    for work in works:
                        if not work.title: continue
                        score = similarity(search_title, work.title)
                        if score > best_score:
                            best_score = score
                            best_match = work
                    
                    # Only accept if similarity is reasonable (> 0.8)
                    if best_match and best_score > 0.8:
                        oa_work = best_match
                        enriched.update({
                            "title": oa_work.title or enriched.get("title"),
                            "authors": oa_work.authors or enriched.get("authors", []),
                            "year": oa_work.year or enriched.get("year"),
                            "doi": oa_work.doi or enriched.get("doi"),
                        })
                        if oa_work.concepts:
                            enriched["keywords"] = [c["name"] for c in oa_work.concepts[:10] if c.get("name")]
                        source = "openalex"
                        print(f"Matched '{search_title}' to '{oa_work.title}' (score: {best_score:.2f})")
                    else:
                        print(f"No good match for '{search_title}' (best score: {best_score:.2f})")
            
            if source:
                enriched["metadata_source"] = source
                enriched["metadata_confidence"] = 0.95 if doi else 0.7
                enriched["needs_review"] = False
                
                supabase.table("documents").update({
                    "metadata": enriched,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", doc_id).execute()
                
                enriched_count += 1
                print(f"Enriched {doc_id} via {source}")
            else:
                failed_count += 1
                # print(f"Failed to enrich {doc_id}")
                
        except Exception as e:
            failed_count += 1
            print(f"Error processing {doc_id}: {e}")

    print(f"Done. Enriched: {enriched_count}, Failed: {failed_count}, Skipped: {skipped_count}")

if __name__ == "__main__":
    asyncio.run(main())
