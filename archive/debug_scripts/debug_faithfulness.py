"""Debug faithfulness scoring to understand why claims are being flagged as unsupported."""
import asyncio
import json
from src.agents.devchat_agent import DevChatAgent, SearchSettings
from evaluation.minicheck_evaluator import MiniCheckEvaluator


async def debug_faithfulness():
    """Run one query and show detailed claim-level analysis."""
    
    # Load test case
    with open('evaluation/test_cases.json') as f:
        data = json.load(f)
    query = data['test_cases'][0]['question']  # First test case
    
    print(f"Query: {query}\n")
    print("=" * 80)
    
    # Get response with claim ledger
    agent = DevChatAgent()
    settings = SearchSettings(max_studies=3, use_claim_ledger=True)
    resp = await agent.chat(query, search_settings=settings)
    
    print("GENERATED ANSWER:")
    print("-" * 80)
    print(resp.answer)
    print("-" * 80)
    
    # Build contexts
    contexts = []
    for c in resp.citations:
        full_context = c.get('full_text') or c.get('snippet', '')
        contexts.append(full_context)
    
    # Initialize evaluator
    evaluator = MiniCheckEvaluator(backend='api', api_model='openai/gpt-4o-mini')
    
    # Run evaluation
    result = await evaluator.evaluate(
        query=query,
        answer=resp.answer,
        contexts=contexts,
        citations=resp.citations
    )
    
    print("\nFAITHFULNESS ANALYSIS (Lane A):")
    print("=" * 80)
    print(f"Overall Faithfulness: {result.faithfulness:.2%}")
    print(f"Total Claims: {len(result.claim_details)}")
    
    supported = [c for c in result.claim_details if c.get('supported')]
    unsupported = [c for c in result.claim_details if not c.get('supported')]
    
    print(f"Supported: {len(supported)}, Unsupported: {len(unsupported)}")
    print()
    
    print("UNSUPPORTED CLAIMS (flagged by NLI):")
    print("-" * 80)
    for i, claim in enumerate(unsupported, 1):
        print(f"{i}. {claim.get('claim', 'N/A')}")
        print(f"   Confidence: {claim.get('confidence', 0):.2f}")
        print()
    
    print("\nSUPPORTED CLAIMS:")
    print("-" * 80)
    for i, claim in enumerate(supported, 1):
        print(f"{i}. {claim.get('claim', 'N/A')}")
        print(f"   Confidence: {claim.get('confidence', 0):.2f}")
        print()
    
    # Show sample of context to understand what we're comparing against
    print("\nSAMPLE CONTEXT (first 1000 chars):")
    print("-" * 80)
    combined = " ".join(contexts)
    print(combined[:1000] + "..." if len(combined) > 1000 else combined)


if __name__ == '__main__':
    asyncio.run(debug_faithfulness())
