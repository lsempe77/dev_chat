#!/usr/bin/env python
"""Run full RAGAS evaluation on test cases."""
import asyncio
import json
from evaluation.ragas_evaluator import RAGASEvaluator, run_evaluation_batch, generate_report
from src.agents.devchat_agent import DevChatAgent


async def run_full_eval():
    # Load test cases
    with open('evaluation/test_cases.json', 'r') as f:
        data = json.load(f)
    test_cases = data['test_cases']  # All 8 graduation-focused cases
    
    agent = DevChatAgent()
    
    print(f'Running RAGAS evaluation on {len(test_cases)} test cases...\n')
    for i, tc in enumerate(test_cases):
        print(f"  [{i+1}] {tc['id']}: {tc['question'][:50]}...")
    print()
    
    results = await run_evaluation_batch(test_cases, agent)
    
    report = generate_report(results)
    
    print('='*60)
    print('RAGAS EVALUATION RESULTS')
    print('='*60)
    print(f"Total cases: {report['total_cases']}")
    print(f"Successful: {report['successful']}")
    print(f"Failed: {report['failed']}")
    print()
    print('Aggregate Metrics:')
    for k, v in report['aggregate_metrics'].items():
        print(f"  {k}: {v:.3f}")
    
    print()
    print('Per-Query Results:')
    for r in report['per_query']:
        query = r['query'][:50] + '...' if len(r['query']) > 50 else r['query']
        overall = r['metrics']['overall']
        print(f"  [{overall:.2f}] {query}")
    
    # Save report
    with open('evaluation/ragas_results_2025-12-28.json', 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved to evaluation/ragas_results_2025-12-28.json")


if __name__ == "__main__":
    asyncio.run(run_full_eval())
