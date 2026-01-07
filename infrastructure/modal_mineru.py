"""
MinerU PDF Processing on Modal with Cloudflare R2 Storage

This is the main entry point for Modal deployment. All heavy logic is in modal_lib/.

Architecture:
    Cloudflare R2 (/input-pdfs/) → Modal (GPU) → R2 (/outputs/) + Qdrant Cloud

Setup:
    1. pip install modal
    2. modal token new
    3. Create Modal secrets: r2-credentials, qdrant-credentials, cohere-credentials
    4. modal deploy infrastructure/modal_mineru.py

Usage:
    # Process all new PDFs in R2 bucket
    modal run infrastructure/modal_mineru.py --action run
    
    # Process single PDF
    modal run infrastructure/modal_mineru.py --action single --pdf-key "input-pdfs/paper.pdf"
    
    # Check status
    modal run infrastructure/modal_mineru.py --action status
"""

import modal

# Import app and all decorated functions from modal_lib
# The app object must be importable at module level for Modal to discover it
from modal_lib import (
    # Core app object (Modal discovers functions attached to this)
    app,
    # Config
    base_image,
    r2_secret,
    qdrant_secret,
    cohere_secret,
    supabase_secret,
    # Processing functions (these are @app.function decorated)
    process_pdf,
    process_pdf_rag,
    # Orchestration functions (these are @app.function decorated)
    orchestrate,
    orchestrate_rag,
    list_pdfs,
    check_qdrant_status,
)


# ============================================================================
# HTTP Web Endpoint (for Railway/Vercel trigger)
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret, cohere_secret, supabase_secret],
    timeout=600,
)
@modal.fastapi_endpoint(method="POST")
def trigger_processing(request: dict = None) -> dict:
    """
    HTTP endpoint to trigger PDF processing from Railway/Vercel.
    
    POST body (all optional):
        {
            "project_id": "uuid",           # If provided, process for this RAG project
            "force_reprocess": false,
            "check_qdrant": true,
            "max_documents": 0,             # 0 = unlimited
            "api_key": "optional-secret-key"
        }
    
    Returns:
        {
            "success": true,
            "processed": 5,
            "skipped": 3,
            "message": "Processing started"
        }
    
    URL will be like:
        https://[your-workspace]--devchat-mineru-trigger-processing.modal.run
    """
    import os
    from datetime import datetime
    
    print(f"Trigger received at {datetime.now().isoformat()}")
    
    if request is None:
        request = {}
    
    project_id = request.get("project_id")
    force_reprocess = request.get("force_reprocess", False)
    check_qdrant = request.get("check_qdrant", True)
    max_documents = request.get("max_documents", 0)
    
    # Safety check for force_reprocess
    if force_reprocess and not request.get("confirm_force", False):
        return {
            "success": False,
            "error": "force_reprocess=true requires confirm_force=true",
            "queued": 0,
        }
    
    # Optional API key validation
    expected_key = os.environ.get("TRIGGER_API_KEY")
    if expected_key:
        provided_key = request.get("api_key")
        if provided_key != expected_key:
            return {"success": False, "error": "Invalid or missing API key", "queued": 0}
    
    try:
        if project_id:
            # Process RAG project - spawn in background to avoid timeout
            print(f"Processing RAG project: {project_id}")
            
            # Use spawn() to start processing in background and return immediately
            # This prevents Railway's HTTP timeout from cancelling the job
            function_call = orchestrate_rag.spawn(
                project_id=project_id,
                force_reprocess=force_reprocess,
                max_documents=max_documents
            )
            
            return {
                "success": True,
                "project_id": project_id,
                "call_id": function_call.object_id,
                "status": "processing",
                "message": f"Processing started for project {project_id}. Check Modal dashboard for progress.",
            }
        else:
            # Process global input-pdfs folder - spawn in background
            function_call = orchestrate.spawn(
                force_reprocess=force_reprocess,
                check_qdrant=check_qdrant,
                max_documents=max_documents
            )
            
            return {
                "success": True,
                "call_id": function_call.object_id,
                "status": "processing",
                "max_documents": max_documents,
                "message": "Processing started. Check Modal dashboard for progress.",
            }
        
    except Exception as e:
        print(f"Error in trigger: {e}")
        return {"success": False, "error": str(e), "status": "failed"}


# ============================================================================
# CLI Entry Point
# ============================================================================

@app.local_entrypoint()
def main(
    action: str = "status",
    pdf_key: str = None,
    force: bool = False,
    project_id: str = None,
    max_documents: int = 0,
):
    """
    CLI for MinerU processing.
    
    Actions:
        status  - Show R2 and Qdrant status
        run     - Process all pending PDFs
        single  - Process a single PDF (requires --pdf-key)
        rag     - Process a RAG project (requires --project-id)
    """
    if action == "status":
        print("\n📁 R2 Storage:")
        r2_status = list_pdfs.remote()
        print(f"   Input PDFs: {r2_status['total_input']}")
        print(f"   Processed: {r2_status['processed']}")
        print(f"   Pending: {r2_status['pending']}")
        
        print("\n🔍 Qdrant:")
        qdrant_status = check_qdrant_status.remote()
        print(f"   Status: {qdrant_status['status']}")
        if "points_count" in qdrant_status:
            print(f"   Vectors: {qdrant_status['points_count']}")
        if "message" in qdrant_status:
            print(f"   Error: {qdrant_status['message']}")
    
    elif action == "run":
        print("\n🚀 Starting batch processing...")
        result = orchestrate.remote(force_reprocess=force, max_documents=max_documents)
        print(f"   Queued: {result['queued']}")
        print(f"   Skipped (fully indexed): {result.get('skipped_fully_indexed', 0)}")
        print(f"   Needs re-index: {result.get('needs_reindex', 0)}")
        print(f"   Total: {result['total']}")
    
    elif action == "single":
        if not pdf_key:
            print("❌ --pdf-key required for single processing")
            return
        print(f"\n📄 Processing: {pdf_key}")
        result = process_pdf.remote(pdf_key=pdf_key)
        print(f"   Success: {result['success']}")
        if result["success"]:
            print(f"   Chunks indexed: {result.get('chunks_indexed', 0)}")
            print(f"   Time: {result.get('elapsed_seconds', 0):.1f}s")
        else:
            print(f"   Error: {result.get('error')}")
    
    elif action == "rag":
        if not project_id:
            print("❌ --project-id required for RAG processing")
            return
        print(f"\n📚 Processing RAG project: {project_id}")
        result = orchestrate_rag.remote(
            project_id=project_id,
            force_reprocess=force,
            max_documents=max_documents
        )
        print(f"   Processed: {result.get('processed', 0)}")
        print(f"   Failed: {result.get('failed', 0)}")
        print(f"   Skipped: {result.get('skipped', 0)}")
        print(f"   Total: {result.get('total', 0)}")
    
    else:
        print(f"Unknown action: {action}")
        print("Use: status, run, single, or rag")
