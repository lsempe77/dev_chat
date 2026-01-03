"""
Test the new Claim Ledger synthesizer on a sample query.

Compares:
- OLD: StructuredSynthesizer (two-pass but generic extraction)
- NEW: ClaimLedgerSynthesizer (ALCE-style with exact quotes)
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Suppress debug logging
os.environ.setdefault("LOG_LEVEL", "WARNING")

from src.agents.devchat_agent import DevChatAgent, SearchSettings

async def test_claim_ledger():
    """Test the claim ledger approach on a sample query."""
    
    print("=" * 60)
    print("CLAIM LEDGER SYNTHESIZER TEST")
    print("=" * 60)
    
    agent = DevChatAgent()
    
    test_query = "What is the graduation approach to poverty reduction?"
    
    # Test 1: NEW Claim Ledger approach (default)
    print("\n[TEST 1] CLAIM LEDGER SYNTHESIZER (ALCE-style)")
    print("-" * 50)
    
    settings_new = SearchSettings(
        max_studies=5,
        use_structured_citations=True,
        use_claim_ledger=True,  # NEW approach
    )
    
    response_new = await agent.chat(
        query=test_query,
        search_settings=settings_new,
    )
    
    print(f"Query: {test_query}")
    print(f"Model: {response_new.model_used}")
    print(f"Sources: {response_new.num_sources}")
    print(f"Time: {response_new.total_time_ms:.0f}ms")
    print(f"\nAnswer preview (first 500 chars):")
    print(response_new.answer[:500])
    print("...")
    
    # Count citations in answer
    import re
    citations_new = re.findall(r'\[(\d+)\]', response_new.answer)
    unique_citations_new = set(citations_new)
    print(f"\n📊 Citation analysis:")
    print(f"  Total citation markers: {len(citations_new)}")
    print(f"  Unique sources cited: {len(unique_citations_new)}")
    print(f"  Sources with evidence: {unique_citations_new}")
    
    # Test 2: OLD Structured approach (for comparison)
    print("\n" + "=" * 60)
    print("[TEST 2] STRUCTURED SYNTHESIZER (old approach)")
    print("-" * 50)
    
    settings_old = SearchSettings(
        max_studies=5,
        use_structured_citations=True,
        use_claim_ledger=False,  # OLD approach
    )
    
    response_old = await agent.chat(
        query=test_query,
        search_settings=settings_old,
    )
    
    print(f"Query: {test_query}")
    print(f"Model: {response_old.model_used}")
    print(f"Sources: {response_old.num_sources}")
    print(f"Time: {response_old.total_time_ms:.0f}ms")
    print(f"\nAnswer preview (first 500 chars):")
    print(response_old.answer[:500])
    print("...")
    
    citations_old = re.findall(r'\[(\d+)\]', response_old.answer)
    unique_citations_old = set(citations_old)
    print(f"\n📊 Citation analysis:")
    print(f"  Total citation markers: {len(citations_old)}")
    print(f"  Unique sources cited: {len(unique_citations_old)}")
    print(f"  Sources cited: {unique_citations_old}")
    
    # Summary comparison
    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"{'Metric':<25} {'Claim Ledger':<15} {'Structured':<15}")
    print("-" * 55)
    print(f"{'Model':<25} {response_new.model_used:<15} {response_old.model_used:<15}")
    print(f"{'Time (ms)':<25} {response_new.total_time_ms:<15.0f} {response_old.total_time_ms:<15.0f}")
    print(f"{'Total citations':<25} {len(citations_new):<15} {len(citations_old):<15}")
    print(f"{'Unique sources cited':<25} {len(unique_citations_new):<15} {len(unique_citations_old):<15}")
    print(f"{'Sources available':<25} {response_new.num_sources:<15} {response_old.num_sources:<15}")
    coverage_new = len(unique_citations_new) / response_new.num_sources if response_new.num_sources else 0
    coverage_old = len(unique_citations_old) / response_old.num_sources if response_old.num_sources else 0
    print(f"{'Citation coverage %':<25} {coverage_new*100:<15.0f} {coverage_old*100:<15.0f}")
    
    print("\n✅ Test complete!")

if __name__ == "__main__":
    asyncio.run(test_claim_ledger())
