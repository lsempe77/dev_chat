#!/usr/bin/env python
"""
DevChat v2.0 - Citation Quality Evaluation

Run the custom RAGAS evaluation with citation accuracy metrics.

Usage:
    python scripts/evaluate_citations.py                     # Single test query
    python scripts/evaluate_citations.py --query "poverty"   # Custom query  
    python scripts/evaluate_citations.py --compare           # Compare old vs new
    python scripts/evaluate_citations.py --batch             # Run all test cases
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.devchat_agent import DevChatAgent, SearchSettings
from src.utils.logging import setup_logging, get_logger
from evaluation.ragas_evaluator import RAGASEvaluator, EvaluationResult, generate_report

setup_logging()
logger = get_logger(__name__)


async def evaluate_single_query(
    query: str,
    use_structured: bool = True,
    verbose: bool = True
) -> EvaluationResult:
    """Run evaluation on a single query."""
    if verbose:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"Using structured citations: {use_structured}")
        print('='*60)
    
    # Initialize agent
    agent = DevChatAgent()
    settings = SearchSettings(use_structured_citations=use_structured)
    
    # Get response
    if verbose:
        print("\n[1/3] Getting agent response...")
    response = await agent.chat(query, search_settings=settings)
    
    if verbose:
        print(f"  - Found {response.num_sources} sources")
        print(f"  - Model: {response.model_used}")
        print(f"  - Synthesis time: {response.synthesis_time_ms:.0f}ms")
    
    # Extract contexts
    contexts = [c.get('snippet', c.get('text', '')) for c in response.citations]
    
    # Run evaluation
    if verbose:
        print("\n[2/3] Running RAGAS evaluation...")
    evaluator = RAGASEvaluator()
    result = await evaluator.evaluate(
        query=query,
        answer=response.answer,
        contexts=contexts,
        citations=response.citations,
    )
    
    # Print results
    if verbose:
        print("\n[3/3] Results:")
        print(f"  - Faithfulness:      {result.faithfulness:.3f}")
        print(f"  - Answer Relevancy:  {result.answer_relevancy:.3f}")
        print(f"  - Context Precision: {result.context_precision:.3f}")
        print(f"  - Citation Accuracy: {result.citation_accuracy:.3f}")
        print(f"  - Citation Coverage: {result.citation_coverage:.3f}")
        print(f"  - Overall Score:     {result.overall_score():.3f}")
        
        if result.claims:
            print(f"\n  Claims extracted: {len(result.claims)}")
            verified = len([c for c in result.claims if c.get('verified')])
            print(f"  Claims verified: {verified}/{len(result.claims)}")
        
        print(f"\n--- ANSWER (first 1000 chars) ---")
        print(response.answer[:1000])
        if len(response.answer) > 1000:
            print("... [truncated]")
    
    return result


async def compare_approaches(query: str):
    """Compare standard vs structured synthesis."""
    print("\n" + "="*70)
    print("COMPARISON: Standard vs Structured Synthesis")
    print("="*70)
    
    # Run with standard synthesis
    print("\n>>> STANDARD SYNTHESIS (single-pass)")
    result_standard = await evaluate_single_query(query, use_structured=False)
    
    # Run with structured synthesis
    print("\n>>> STRUCTURED SYNTHESIS (two-pass)")
    result_structured = await evaluate_single_query(query, use_structured=True)
    
    # Print comparison
    print("\n" + "="*70)
    print("COMPARISON SUMMARY")
    print("="*70)
    
    metrics = ['faithfulness', 'answer_relevancy', 'context_precision', 
               'citation_accuracy', 'citation_coverage']
    
    print(f"\n{'Metric':<20} {'Standard':>12} {'Structured':>12} {'Diff':>10}")
    print("-"*54)
    
    improvements = {}
    for metric in metrics:
        std_val = getattr(result_standard, metric)
        struct_val = getattr(result_structured, metric)
        diff = struct_val - std_val
        improvements[metric] = diff
        diff_str = f"+{diff:.3f}" if diff > 0 else f"{diff:.3f}"
        indicator = "✅" if diff > 0 else "❌" if diff < 0 else "—"
        print(f"{metric:<20} {std_val:>12.3f} {struct_val:>12.3f} {diff_str:>8} {indicator}")
    
    print("-"*54)
    std_overall = result_standard.overall_score()
    struct_overall = result_structured.overall_score()
    diff = struct_overall - std_overall
    diff_str = f"+{diff:.3f}" if diff > 0 else f"{diff:.3f}"
    indicator = "✅" if diff > 0 else "❌"
    print(f"{'OVERALL':<20} {std_overall:>12.3f} {struct_overall:>12.3f} {diff_str:>8} {indicator}")
    
    # Summary
    improved = sum(1 for v in improvements.values() if v > 0)
    print(f"\n📊 {improved}/{len(metrics)} metrics improved with structured synthesis")
    
    return result_standard, result_structured


async def run_batch_evaluation():
    """Run evaluation on all test cases."""
    # Load test cases
    test_cases_path = Path(__file__).parent.parent / "evaluation" / "test_cases.json"
    
    if not test_cases_path.exists():
        print(f"❌ Test cases file not found: {test_cases_path}")
        return
    
    with open(test_cases_path) as f:
        data = json.load(f)
    
    test_cases = data.get('test_cases', [])
    
    print(f"\n{'='*60}")
    print(f"Running evaluation on {len(test_cases)} test cases")
    print(f"{'='*60}")
    
    agent = DevChatAgent()
    evaluator = RAGASEvaluator()
    
    results_standard = []
    results_structured = []
    
    for i, case in enumerate(test_cases):
        query = case.get('question', case.get('query', ''))
        print(f"\n[{i+1}/{len(test_cases)}] {query[:50]}...")
        
        try:
            # Standard synthesis
            settings_std = SearchSettings(use_structured_citations=False)
            response_std = await agent.chat(query, search_settings=settings_std)
            contexts_std = [c.get('snippet', '') for c in response_std.citations]
            result_std = await evaluator.evaluate(
                query=query,
                answer=response_std.answer,
                contexts=contexts_std,
                citations=response_std.citations,
            )
            results_standard.append(result_std)
            
            # Structured synthesis  
            settings_struct = SearchSettings(use_structured_citations=True)
            response_struct = await agent.chat(query, search_settings=settings_struct)
            contexts_struct = [c.get('snippet', '') for c in response_struct.citations]
            result_struct = await evaluator.evaluate(
                query=query,
                answer=response_struct.answer,
                contexts=contexts_struct,
                citations=response_struct.citations,
            )
            results_structured.append(result_struct)
            
            print(f"  Standard: {result_std.overall_score():.3f} | Structured: {result_struct.overall_score():.3f}")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Generate reports
    report_std = generate_report(results_standard)
    report_struct = generate_report(results_structured)
    
    # Print comparison
    print("\n" + "="*70)
    print("BATCH EVALUATION SUMMARY")
    print("="*70)
    
    print(f"\n{'Metric':<20} {'Standard':>12} {'Structured':>12} {'Improvement':>12}")
    print("-"*56)
    
    for metric in report_std['aggregate_metrics']:
        std_val = report_std['aggregate_metrics'][metric]
        struct_val = report_struct['aggregate_metrics'][metric]
        diff = struct_val - std_val
        pct = (diff / std_val * 100) if std_val > 0 else 0
        print(f"{metric:<20} {std_val:>12.3f} {struct_val:>12.3f} {pct:>+11.1f}%")
    
    # Save reports
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path(__file__).parent.parent / "evaluation" / "reports"
    output_dir.mkdir(exist_ok=True)
    
    with open(output_dir / f"standard_{timestamp}.json", 'w') as f:
        json.dump(report_std, f, indent=2)
    
    with open(output_dir / f"structured_{timestamp}.json", 'w') as f:
        json.dump(report_struct, f, indent=2)
    
    print(f"\n📁 Reports saved to: {output_dir}")
    
    return report_std, report_struct


async def main():
    parser = argparse.ArgumentParser(description="Evaluate DevChat citation quality")
    parser.add_argument("--query", "-q", type=str, help="Single query to evaluate")
    parser.add_argument("--compare", "-c", action="store_true", help="Compare standard vs structured")
    parser.add_argument("--batch", "-b", action="store_true", help="Run batch evaluation")
    parser.add_argument("--structured", "-s", action="store_true", help="Use structured synthesis")
    
    args = parser.parse_args()
    
    if args.batch:
        await run_batch_evaluation()
    elif args.compare:
        query = args.query or "What is the impact of cash transfers on poverty?"
        await compare_approaches(query)
    elif args.query:
        await evaluate_single_query(args.query, use_structured=args.structured)
    else:
        # Default: show help
        print("DevChat Citation Quality Evaluation")
        print("="*40)
        print("\nUsage examples:")
        print("  python scripts/evaluate_citations.py --query 'poverty reduction'")
        print("  python scripts/evaluate_citations.py --compare --query 'cash transfers'")
        print("  python scripts/evaluate_citations.py --batch")
        print("\nRun with --help for all options")


if __name__ == "__main__":
    asyncio.run(main())
