#!/usr/bin/env python
"""
DevChat v2.0 SOTA - Unified Command Line Interface

Single entry point for all DevChat commands.

Usage:
    devchat serve              # Start the API server
    devchat ingest             # Ingest documents into vector DB
    devchat evaluate           # Run RAGAS evaluation
    devchat process-pdfs       # Process PDFs with MinerU
    devchat citations          # Evaluate citation quality
    devchat check-metadata     # Check metadata in Qdrant
    devchat --help             # Show all commands

After installing with `pip install -e .`, the `devchat` command becomes available.
"""

import sys
from pathlib import Path

# Add project root to path for development
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import typer
from typing import Optional
from typing_extensions import Annotated

# Create main CLI app
app = typer.Typer(
    name="devchat",
    help="DevChat v2.0 SOTA - AI-powered assistant for 3ie Development Evidence Portal",
    add_completion=True,
    no_args_is_help=True,
)


# =============================================================================
# Server Command
# =============================================================================

@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Host to bind to")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Port to bind to")] = 8000,
    reload: Annotated[bool, typer.Option(help="Enable auto-reload")] = False,
    workers: Annotated[int, typer.Option(help="Number of worker processes")] = 1,
):
    """Start the DevChat API server."""
    import uvicorn
    
    typer.echo(f"🚀 Starting DevChat API server on {host}:{port}")
    
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level="info",
    )


# =============================================================================
# Ingest Command
# =============================================================================

@app.command()
def ingest(
    source: Annotated[str, typer.Option(help="Path to source documents")] = "./data/markdown",
    metadata: Annotated[Optional[str], typer.Option(help="Path to metadata CSV")] = None,
    collection: Annotated[Optional[str], typer.Option(help="Qdrant collection name")] = None,
    recreate: Annotated[bool, typer.Option(help="Recreate collection from scratch")] = False,
    batch_size: Annotated[int, typer.Option(help="Batch size for indexing")] = 100,
):
    """Ingest documents into the Qdrant vector database."""
    from scripts.ingest_documents import main as ingest_main
    
    typer.echo(f"📚 Ingesting documents from: {source}")
    
    # Build sys.argv for the script
    sys.argv = ["ingest_documents.py", "--source", source]
    if metadata:
        sys.argv.extend(["--metadata", metadata])
    if collection:
        sys.argv.extend(["--collection", collection])
    if recreate:
        sys.argv.append("--recreate")
    sys.argv.extend(["--batch-size", str(batch_size)])
    
    ingest_main()


# =============================================================================
# Process PDFs Command
# =============================================================================

@app.command("process-pdfs")
def process_pdfs(
    pdf_dir: Annotated[str, typer.Option("--pdf-dir", help="Directory containing PDFs")] = "./pdfs",
    output_dir: Annotated[Optional[str], typer.Option(help="Output directory")] = None,
    recursive: Annotated[bool, typer.Option(help="Search subdirectories")] = True,
    dry_run: Annotated[bool, typer.Option(help="List files without processing")] = False,
    skip_existing: Annotated[bool, typer.Option(help="Skip already processed")] = True,
):
    """Process PDFs with MinerU and ingest into vector database."""
    from scripts.process_pdfs import main as process_main
    
    typer.echo(f"📄 Processing PDFs from: {pdf_dir}")
    
    # Build sys.argv for the script
    sys.argv = ["process_pdfs.py", "--pdf-dir", pdf_dir]
    if output_dir:
        sys.argv.extend(["--output-dir", output_dir])
    if recursive:
        sys.argv.append("--recursive")
    if dry_run:
        sys.argv.append("--dry-run")
    if skip_existing:
        sys.argv.append("--skip-existing")
    
    process_main()


# =============================================================================
# Evaluate Command
# =============================================================================

@app.command()
def evaluate(
    test_file: Annotated[str, typer.Option(help="Path to test cases JSON")] = "./evaluation/test_cases.json",
    output: Annotated[Optional[str], typer.Option(help="Output file for results")] = None,
    metrics: Annotated[str, typer.Option(help="Metrics to compute")] = "all",
    verbose: Annotated[bool, typer.Option(help="Verbose output")] = True,
):
    """Run RAGAS evaluation on test cases."""
    from scripts.run_evaluation import main as eval_main
    
    typer.echo(f"📊 Running evaluation with test file: {test_file}")
    
    # Build sys.argv for the script
    sys.argv = ["run_evaluation.py", "--test-file", test_file]
    if output:
        sys.argv.extend(["--output", output])
    sys.argv.extend(["--metrics", metrics])
    if verbose:
        sys.argv.append("--verbose")
    
    eval_main()


# =============================================================================
# Citations Command
# =============================================================================

@app.command()
def citations(
    query: Annotated[Optional[str], typer.Option(help="Single query to evaluate")] = None,
    batch: Annotated[bool, typer.Option(help="Run all test cases")] = False,
    compare: Annotated[bool, typer.Option(help="Compare old vs new citations")] = False,
    output: Annotated[Optional[str], typer.Option(help="Output file for results")] = None,
):
    """Evaluate citation quality with custom RAGAS metrics."""
    import asyncio
    from scripts.evaluate_citations import main as citations_main
    
    typer.echo("🔍 Evaluating citation quality...")
    
    # Build sys.argv for the script
    sys.argv = ["evaluate_citations.py"]
    if query:
        sys.argv.extend(["--query", query])
    if batch:
        sys.argv.append("--batch")
    if compare:
        sys.argv.append("--compare")
    if output:
        sys.argv.extend(["--output", output])
    
    asyncio.run(citations_main())


