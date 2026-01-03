"""
Test Post-Hoc Verification Impact on Faithfulness.

Compares evaluation results with and without post-hoc verification.
"""

import asyncio
import sys
import os
import json
import argparse
from datetime import datetime
import re

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config.settings import settings
from src.agents.devchat_agent import DevChatAgent, DevChatAgentFactory, SearchSettings
from src.generation.post_hoc_verifier import PostHocVerifier
from evaluation.minicheck_evaluator import MiniCheckEvaluator

console = Console()

# Test queries
TEST_QUERIES = [
    "What is the graduation approach to poverty reduction?",
    "What are the key components of a graduation program?",
    "What is the evidence on graduation programs from Bangladesh?",
    "Find studies on graduation programs in Africa",
    "What do studies say about the long-term effects of graduation programs?",
]


async def run_single_query_pair(
    query: str,
    agent: DevChatAgent,
    evaluator: MiniCheckEvaluator,
    verifier: PostHocVerifier
) -> tuple:
    """Run a single query and return results with and without verification."""
    
    # Get response from agent (with claim ledger)
    search_settings = SearchSettings(max_studies=5, use_claim_ledger=True)
    resp = await agent.chat(query, search_settings=search_settings)
    
    original_answer = resp.answer
    
    # Build contexts and passages for evaluation/verification
    contexts = []
    passages = {}
    for idx, c in enumerate(resp.citations, 1):
        full_context = c.get('full_text') or c.get('snippet', '')
        contexts.append(full_context)
        if full_context:
            passages[idx] = full_context
    
    # Evaluate ORIGINAL answer (no post-hoc verification)
    result_original = await evaluator.evaluate(
        query=query,
        answer=original_answer,
        contexts=contexts,
        citations=resp.citations
    )
    
    # Apply post-hoc verification
    verification_result = verifier.verify(original_answer, passages, resp.citations)
    verified_answer = verification_result.verified_answer
    
    # Evaluate VERIFIED answer
    result_verified = await evaluator.evaluate(
        query=query,
        answer=verified_answer,
        contexts=contexts,
        citations=resp.citations
    )
    
    return (
        {
            "query": query[:50],
            "sources": resp.num_sources,
            "answer_length": len(original_answer),
            "faithfulness": result_original.faithfulness,
            "citation_recall": result_original.citation_recall,
            "citation_precision": result_original.citation_precision,
        },
        {
            "query": query[:50],
            "sources": resp.num_sources,
            "answer_length": len(verified_answer),
            "verified_sentences": verification_result.verified_sentences,
            "removed_sentences": verification_result.removed_sentences,
            "verification_rate": verification_result.verification_rate,
            "faithfulness": result_verified.faithfulness,
            "citation_recall": result_verified.citation_recall,
            "citation_precision": result_verified.citation_precision,
        }
    )


