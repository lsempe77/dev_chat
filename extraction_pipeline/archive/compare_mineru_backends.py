"""
Compare MinerU Pipeline vs Hybrid (VLM) Backends

This script tests both backends on the same PDFs to evaluate:
1. Figure vs table detection accuracy
2. Split table handling
3. Empty body issues
4. Overall table extraction quality

NOTE: MinerU runs on Modal (GPU), not locally. This script deploys a Modal function
to run the comparison, then fetches and analyzes the results.

Usage:
    # Test with a local PDF (uploads to Modal)
    python extraction_pipeline/compare_mineru_backends.py --pdf data/test_pdfs/121058359.pdf
    
    # Run comparison on Modal (deploys a test function)
    modal run extraction_pipeline/compare_mineru_backends.py
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Analysis Helpers (Run locally on results)
# ============================================================================

FIGURE_CAPTION_PATTERN = re.compile(r'\b(figure|fig\.?)\s*\d', re.IGNORECASE)
TABLE_CAPTION_PATTERN = re.compile(r'\btable\s*\d', re.IGNORECASE)


def get_caption(item: dict) -> str:
    """Extract caption from table item."""
    caption_list = item.get("table_caption", [])
    if caption_list and isinstance(caption_list, list):
        return caption_list[0] if caption_list else ""
    return str(caption_list) if caption_list else ""


def count_rows(body: str) -> int:
    """Count table rows."""
    if not body:
        return 0
    return body.lower().count('<tr')


def analyze_table(item: dict) -> dict:
    """Analyze a single table item."""
    caption = get_caption(item)
    body = item.get("table_body", "")
    
    return {
        "page_idx": item.get("page_idx", -1),
        "caption": caption[:100] if caption else None,
        "caption_length": len(caption),
        "body_length": len(body) if body else 0,
        "row_count": count_rows(body),
        "is_empty": not body or not body.strip() or body.strip() == "<table></table>",
        "is_figure_caption": bool(FIGURE_CAPTION_PATTERN.search(caption)),
        "is_table_caption": bool(TABLE_CAPTION_PATTERN.search(caption)),
        "has_footnote": bool(item.get("table_footnote")),
    }


def summarize_extraction(tables: list, backend_name: str) -> dict:
    """Generate summary statistics for extracted tables."""
    if not tables:
        return {"backend": backend_name, "total": 0}
    
    analyses = [analyze_table(t) for t in tables]
    
    empty_count = sum(1 for a in analyses if a["is_empty"])
    figure_count = sum(1 for a in analyses if a["is_figure_caption"])
    single_row = sum(1 for a in analyses if a["row_count"] == 1)
    valid_tables = sum(1 for a in analyses if 
                       not a["is_empty"] and 
                       not a["is_figure_caption"] and 
                       a["row_count"] >= 2)
    
    return {
        "backend": backend_name,
        "total": len(tables),
        "empty_body": empty_count,
        "figure_as_table": figure_count,
        "single_row": single_row,
        "valid_tables": valid_tables,
        "artifact_rate": f"{((empty_count + figure_count + single_row) / len(tables) * 100):.1f}%" if tables else "0%",
        "pages_with_tables": len(set(a["page_idx"] for a in analyses)),
    }


def compare_results(pipeline_result: dict, hybrid_result: dict, pdf_name: str) -> dict:
    """Compare extraction results from both backends."""
    print(f"\n{'='*60}")
    print(f"COMPARISON: {pdf_name}")
    print(f"{'='*60}")
    
    comparison = {
        "pdf": pdf_name,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Pipeline summary
    if pipeline_result.get("success"):
        p_tables = pipeline_result.get("tables", [])
        p_summary = summarize_extraction(p_tables, "pipeline")
        comparison["pipeline"] = p_summary
        print(f"\nPIPELINE: {p_summary['total']} tables")
        print(f"  - Empty body: {p_summary['empty_body']}")
        print(f"  - Figure as table: {p_summary['figure_as_table']}")
        print(f"  - Single row: {p_summary['single_row']}")
        print(f"  - Valid tables: {p_summary['valid_tables']}")
        print(f"  - Artifact rate: {p_summary['artifact_rate']}")
        print(f"  - Time: {pipeline_result.get('elapsed_seconds', 0):.1f}s")
    else:
        comparison["pipeline"] = {"error": pipeline_result.get("error")}
        print(f"\nPIPELINE: FAILED - {pipeline_result.get('error')}")
    
    # Hybrid summary
    if hybrid_result.get("success"):
        h_tables = hybrid_result.get("tables", [])
        h_summary = summarize_extraction(h_tables, "hybrid")
        comparison["hybrid"] = h_summary
        print(f"\nHYBRID (VLM): {h_summary['total']} tables")
        print(f"  - Empty body: {h_summary['empty_body']}")
        print(f"  - Figure as table: {h_summary['figure_as_table']}")
        print(f"  - Single row: {h_summary['single_row']}")
        print(f"  - Valid tables: {h_summary['valid_tables']}")
        print(f"  - Artifact rate: {h_summary['artifact_rate']}")
        print(f"  - Time: {hybrid_result.get('elapsed_seconds', 0):.1f}s")
    else:
        comparison["hybrid"] = {"error": hybrid_result.get("error")}
        print(f"\nHYBRID: FAILED - {hybrid_result.get('error')}")
    
    # Delta analysis
    if pipeline_result.get("success") and hybrid_result.get("success"):
        p_valid = comparison["pipeline"]["valid_tables"]
        h_valid = comparison["hybrid"]["valid_tables"]
        p_artifacts = comparison["pipeline"]["empty_body"] + comparison["pipeline"]["figure_as_table"]
        h_artifacts = comparison["hybrid"]["empty_body"] + comparison["hybrid"]["figure_as_table"]
        
        print(f"\n📊 DELTA:")
        print(f"  Valid tables: Pipeline={p_valid}, Hybrid={h_valid} (diff: {h_valid - p_valid:+d})")
        print(f"  Artifacts: Pipeline={p_artifacts}, Hybrid={h_artifacts} (diff: {h_artifacts - p_artifacts:+d})")
        
        if h_artifacts < p_artifacts:
            print(f"  ✅ Hybrid has FEWER artifacts ({p_artifacts - h_artifacts} less)")
        elif h_artifacts > p_artifacts:
            print(f"  ⚠️ Hybrid has MORE artifacts ({h_artifacts - p_artifacts} more)")
        else:
            print(f"  ➡️ Same artifact count")
        
        comparison["delta"] = {
            "valid_tables_diff": h_valid - p_valid,
            "artifacts_diff": h_artifacts - p_artifacts,
            "recommendation": "hybrid" if h_artifacts < p_artifacts else "pipeline" if h_artifacts > p_artifacts else "equal"
        }
    
    return comparison


def detailed_table_comparison(pipeline_result: dict, hybrid_result: dict):
    """Show detailed side-by-side comparison of tables."""
    print(f"\n{'='*60}")
    print("DETAILED TABLE COMPARISON")
    print(f"{'='*60}")
    
    p_tables = pipeline_result.get("tables", []) if pipeline_result.get("success") else []
    h_tables = hybrid_result.get("tables", []) if hybrid_result.get("success") else []
    
    # Group by page
    p_by_page = {}
    for t in p_tables:
        page = t.get("page_idx", -1)
        p_by_page.setdefault(page, []).append(t)
    
    h_by_page = {}
    for t in h_tables:
        page = t.get("page_idx", -1)
        h_by_page.setdefault(page, []).append(t)
    
    all_pages = sorted(set(list(p_by_page.keys()) + list(h_by_page.keys())))
    
    for page in all_pages:
        p_count = len(p_by_page.get(page, []))
        h_count = len(h_by_page.get(page, []))
        
        if p_count == h_count == 0:
            continue
        
        diff_marker = "⚠️" if p_count != h_count else "  "
        print(f"\n{diff_marker} Page {page}: Pipeline={p_count}, Hybrid={h_count}")
        
        # Show captions
        for i, t in enumerate(p_by_page.get(page, [])):
            caption = get_caption(t)[:60]
            rows = count_rows(t.get("table_body", ""))
            is_fig = "🖼️" if FIGURE_CAPTION_PATTERN.search(get_caption(t)) else ""
            is_empty = "⭕" if not t.get("table_body") else ""
            print(f"    [P{i+1}] {rows}rows {is_fig}{is_empty} {caption}")
        
        for i, t in enumerate(h_by_page.get(page, [])):
            caption = get_caption(t)[:60]
            rows = count_rows(t.get("table_body", ""))
            is_fig = "🖼️" if FIGURE_CAPTION_PATTERN.search(get_caption(t)) else ""
            is_empty = "⭕" if not t.get("table_body") else ""
            print(f"    [H{i+1}] {rows}rows {is_fig}{is_empty} {caption}")


# ============================================================================
# Modal Deployment for Backend Comparison
# ============================================================================

try:
    import modal
    MODAL_AVAILABLE = True
except ImportError:
    MODAL_AVAILABLE = False
    print("Warning: modal not installed. Install with: pip install modal")


if MODAL_AVAILABLE:
    # Create a Modal app for comparison testing
    compare_app = modal.App("mineru-backend-compare")
    
    # Use same image config as main Modal deployment
    compare_image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install(
            "libgl1-mesa-glx",
            "libglib2.0-0",
            "libsm6",
            "libxext6",
            "libxrender-dev",
        )
        .pip_install(
            "mineru[core]>=2.6.0",
            "pypdfium2>=4.30.0",
            "loguru",
        )
    )
    
    # Volume for caching HuggingFace models (needed for VLM)
    model_cache = modal.Volume.from_name("mineru-model-cache", create_if_missing=True)
    
    @compare_app.function(
        image=compare_image,
        gpu="T4",  # Use T4 for cost efficiency in testing
        timeout=1800,  # 30 min timeout
        volumes={"/root/.cache/huggingface": model_cache},
    )
    def run_pipeline_extraction(pdf_bytes: bytes, pdf_name: str) -> dict:
        """Run MinerU pipeline backend extraction on Modal GPU."""
        import copy
        import os
        import tempfile
        from datetime import datetime
        from pathlib import Path
        
        os.environ["MINERU_TABLE_MERGE_ENABLE"] = "true"
        os.environ["MINERU_TABLE_ENABLE"] = "true"
        
        print(f"Running PIPELINE backend on {pdf_name}...")
        start_time = datetime.now()
        
        try:
            from mineru.cli.common import prepare_env
            from mineru.data.data_reader_writer import FileBasedDataWriter
            from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
            from mineru.backend.pipeline.pipeline_middle_json_mkcontent import union_make as pipeline_union_make
            from mineru.backend.pipeline.model_json_to_middle_json import result_to_middle_json as pipeline_result_to_middle_json
            from mineru.utils.enum_class import MakeMode
            
            output_dir = tempfile.mkdtemp(prefix="mineru_pipeline_")
            
            infer_results, all_image_lists, all_pdf_docs, lang_list, ocr_enabled_list = pipeline_doc_analyze(
                [pdf_bytes],
                ["en"],
                parse_method="auto",
                formula_enable=True,
                table_enable=True,
            )
            
            if not infer_results:
                return {"success": False, "error": "No results", "backend": "pipeline"}
            
            model_list = infer_results[0]
            images_list = all_image_lists[0]
            pdf_doc = all_pdf_docs[0]
            _lang = lang_list[0]
            _ocr_enable = ocr_enabled_list[0]
            
            local_image_dir, local_md_dir = prepare_env(output_dir, Path(pdf_name).stem, "auto")
            image_writer = FileBasedDataWriter(local_image_dir)
            
            middle_json = pipeline_result_to_middle_json(
                model_list, images_list, pdf_doc, image_writer, _lang, _ocr_enable, True
            )
            
            pdf_info = middle_json["pdf_info"]
            image_dir = os.path.basename(local_image_dir)
            content_list = pipeline_union_make(pdf_info, MakeMode.CONTENT_LIST, image_dir)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            tables = []
            if isinstance(content_list, list):
                for item in content_list:
                    if isinstance(item, dict) and item.get("type") == "table":
                        tables.append(item)
            
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)
            
            print(f"Pipeline completed in {elapsed:.1f}s - Found {len(tables)} tables")
            
            return {
                "success": True,
                "backend": "pipeline",
                "tables": tables,
                "elapsed_seconds": elapsed,
                "page_count": len(pdf_info) if isinstance(pdf_info, list) else 0,
            }
            
        except Exception as e:
            import traceback
            return {"success": False, "error": str(e), "traceback": traceback.format_exc(), "backend": "pipeline"}
    
    
    @compare_app.function(
        image=compare_image,
        gpu="A10G",  # Need stronger GPU for VLM
        timeout=3600,  # 1 hour for VLM processing
        volumes={"/root/.cache/huggingface": model_cache},
    )
    def run_hybrid_extraction(pdf_bytes: bytes, pdf_name: str) -> dict:
        """Run MinerU hybrid (VLM) backend extraction on Modal GPU."""
        import os
        import tempfile
        from datetime import datetime
        from pathlib import Path
        
        os.environ["MINERU_TABLE_MERGE_ENABLE"] = "true"
        os.environ["MINERU_TABLE_ENABLE"] = "true"
        
        print(f"Running HYBRID (VLM) backend on {pdf_name}...")
        start_time = datetime.now()
        
        try:
            from mineru.cli.common import prepare_env
            from mineru.data.data_reader_writer import FileBasedDataWriter
            from mineru.backend.hybrid.hybrid_analyze import doc_analyze as hybrid_doc_analyze
            from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make
            from mineru.utils.enum_class import MakeMode
            from mineru.utils.engine_utils import get_vlm_engine
            
            output_dir = tempfile.mkdtemp(prefix="mineru_hybrid_")
            
            print("  Getting VLM engine...")
            backend = get_vlm_engine(inference_engine='auto', is_async=False)
            print(f"  Using VLM backend: {backend}")
            
            local_image_dir, local_md_dir = prepare_env(output_dir, Path(pdf_name).stem, "hybrid_auto")
            image_writer = FileBasedDataWriter(local_image_dir)
            
            print("  Running hybrid analysis...")
            middle_json, infer_result, vlm_ocr_enable = hybrid_doc_analyze(
                pdf_bytes,
                image_writer=image_writer,
                backend=backend,
                parse_method="hybrid_auto",
                language="en",
                inline_formula_enable=True,
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            pdf_info = middle_json["pdf_info"]
            image_dir = os.path.basename(local_image_dir)
            content_list = vlm_union_make(pdf_info, MakeMode.CONTENT_LIST, image_dir)
            
            tables = []
            if isinstance(content_list, list):
                for item in content_list:
                    if isinstance(item, dict) and item.get("type") == "table":
                        tables.append(item)
            
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)
            
            print(f"Hybrid completed in {elapsed:.1f}s - Found {len(tables)} tables")
            
            return {
                "success": True,
                "backend": "hybrid",
                "tables": tables,
                "elapsed_seconds": elapsed,
                "page_count": len(pdf_info) if isinstance(pdf_info, list) else 0,
                "vlm_backend": str(backend),
            }
            
        except Exception as e:
            import traceback
            return {"success": False, "error": str(e), "traceback": traceback.format_exc(), "backend": "hybrid"}
    
    
    @compare_app.local_entrypoint()
    def modal_main(
        pdf: str = None,
        pipeline_only: bool = False,
        hybrid_only: bool = False,
        output: str = None,
    ):
        """
        Run MinerU backend comparison on Modal.
        
        Args:
            pdf: Path to local PDF file to test
            pipeline_only: Only run pipeline backend
            hybrid_only: Only run hybrid backend
            output: Output JSON file for results
        """
        if not pdf:
            # Default test PDF
            default_pdfs = [
                "data/test_pdfs/121058359.pdf",
                "data/test_pdfs/alce_paper.pdf",
            ]
            for p in default_pdfs:
                if Path(p).exists():
                    pdf = p
                    break
        
        if not pdf or not Path(pdf).exists():
            print("❌ No PDF specified or found. Use --pdf <path>")
            print("\nExample:")
            print("  modal run extraction_pipeline/compare_mineru_backends.py --pdf data/test_pdfs/121058359.pdf")
            return
        
        pdf_path = Path(pdf)
        pdf_bytes = pdf_path.read_bytes()
        pdf_name = pdf_path.name
        
        print(f"\n🔬 MinerU Backend Comparison")
        print(f"PDF: {pdf_name} ({len(pdf_bytes) / 1024 / 1024:.1f} MB)")
        
        pipeline_result = None
        hybrid_result = None
        
        # Run pipeline
        if not hybrid_only:
            print(f"\n{'='*60}")
            print("Running PIPELINE backend on Modal (T4 GPU)...")
            print(f"{'='*60}")
            pipeline_result = run_pipeline_extraction.remote(pdf_bytes, pdf_name)
            
            if pipeline_result.get("success"):
                print(f"✅ Pipeline: {len(pipeline_result.get('tables', []))} tables in {pipeline_result.get('elapsed_seconds', 0):.1f}s")
            else:
                print(f"❌ Pipeline failed: {pipeline_result.get('error')}")
        
        # Run hybrid
        if not pipeline_only:
            print(f"\n{'='*60}")
            print("Running HYBRID (VLM) backend on Modal (A10G GPU)...")
            print(f"{'='*60}")
            hybrid_result = run_hybrid_extraction.remote(pdf_bytes, pdf_name)
            
            if hybrid_result.get("success"):
                print(f"✅ Hybrid: {len(hybrid_result.get('tables', []))} tables in {hybrid_result.get('elapsed_seconds', 0):.1f}s")
            else:
                print(f"❌ Hybrid failed: {hybrid_result.get('error')}")
        
        # Compare
        if pipeline_result and hybrid_result:
            comparison = compare_results(pipeline_result, hybrid_result, pdf_name)
            detailed_table_comparison(pipeline_result, hybrid_result)
            
            # Save results
            if output:
                output_path = Path(output)
                results = {
                    "comparison": comparison,
                    "pipeline_tables": pipeline_result.get("tables", []),
                    "hybrid_tables": hybrid_result.get("tables", []),
                }
                with open(output_path, "w") as f:
                    json.dump(results, f, indent=2, default=str)
                print(f"\n📄 Results saved to {output_path}")


# ============================================================================
# Local CLI (for analyzing results)
# ============================================================================

def main():
    """CLI entry point for local analysis."""
    parser = argparse.ArgumentParser(description="Compare MinerU Pipeline vs Hybrid backends")
    parser.add_argument("--pdf", type=str, help="Path to a specific PDF to test")
    parser.add_argument("--analyze", type=str, help="Analyze existing results JSON file")
    parser.add_argument("--output", type=str, help="Output JSON file for results")
    
    args = parser.parse_args()
    
    if args.analyze:
        # Analyze existing results
        with open(args.analyze) as f:
            results = json.load(f)
        
        if "pipeline_tables" in results and "hybrid_tables" in results:
            p_summary = summarize_extraction(results["pipeline_tables"], "pipeline")
            h_summary = summarize_extraction(results["hybrid_tables"], "hybrid")
            
            print(f"\nPIPELINE: {json.dumps(p_summary, indent=2)}")
            print(f"\nHYBRID: {json.dumps(h_summary, indent=2)}")
        else:
            print(json.dumps(results.get("comparison", results), indent=2))
    
    elif not MODAL_AVAILABLE:
        print("❌ Modal not installed. Install with: pip install modal")
        print("\nThen run with:")
        print("  modal run extraction_pipeline/compare_mineru_backends.py --pdf <path>")
    
    else:
        print("Use Modal to run the comparison:")
        print("  modal run extraction_pipeline/compare_mineru_backends.py --pdf <path>")
        print("\nOr analyze existing results:")
        print("  python extraction_pipeline/compare_mineru_backends.py --analyze results.json")


if __name__ == "__main__":
    main()