# =============================================================================
# RAGAS Command
# =============================================================================

@app.command()
def ragas(
    query: Annotated[Optional[str], typer.Option(help="Query to evaluate")] = None,
    verbose: Annotated[bool, typer.Option(help="Show detailed output")] = True,
):
    """Run RAGAS evaluator directly."""
    import asyncio
    
    typer.echo("📈 Running RAGAS evaluator...")
    
    if query:
        # Import and run evaluation
        from evaluation.ragas_evaluator import RAGASEvaluator, generate_report
        from src.agents.devchat_agent import DevChatAgent
        
        async def run_eval():
            agent = DevChatAgent()
            response = await agent.chat(query)
            
            evaluator = RAGASEvaluator()
            contexts = [c.get('snippet', c.get('text', '')) for c in response.citations]
            result = await evaluator.evaluate(
                query=query,
                answer=response.answer,
                contexts=contexts,
                citations=response.citations,
            )
            
            print(generate_report([result]))
            return result
        
        asyncio.run(run_eval())
    else:
        typer.echo("Please provide a --query to evaluate")
        raise typer.Exit(1)


# =============================================================================
# Check Metadata Command
# =============================================================================

@app.command("check-metadata")
def check_metadata(
    doc_id: Annotated[Optional[str], typer.Option(help="Specific document ID to check")] = None,
    list_all: Annotated[bool, typer.Option("--list", help="List all document IDs")] = False,
):
    """Check metadata in Qdrant for debugging."""
    import os
    from dotenv import load_dotenv
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    load_dotenv()
    
    client = QdrantClient(
        url=os.getenv('QDRANT_URL'),
        api_key=os.getenv('QDRANT_API_KEY')
    )
    
    collection = os.getenv('QDRANT_COLLECTION_NAME', 'devchat_v2')
    
    # Get collection info
    info = client.get_collection(collection)
    typer.echo(f"Collection '{collection}' has {info.points_count} points")
    
    if doc_id:
        # Get specific document
        results = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[
                FieldCondition(key='doc_id', match=MatchValue(value=doc_id))
            ]),
            limit=1,
            with_payload=True
        )
        
        if results[0]:
            p = results[0][0].payload
            typer.echo(f"\n=== METADATA FOR {doc_id} ===")
            for key, value in sorted(p.items()):
                if key not in ['text', 'embedding']:
                    typer.echo(f"  {key}: {value}")
        else:
            typer.echo(f"Document not found: {doc_id}")
    
    if list_all:
        # Show all unique doc_ids
        typer.echo("\n=== ALL DOC IDS ===")
        all_results = client.scroll(
            collection_name=collection, 
            limit=500, 
            with_payload=["doc_id"]
        )
        doc_ids = set(
            r.payload.get('doc_id') 
            for r in all_results[0] 
            if r.payload.get('doc_id')
        )
        for d in sorted(doc_ids):
            typer.echo(f"  - {d}")
        typer.echo(f"\nTotal unique documents: {len(doc_ids)}")


# =============================================================================
# Version Command
# =============================================================================

@app.command()
def version():
    """Show DevChat version information."""
    typer.echo("DevChat v2.0.0 SOTA")
    typer.echo("AI-powered assistant for 3ie Development Evidence Portal")
    typer.echo("")
    typer.echo("Components:")
    typer.echo("  - FastAPI backend")
    typer.echo("  - Qdrant vector database")
    typer.echo("  - Cohere embeddings (embed-v4)")
    typer.echo("  - OpenRouter LLM (GPT-4o/Claude)")
    typer.echo("  - MinerU PDF processing")


# =============================================================================
# Health Command
# =============================================================================

@app.command()
def health(
    detailed: Annotated[bool, typer.Option(help="Show detailed status")] = False,
):
    """Check health of all services."""
    import asyncio
    import httpx
    
    async def check_health():
        base_url = "http://localhost:8000"
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Basic health
                response = await client.get(f"{base_url}/health/ping")
                if response.status_code == 200:
                    typer.echo("✅ API Server: healthy")
                else:
                    typer.echo("❌ API Server: unhealthy")
                
                if detailed:
                    # Full health check
                    response = await client.get(f"{base_url}/health")
                    data = response.json()
                    
                    typer.echo(f"\nStatus: {data.get('status', 'unknown')}")
                    typer.echo(f"Version: {data.get('version', 'unknown')}")
                    
                    components = data.get('components', {})
                    typer.echo("\nComponents:")
                    for name, status in components.items():
                        icon = "✅" if status else "❌"
                        typer.echo(f"  {icon} {name}")
                        
        except httpx.ConnectError:
            typer.echo("❌ API Server: not running")
            typer.echo("\nStart with: devchat serve")
            raise typer.Exit(1)
    
    asyncio.run(check_health())


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
