"""Evaluate Claim Ledger with MiniCheck dual-lane evaluator.

Dual-Lane Architecture:
- Lane A (Faithfulness): Is each claim grounded in ANY retrieved context?
- Lane B (Citation Alignment): Does each [N] citation actually entail its sentence?

Uses MiniCheck (EMNLP 2024) as NLI backbone for BOTH lanes.
"""
import asyncio
import json
import re
from datetime import datetime
from src.agents.devchat_agent import DevChatAgent, SearchSettings
from src.retrieval.context_builder import ContextBuilder
from evaluation.minicheck_evaluator import MiniCheckEvaluator


async def full_comparison():
    with open('evaluation/test_cases.json') as f:
        data = json.load(f)
    test_cases = data['test_cases'][:5]  # 5 queries
    
    agent = DevChatAgent()
    # Use MiniCheck dual-lane evaluator (SOTA, EMNLP 2024)
    # backend='api' uses LLM API (no model download, production-ready)
    # backend='local' downloads flan-t5-large (~3GB, development)
    evaluator = MiniCheckEvaluator(backend='api', api_model='openai/gpt-4o-mini')
    
    results = []
    
    print('Running Claim Ledger Evaluation (5 queries)...')
    print('=' * 60)
    
    for i, tc in enumerate(test_cases, 1):
        query = tc['question']
        expected = tc.get('expected_answer', '')
        
        print(f'[{i}/5] {query[:50]}...')
        
        # Run with claim ledger
        settings = SearchSettings(max_studies=5, use_claim_ledger=True)
        resp = await agent.chat(query, search_settings=settings)
        
        # Build FULL contexts for each source (use full_text for NLI evaluation)
        # IMPORTANT: Keep indices aligned! Use empty string for missing contexts.
        contexts = []
        for idx, c in enumerate(resp.citations, 1):
            # Prefer full_text (complete study text), fallback to snippet
            full_context = c.get('full_text') or c.get('snippet', '')
            contexts.append(full_context if full_context else '')
            if not full_context:
                print(f"  WARNING: Source [{idx}] has no context text!")
        
        non_empty = [c for c in contexts if c]
        total_context_chars = sum(len(c) for c in contexts)
        print(f"  Contexts: {len(non_empty)}/{len(contexts)} sources with text, {total_context_chars:,} chars total")
        
        # Evaluate using reliable evaluator
        eval_result = await evaluator.evaluate(
            query=query,
            answer=resp.answer,
            contexts=contexts,
            citations=resp.citations
        )
        
        # Extract metrics from result (now dual-lane)
        metrics = {
            'faithfulness': eval_result.faithfulness,
            'citation_recall': eval_result.citation_recall,
            'citation_precision': eval_result.citation_precision,
            'citation_accuracy': eval_result.citation_accuracy,  # Legacy: avg of recall + precision
            'context_precision': eval_result.context_precision,
            'citation_coverage': eval_result.citation_coverage,
            'answer_relevancy': eval_result.answer_relevancy,
            'overall': (eval_result.faithfulness + eval_result.citation_recall + eval_result.citation_precision) / 3
        }
        
        # Citation stats
        citations = re.findall(r'\[(\d+)\]', resp.answer)
        unique_cited = len(set(citations))
        coverage = unique_cited / resp.num_sources if resp.num_sources else 0
        
        results.append({
            'query': query[:50],
            'sources': resp.num_sources,
            'unique_cited': unique_cited,
            'coverage': coverage,
            **metrics
        })
        
        print(f'  Faith: {metrics["faithfulness"]:.2f}, CitRecall: {metrics["citation_recall"]:.2f}, CitPrec: {metrics["citation_precision"]:.2f}')
    
    # Aggregate
    def avg(k):
        return sum(r[k] for r in results) / len(results)
    
    print()
    print('=' * 60)
    print('CLAIM LEDGER RESULTS (MiniCheck Dual-Lane)')
    print('=' * 60)
    print('Lane A (Groundedness):')
    print(f'  Faithfulness:        {avg("faithfulness"):.3f}')
    print()
    print('Lane B (Citation Alignment - ALCE-style):')
    print(f'  Citation Recall:     {avg("citation_recall"):.3f}')
    print(f'  Citation Precision:  {avg("citation_precision"):.3f}')
    print()
    print('Combined:')
    print(f'  Citation Coverage:   {avg("citation_coverage"):.3f}')
    print(f'  Overall:             {avg("overall"):.3f}')
    
    # Compare to old (ReliableEvaluator baseline)
    old_faith = 0.306
    old_cit = 0.013  # Was broken - embedding similarity instead of NLI
    old_overall = 0.221
    
    print()
    print('COMPARISON vs OLD (ReliableEvaluator - broken citation_accuracy):')
    print(f'  Old Faithfulness:      {old_faith:.3f} -> New: {avg("faithfulness"):.3f} ({avg("faithfulness")-old_faith:+.3f})')
    print(f'  Old Citation Accuracy: {old_cit:.3f} (BROKEN)')
    print(f'  New Citation Recall:   {avg("citation_recall"):.3f}')
    print(f'  New Citation Precision:{avg("citation_precision"):.3f}')
    print(f'  Old Overall:           {old_overall:.3f} -> New: {avg("overall"):.3f} ({avg("overall")-old_overall:+.3f})')
    
    # Save
    out = {
        'timestamp': datetime.now().isoformat(),
        'method': 'claim_ledger_minicheck',
        'evaluator': 'MiniCheckEvaluator (flan-t5-large)',
        'num_queries': len(results),
        'averages': {
            'lane_a_faithfulness': avg('faithfulness'),
            'lane_b_citation_recall': avg('citation_recall'),
            'lane_b_citation_precision': avg('citation_precision'),
            'citation_coverage': avg('citation_coverage'),
            'overall': avg('overall')
        },
        'details': results
    }
    with open('evaluation/claim_ledger_minicheck_results.json', 'w') as f:
        json.dump(out, f, indent=2)
    print()
    print('Saved to evaluation/claim_ledger_minicheck_results.json')


if __name__ == '__main__':
    asyncio.run(full_comparison())
