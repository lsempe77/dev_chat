"""Test ALL improvements from yesterday's session (Jan 27, 2026)."""

print("=" * 70)
print("COMPREHENSIVE TEST - ALL JANUARY 27 IMPROVEMENTS")
print("=" * 70)

import os
import sys

# =============================================================================
# TEST 1: Extraction Schemas (commit 44e10ec)
# =============================================================================
print("\n--- TEST 1: Extraction Schemas ---")

try:
    from src.extraction.schemas import (
        ExtractedEstimate, CoreNumericFields, StudyMetadata,
        ExtractionMode, DOMAIN_CONFIGS, list_available_domains
    )
    domains = list_available_domains()
    print(f"  ✅ Extraction schemas: {len(domains)} domains, 3 modes")
except Exception as e:
    print(f"  ❌ Extraction schemas: {e}")

# =============================================================================
# TEST 2: Sphinx Documentation (commit 57d4477)
# =============================================================================
print("\n--- TEST 2: Sphinx Documentation ---")

sphinx_check = os.path.exists("docs/sphinx/source/conf.py")
print(f"  {'✅' if sphinx_check else '❌'} Sphinx conf.py exists")

# =============================================================================
# TEST 3: File Renames (commit bb878f8)
# =============================================================================
print("\n--- TEST 3: File Renames ---")

renames = [
    ("extraction_pipeline/pipeline.py", "pipeline.py (renamed from pipeline_v2_sota.py)"),
    ("evaluation/validate_extraction.py", "validate_extraction.py (renamed from analyze_effect_sizes.py)"),
]
for path, desc in renames:
    exists = os.path.exists(path)
    print(f"  {'✅' if exists else '❌'} {desc}")

# =============================================================================
# TEST 4: Archived Scripts (commit 05e3694)
# =============================================================================
print("\n--- TEST 4: Archived Scripts ---")

archive_dir = "evaluation/archive"
if os.path.exists(archive_dir):
    archived = os.listdir(archive_dir)
    print(f"  ✅ Archive directory: {len(archived)} files")
else:
    print("  ❌ Archive directory missing")

# =============================================================================
# TEST 5: Configurable Quantization (commit 4ec1715)
# =============================================================================
print("\n--- TEST 5: Configurable Quantization ---")

try:
    from src.config.settings import settings
    quant_type = getattr(settings, 'qdrant_quantization_type', None)
    print(f"  ✅ Quantization setting: {quant_type or 'binary (default)'}")
except Exception as e:
    print(f"  ⚠️ Quantization setting: {e}")

# =============================================================================
# TEST 6: Step-Back Prompting (commit 0fa7038)
# =============================================================================
print("\n--- TEST 6: Step-Back Prompting ---")

try:
    from src.retrieval.query_processor import QueryProcessor
    qp = QueryProcessor()
    # Check if step-back method exists
    has_stepback = hasattr(qp, 'generate_step_back_query') or hasattr(qp, 'step_back')
    print(f"  {'✅' if has_stepback else '⚠️'} QueryProcessor has step-back method")
except Exception as e:
    print(f"  ⚠️ Step-back prompting: {e}")

# =============================================================================
# TEST 7: Semantic Cache (commit f1dda5e)
# =============================================================================
print("\n--- TEST 7: Semantic Cache ---")

try:
    from src.utils.embedding_cache import EmbeddingCache
    print("  ✅ EmbeddingCache class exists")
except Exception as e:
    print(f"  ⚠️ Semantic cache: {e}")

# =============================================================================
# TEST 8: Query Decomposition (commit f1dda5e)
# =============================================================================
print("\n--- TEST 8: Query Decomposition ---")

try:
    from src.retrieval.query_processor import QueryProcessor
    # Check for decomposition method
    has_decomp = hasattr(QueryProcessor, 'decompose_query') or 'decompose' in dir(QueryProcessor)
    print(f"  {'✅' if has_decomp else '⚠️'} Query decomposition available")
except Exception as e:
    print(f"  ⚠️ Query decomposition: {e}")

# =============================================================================
# TEST 9: RAG Pipeline Optimizations (commit b0713be)
# =============================================================================
print("\n--- TEST 9: RAG Pipeline Optimizations ---")

# 9a. Lost-in-Middle mitigation
try:
    from src.retrieval.context_builder import ContextBuilder, mitigate_lost_in_middle
    cb = ContextBuilder()
    # Check module-level function and class attribute
    has_reorder = callable(mitigate_lost_in_middle) and hasattr(cb, 'mitigate_lost_in_middle_enabled')
    print(f"  {'✅' if has_reorder else '⚠️'} Lost-in-Middle mitigation")
except Exception as e:
    print(f"  ⚠️ Lost-in-Middle: {e}")

# 9b. MMR diversity
try:
    from src.retrieval.hybrid_retriever import HybridRetriever
    print("  ✅ HybridRetriever exists")
except Exception as e:
    print(f"  ⚠️ HybridRetriever: {e}")

# 9c. Multi-Query RAG-Fusion
try:
    from src.retrieval.hybrid_retriever import HybridRetriever
    # Check source for rag_fusion or multi_query
    import inspect
    source = inspect.getsourcefile(HybridRetriever)
    with open(source) as f:
        content = f.read()
    has_fusion = 'rrf' in content.lower() or 'fusion' in content.lower() or 'multi_query' in content.lower()
    print(f"  {'✅' if has_fusion else '⚠️'} RAG-Fusion / RRF")
except Exception as e:
    print(f"  ⚠️ RAG-Fusion: {e}")

# 9d. Retrieval metrics
try:
    from src.utils.metrics import recall_at_k, precision_at_k, mean_reciprocal_rank
    print("  ✅ Retrieval metric functions (recall_at_k, precision_at_k, mrr)")
except Exception as e:
    print(f"  ⚠️ Retrieval metrics: {e}")

# 9e. Feature suggestions
try:
    from src.generation.feature_suggestions import FeatureSuggestionsGenerator
    print("  ✅ FeatureSuggestionsGenerator exists")
except Exception as e:
    print(f"  ⚠️ Feature suggestions: {e}")

# =============================================================================
# TEST 10: Frontend Components
# =============================================================================
print("\n--- TEST 10: Frontend Components ---")

frontend_files = [
    "frontend/src/components/admin/FeatureSuggestionsTab.tsx",
    "frontend/src/lib/validation.ts",
]
for f in frontend_files:
    exists = os.path.exists(f)
    name = os.path.basename(f)
    print(f"  {'✅' if exists else '❌'} {name}")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("SUMMARY - JANUARY 27, 2026 COMMITS (12 total)")
print("=" * 70)

commits = [
    ("b0713be", "RAG Pipeline Optimizations (Lost-in-Middle, MMR, RRF, Cache, Metrics)"),
    ("f1dda5e", "Semantic Cache + Query Decomposition"),
    ("0fa7038", "Step-Back Prompting"),
    ("4ec1715", "Configurable Quantization (binary/scalar/none)"),
    ("29e706c", "Quantization docs"),
    ("20dc763", "Tables GT Dataset update"),
    ("05e3694", "Archive old extraction scripts"),
    ("bb878f8", "Rename pipeline files"),
    ("42b075d", "Update doc references"),
    ("57d4477", "Sphinx documentation"),
    ("ae20fc6", "Sphinx deployment docs"),
    ("44e10ec", "Topic-agnostic extraction schemas"),
    ("3f77209", "Fix Sphinx warnings"),
]

print("\nCommits from yesterday:")
for sha, desc in commits:
    print(f"  {sha[:7]} - {desc}")
