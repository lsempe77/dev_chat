"""Debug evaluation to find why Citation Accuracy = 0%."""
import asyncio
import json
import re
from src.agents.devchat_agent import DevChatAgent, SearchSettings
from evaluation.reliable_evaluator import ReliableEvaluator


async def debug_eval():
    # Run one query
    agent = DevChatAgent()
    settings = SearchSettings(max_studies=3, use_claim_ledger=True)
    
    query = 'What is the graduation approach to poverty reduction?'
    print(f'Query: {query}')
    print('=' * 60)
    
    resp = await agent.chat(query, search_settings=settings)
    
    print(f'Answer preview: {resp.answer[:300]}...')
    print()
    print(f'Num citations returned: {len(resp.citations)}')
    print(f'Num sources: {resp.num_sources}')
    
    # Extract contexts
    contexts = [c.get('content', c.get('text', '')) for c in resp.citations]
    print(f'Contexts extracted: {len(contexts)}')
    print(f'Context lengths: {[len(c) for c in contexts]}')
    print()
    
    # Initialize evaluator
    evaluator = ReliableEvaluator()
    evaluator._setup()
    
    # Step 1: Extract claims
    claims = evaluator._extract_claims_regex(resp.answer)
    print(f'Claims extracted: {len(claims)}')
    for i, c in enumerate(claims[:3]):
        text = c["text"][:80]
        cits = c["citations"]
        print(f'  [{i+1}] {text}...')
        print(f'      Citations: {cits}')
    print()
    
    # Step 2: Check how many claims have citations
    cited_claims = [c for c in claims if c.get('citations')]
    print(f'Claims WITH citations: {len(cited_claims)} / {len(claims)}')
    print()
    
    # Step 3: Test embedding similarity manually
    if cited_claims and contexts:
        c = cited_claims[0]
        print(f'Testing first cited claim:')
        claim_text = c["text"][:100]
        print(f'  Claim: {claim_text}...')
        print(f'  Cited sources: {c["citations"]}')
        
        # Check if cited index is valid
        for idx in c['citations']:
            if 1 <= idx <= len(contexts):
                ctx_preview = contexts[idx-1][:150]
                print(f'  Context [{idx}]: {ctx_preview}...')
            else:
                print(f'  Context [{idx}]: OUT OF RANGE! (only {len(contexts)} contexts)')
    
    print()
    print('Full evaluation...')
    result = await evaluator.evaluate(
        query=query,
        answer=resp.answer,
        contexts=contexts,
        citations=resp.citations
    )
    
    print()
    print('RESULTS:')
    print(f'  Faithfulness:      {result.faithfulness:.3f}')
    print(f'  Citation Accuracy: {result.citation_accuracy:.3f}')
    print(f'  Context Precision: {result.context_precision:.3f}')
    print(f'  Citation Coverage: {result.citation_coverage:.3f}')
    print(f'  Answer Relevancy:  {result.answer_relevancy:.3f}')
    print()
    
    if result.claim_details:
        print('Claim details:')
        for c in result.claim_details[:5]:
            verified = c.get("citation_verified")
            sim = c.get("similarity", 0)
            text = c["text"][:50]
            cits = c.get("citations", [])
            print(f'  verified={verified}, sim={sim:.3f}, cits={cits}: {text}...')


if __name__ == '__main__':
    asyncio.run(debug_eval())
