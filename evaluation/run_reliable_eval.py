"""
Run reliable RAGAS evaluation using NLI + embeddings.

Usage:
    python run_reliable_eval.py
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()


async def main():
    print("=" * 60)
    print("RELIABLE RAGAS EVALUATION (NLI + Embeddings)")
    print("=" * 60)
    
    # Import after dotenv
    from src.agents.devchat_agent import DevChatAgent
    from evaluation.reliable_evaluator import run_reliable_evaluation
    
    # Load test cases
    test_file = Path("evaluation/test_cases.json")
    with open(test_file) as f:
        data = json.load(f)
    
    # Handle both formats: list or {"test_cases": [...]}
    if isinstance(data, dict) and "test_cases" in data:
        test_cases = data["test_cases"]
    elif isinstance(data, list):
        test_cases = data
    else:
        raise ValueError("Invalid test_cases.json format")
    
    print(f"\nLoaded {len(test_cases)} test cases")
    print("\nMethod comparison:")
    print("  OLD: LLM-as-judge (unreliable, expensive)")
    print("  NEW: NLI model + embedding similarity (deterministic, fast)")
    print()
    
    # Initialize agent
    print("Initializing agent...")
    agent = DevChatAgent()
    
    # Run evaluation
    print(f"\nRunning evaluation on {len(test_cases)} test cases...\n")
    results = await run_reliable_evaluation(test_cases, agent)
    
    # Calculate aggregates
    successful = [r for r in results if not r.errors]
    
    if successful:
        avg_metrics = {
            'faithfulness': sum(r.faithfulness for r in successful) / len(successful),
            'citation_accuracy': sum(r.citation_accuracy for r in successful) / len(successful),
            'context_precision': sum(r.context_precision for r in successful) / len(successful),
            'citation_coverage': sum(r.citation_coverage for r in successful) / len(successful),
            'answer_relevancy': sum(r.answer_relevancy for r in successful) / len(successful),
            'overall': sum(r.overall_score() for r in successful) / len(successful),
        }
    else:
        avg_metrics = {}
    
    # Print results
    print("\n" + "=" * 60)
    print("RELIABLE EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total cases: {len(test_cases)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(test_cases) - len(successful)}")
    
    if avg_metrics:
        print("\nAggregate Metrics (using reliable methods):")
        for metric, value in avg_metrics.items():
            method = ""
            if metric == "faithfulness":
                method = " (NLI model)"
            elif metric == "citation_accuracy":
                method = " (embedding similarity)"
            elif metric == "context_precision":
                method = " (reranker/embedding)"
            elif metric == "citation_coverage":
                method = " (regex)"
            elif metric == "answer_relevancy":
                method = " (LLM - only one)"
            print(f"  {metric}: {value:.3f}{method}")
        
        print("\nPer-Query Results:")
        for r in results:
            status = "✓" if not r.errors else "✗"
            print(f"  [{r.overall_score():.2f}] {status} {r.query[:50]}...")
    
    # Save results
    output_file = f"evaluation/reliable_results_{datetime.now().strftime('%Y-%m-%d')}.json"
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'method': 'reliable (NLI + embeddings)',
        'test_cases': len(test_cases),
        'successful': len(successful),
        'aggregate_metrics': avg_metrics,
        'results': [r.to_dict() for r in results],
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nSaved to {output_file}")
    
    # Compare with old method if available
    old_file = Path(f"evaluation/ragas_results_{datetime.now().strftime('%Y-%m-%d')}.json")
    if old_file.exists():
        print("\n" + "-" * 60)
        print("COMPARISON: Old (LLM) vs New (Reliable)")
        print("-" * 60)
        with open(old_file) as f:
            old_data = json.load(f)
        
        old_metrics = old_data.get('aggregate_metrics', {})
        
        print(f"{'Metric':<20} {'Old (LLM)':<12} {'New (Reliable)':<12} {'Diff':<10}")
        print("-" * 54)
        for metric in ['faithfulness', 'citation_accuracy', 'context_precision', 
                       'citation_coverage', 'answer_relevancy', 'overall']:
            old_val = old_metrics.get(metric, 0)
            new_val = avg_metrics.get(metric, 0)
            diff = new_val - old_val
            diff_str = f"+{diff:.3f}" if diff > 0 else f"{diff:.3f}"
            print(f"{metric:<20} {old_val:.3f}        {new_val:.3f}        {diff_str}")


if __name__ == "__main__":
    asyncio.run(main())
