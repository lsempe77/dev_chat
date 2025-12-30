"""Debug citation accuracy issue with single query."""
import asyncio
import json
import re
from src.agents.devchat_agent import DevChatAgent, SearchSettings
from evaluation.reliable_evaluator import ReliableEvaluator


async def debug():
    agent = DevChatAgent()
    evaluator = ReliableEvaluator()
    
    query = "What is the graduation approach to poverty reduction?"
    print(f"Query: {query}")
    print("=" * 60)
    
    # Run with claim ledger
    settings = SearchSettings(max_studies=3, use_claim_ledger=True)
    resp = await agent.chat(query, search_settings=settings)
    
    print(f"\nAnswer preview:\n{resp.answer[:500]}...")
    print(f"\nNumber of citations in response: {len(resp.citations)}")
    
    # Check what citation keys are available
    if resp.citations:
        print(f"\nCitation keys for first citation: {list(resp.citations[0].keys())}")
    
    # Build contexts with index preservation
    contexts = []
    for idx, c in enumerate(resp.citations, 1):
        full_context = c.get('full_text') or c.get('snippet', '')
        print(f"\n  Source [{idx}]: {c.get('title', 'No title')[:50]}...")
        print(f"    full_text: {len(c.get('full_text', '')) if c.get('full_text') else 'None'} chars")
        print(f"    snippet: {len(c.get('snippet', '')) if c.get('snippet') else 'None'} chars")
        print(f"    Using: {len(full_context)} chars")
        contexts.append(full_context if full_context else '')
    
    non_empty = [c for c in contexts if c]
    total_chars = sum(len(c) for c in contexts)
    print(f"\n  Total: {len(non_empty)}/{len(contexts)} sources with text, {total_chars:,} chars")
    
    # Extract claims to see what we're evaluating
    claims = evaluator._extract_claims_regex(resp.answer)
    cited_claims = [c for c in claims if c.get('citations')]
    print(f"\n  Claims extracted: {len(claims)} total, {len(cited_claims)} with citations")
    
    # Show first few claims
    for i, claim in enumerate(cited_claims[:5]):
        print(f"\n  Claim {i+1}: {claim['text'][:80]}...")
        print(f"    Citations: {claim['citations']}")
    
    # Now run evaluation
    print("\n" + "=" * 60)
    print("Running evaluation...")
    eval_result = await evaluator.evaluate(
        query=query,
        answer=resp.answer,
        contexts=contexts,
        citations=resp.citations
    )
    
    print(f"\nResults:")
    print(f"  Faithfulness:      {eval_result.faithfulness:.3f}")
    print(f"  Citation Accuracy: {eval_result.citation_accuracy:.3f}")
    print(f"  Context Precision: {eval_result.context_precision:.3f}")
    print(f"  Citation Coverage: {eval_result.citation_coverage:.3f}")
    print(f"  Answer Relevancy:  {eval_result.answer_relevancy:.3f}")
    
    # Show claim details
    print(f"\nClaim details:")
    for i, claim in enumerate(eval_result.claim_details[:5]):
        if claim.get('citations'):
            print(f"  {i+1}. {claim.get('text', '')[:60]}...")
            print(f"      Citations: {claim.get('citations')}, Verified: {claim.get('citation_verified')}, Sim: {claim.get('similarity', 0):.3f}")


if __name__ == '__main__':
    asyncio.run(debug())
