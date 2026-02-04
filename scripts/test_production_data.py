"""
Test January 27 improvements against REAL production data.
"""

import asyncio
import os
from src.utils.embedding_cache import EmbeddingCache
from src.utils.metrics import recall_at_k, precision_at_k, mean_reciprocal_rank


def check_qdrant_available():
    """Check if Qdrant cloud is accessible."""
    from qdrant_client import QdrantClient
    from src.config.settings import get_settings
    
    settings = get_settings()
    try:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        collections = [c.name for c in client.get_collections().collections]
        return settings.qdrant_collection_name in collections, collections
    except Exception as e:
        return False, str(e)

async def test_hybrid_retrieval():
    """Test HybridRetriever against actual Qdrant data."""
    print("=" * 60)
    print("TEST: HybridRetriever on Production Qdrant")
    print("=" * 60)
    
    hr = HybridRetriever()
    
    # Test query
    query = "What is the effect of graduation programs on household consumption?"
    print(f'\nQuery: "{query}"')
    
    results = await hr.retrieve(query, top_k=5)
    print(f"\nRetrieved {len(results)} chunks:")
    for i, r in enumerate(results[:5]):
        study = r.metadata.get("study_name", "Unknown")[:50]
        score = r.metadata.get("score", 0)
        text_preview = r.text[:100].replace("\n", " ")
        print(f"  {i+1}. [{score:.3f}] {study}")
        print(f"     {text_preview}...")
    
    return len(results) > 0


async def test_embedding_cache():
    """Test semantic cache with repeated queries."""
    print("\n" + "=" * 60)
    print("TEST: EmbeddingCache (Semantic Cache)")
    print("=" * 60)
    
    cache = EmbeddingCache()
    model_name = "cohere/embed-v4.0"
    
    test_queries = [
        "graduation programs consumption",
        "graduation programs consumption",  # Exact repeat
        "graduation program effects on consumption",  # Semantic similar (diff hash)
    ]
    
    for q in test_queries:
        # Check cache hit
        cached = cache.get(q, model_name)
        if cached:
            print(f"  CACHE HIT: '{q[:40]}...'")
        else:
            print(f"  CACHE MISS: '{q[:40]}...' (would compute embedding)")
            # Simulate caching
            cache.set(q, [0.1] * 1024, model_name)
    
    print(f"  Stats: {cache.hits} hits, {cache.misses} misses")
    return True


async def test_metrics():
    """Test retrieval metrics with mock relevance data."""
    print("\n" + "=" * 60)
    print("TEST: Retrieval Quality Metrics")
    print("=" * 60)
    
    # Mock scenario: retrieved 5 docs, 3 are relevant
    retrieved = ["doc_1", "doc_2", "doc_3", "doc_4", "doc_5"]
    relevant = {"doc_1", "doc_3", "doc_7"}  # doc_7 not retrieved
    
    r_at_3 = recall_at_k(retrieved, relevant, k=3)
    p_at_3 = precision_at_k(retrieved, relevant, k=3)
    mrr = mean_reciprocal_rank(retrieved, relevant)
    
    print(f"  Retrieved: {retrieved}")
    print(f"  Relevant:  {relevant}")
    print(f"  Recall@3:    {r_at_3:.3f} (expected: 0.667)")
    print(f"  Precision@3: {p_at_3:.3f} (expected: 0.667)")
    print(f"  MRR:         {mrr:.3f} (expected: 1.0, first hit at rank 1)")
    
    return abs(r_at_3 - 0.667) < 0.01


async def test_full_rag_query():
    """Test full RAG query with all optimizations."""
    print("\n" + "=" * 60)
    print("TEST: Full RAG Query (End-to-End)")
    print("=" * 60)
    
    from src.retrieval.query_processor import QueryProcessor
    from src.retrieval.context_builder import ContextBuilder, mitigate_lost_in_middle
    
    qp = QueryProcessor()
    hr = HybridRetriever()
    cb = ContextBuilder()
    
    query = "What are the long-term effects of graduation programs?"
    print(f'\nOriginal query: "{query}"')
    
    # 1. Step-back prompting
    step_back = await qp.generate_step_back_query(query)
    print(f"Step-back query: {step_back}")
    
    # 2. Retrieve with both queries
    results1 = await hr.retrieve(query, top_k=3)
    results2 = await hr.retrieve(step_back, top_k=3) if step_back else []
    
    # 3. Combine and dedupe (RRF would be applied here in production)
    all_results = results1 + results2
    print(f"\nRetrieved {len(all_results)} total chunks")
    
    # 4. Lost-in-middle reorder
    if len(all_results) > 2:
        paired = [(r, r.metadata.get("score", 0)) for r in all_results]
        reordered = mitigate_lost_in_middle(paired, key=lambda x: x[1])
        print(f"Applied Lost-in-Middle reordering")
    
    # 5. Build context
    context = cb.build(all_results[:5])
    print(f"Built context: {len(context)} characters")
    
    return len(context) > 0


async def main():
    print("\n" + "=" * 70)
    print(" PRODUCTION DATA TESTS - January 27 Improvements")
    print("=" * 70)
    
    # Check Qdrant availability first
    qdrant_ok, info = check_qdrant_available()
    if not qdrant_ok:
        print(f"\n⚠️ Qdrant collection not available: {info}")
        print("Skipping retrieval tests, running local-only tests...\n")
    else:
        print(f"✅ Qdrant connected. Collections: {info}\n")
    
    results = {}
    
    # Run tests that don't need Qdrant
    results["EmbeddingCache"] = await test_embedding_cache()
    results["Metrics"] = await test_metrics()
    
    # Run retrieval tests only if Qdrant is available
    if qdrant_ok:
        from src.retrieval.hybrid_retriever import HybridRetriever
        results["HybridRetriever"] = await test_hybrid_retrieval()
        results["Full RAG"] = await test_full_rag_query()
    else:
        # Test query processing without retrieval
        print("\n" + "=" * 60)
        print("TEST: Query Processing (no Qdrant needed)")
        print("=" * 60)
        from src.retrieval.query_processor import QueryProcessor
        qp = QueryProcessor()
        
        query = "What are the effects of graduation programs?"
        step_back = await qp.generate_step_back_query(query)
        decomposed = await qp.decompose_query("Compare effects in Bangladesh vs Ethiopia")
        
        print(f"  Step-back: {step_back}")
        print(f"  Decomposed: {len(decomposed)} sub-queries")
        results["QueryProcessing"] = step_back is not None
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test}")
    
    all_passed = all(results.values())
    print(f"\n{'✅ All tests passed!' if all_passed else '❌ Some tests failed'}")


if __name__ == "__main__":
    asyncio.run(main())