async def main(num_queries: int = 5, collection: str = "devchat_v2_enhanced"):
    """Run comparison test."""
    
    console.print(Panel.fit(
        "[bold cyan]Post-Hoc Verification A/B Test[/bold cyan]\n"
        "Comparing faithfulness WITH and WITHOUT post-hoc verification\n"
        "(Same response, verified vs original)",
        border_style="cyan"
    ))
    
    # Initialize agent with custom collection
    if collection:
        console.print(f"Using collection: [cyan]{collection}[/cyan]")
        agent = DevChatAgentFactory.create_with_custom_collection(collection)
    else:
        agent = DevChatAgent()
    
    evaluator = MiniCheckEvaluator(backend='api')
    # Use STRICTER threshold (0.75) to filter more aggressively
    verifier = PostHocVerifier(verification_threshold=0.75, remove_unverified=True)
    
    queries = TEST_QUERIES[:num_queries]
    
    results_without = []
    results_with = []
    
    for i, query in enumerate(queries, 1):
        console.print(f"\n[bold]Query {i}/{len(queries)}:[/bold] {query[:60]}...")
        
        try:
            result_no, result_yes = await run_single_query_pair(
                query, agent, evaluator, verifier
            )
            results_without.append(result_no)
            results_with.append(result_yes)
            
            console.print(f"  [red]WITHOUT verification:[/red] Faith={result_no['faithfulness']:.2f}")
            console.print(f"  [green]WITH verification:[/green] Faith={result_yes['faithfulness']:.2f} "
                         f"(removed {result_yes['removed_sentences']} sentences)")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
            results_without.append({"faithfulness": 0, "citation_recall": 0, "citation_precision": 0})
            results_with.append({"faithfulness": 0, "citation_recall": 0, "citation_precision": 0, "removed_sentences": 0})
    
    # Calculate averages
    def avg(results, key):
        vals = [r.get(key, 0) for r in results]
        return sum(vals) / len(vals) if vals else 0
    
    console.print("\n" + "=" * 60)
    console.print("[bold]RESULTS COMPARISON[/bold]")
    console.print("=" * 60)
    
    # Build comparison table
    table = Table(title="Post-Hoc Verification Impact")
    table.add_column("Metric", style="cyan")
    table.add_column("WITHOUT Verification", style="red")
    table.add_column("WITH Verification", style="green")
    table.add_column("Change", style="yellow")
    
    metrics = [
        ("Faithfulness", "faithfulness"),
        ("Citation Recall", "citation_recall"),
        ("Citation Precision", "citation_precision"),
    ]
    
    for label, key in metrics:
        val_without = avg(results_without, key)
        val_with = avg(results_with, key)
        change = val_with - val_without
        change_str = f"{change:+.3f}" if change != 0 else "0.000"
        table.add_row(
            label,
            f"{val_without:.3f}",
            f"{val_with:.3f}",
            change_str
        )
    
    console.print(table)
    
    # Detailed per-query comparison
    console.print("\n[bold]Per-Query Breakdown:[/bold]")
    detail_table = Table()
    detail_table.add_column("Query", style="dim", max_width=40)
    detail_table.add_column("Faith (NO)", style="red")
    detail_table.add_column("Faith (YES)", style="green")
    detail_table.add_column("Δ", style="yellow")
    detail_table.add_column("Removed", style="magenta")
    
    for i, (r_no, r_yes) in enumerate(zip(results_without, results_with)):
        query_short = queries[i][:38] + "..."
        f_no = r_no.get("faithfulness", 0)
        f_yes = r_yes.get("faithfulness", 0)
        delta = f_yes - f_no
        removed = r_yes.get("removed_sentences", 0)
        detail_table.add_row(
            query_short,
            f"{f_no:.2f}",
            f"{f_yes:.2f}",
            f"{delta:+.2f}",
            str(removed)
        )
    
    console.print(detail_table)
    
    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "collection": collection,
        "num_queries": num_queries,
        "without_verification": {
            "faithfulness": avg(results_without, "faithfulness"),
            "citation_recall": avg(results_without, "citation_recall"),
            "citation_precision": avg(results_without, "citation_precision"),
            "details": results_without
        },
        "with_verification": {
            "faithfulness": avg(results_with, "faithfulness"),
            "citation_recall": avg(results_with, "citation_recall"),
            "citation_precision": avg(results_with, "citation_precision"),
            "avg_removed_sentences": avg(results_with, "removed_sentences"),
            "details": results_with
        },
        "improvement": {
            "faithfulness": avg(results_with, "faithfulness") - avg(results_without, "faithfulness"),
            "citation_recall": avg(results_with, "citation_recall") - avg(results_without, "citation_recall"),
            "citation_precision": avg(results_with, "citation_precision") - avg(results_without, "citation_precision"),
        }
    }
    
    output_file = f"evaluation/post_hoc_verification_test_{collection}.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    console.print(f"\n[dim]Results saved to {output_file}[/dim]")
    
    # Summary
    improvement = output["improvement"]["faithfulness"]
    if improvement > 0.02:
        console.print(f"\n✅ [bold green]Post-hoc verification IMPROVED faithfulness by {improvement:+.3f}[/bold green]")
    elif improvement > 0:
        console.print(f"\n✅ [bold yellow]Post-hoc verification slightly improved faithfulness by {improvement:+.3f}[/bold yellow]")
    else:
        console.print(f"\n⚠️ [bold yellow]Post-hoc verification changed faithfulness by {improvement:+.3f}[/bold yellow]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test post-hoc verification impact")
    parser.add_argument("--queries", type=int, default=5, help="Number of queries to test")
    parser.add_argument("--collection", type=str, default="devchat_v2_enhanced", help="Qdrant collection")
    args = parser.parse_args()
    
    asyncio.run(main(num_queries=args.queries, collection=args.collection))
