"""
Run Langfuse Experiment

Run the DevChat test suite and log results as a Langfuse experiment.
This allows you to compare different configurations.

Usage:
  python scripts/run_langfuse_experiment.py --name "baseline-v1"
  python scripts/run_langfuse_experiment.py --name "test-gpt4o-mini" --model "openai/gpt-4o-mini"
"""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse

# Initialize
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)


async def run_experiment(
    experiment_name: str,
    model: str = "openai/gpt-4o",
    max_studies: int = 5,
    use_claim_ledger: bool = True,
):
    """Run the test dataset through DevChat and log results."""
    
    from src.agents.devchat_agent import DevChatAgent, SearchSettings
    from src.retrieval.hybrid_retriever import HybridRetriever
    from evaluation.minicheck_evaluator import MiniCheckEvaluator
    
    # Get the dataset
    dataset = langfuse.get_dataset("devchat-graduation-tests")
    items = list(dataset.items)
    
    print(f"\n🧪 Running experiment: {experiment_name}")
    print(f"   Model: {model}")
    print(f"   Max studies: {max_studies}")
    print(f"   Claim ledger: {use_claim_ledger}")
    print(f"   Test cases: {len(items)}")
    print("-" * 50)
    
    # Initialize agent with custom collection and evaluator
    collection_name = "rag_0816e8d3-ab23-417c-bf3f-e45531411c73"
    agent = DevChatAgent(retriever=HybridRetriever(collection_name=collection_name))
    evaluator = MiniCheckEvaluator(backend='api', api_model='openai/gpt-4o-mini')
    
    settings = SearchSettings(
        max_studies=max_studies,
        use_claim_ledger=use_claim_ledger,
    )
    
    results = []
    
    for i, item in enumerate(items):
        query = item.input.get("query", "")
        expected = item.expected_output or {}
        
        print(f"\n[{i+1}/{len(items)}] {query[:50]}...")
        
        # Create a trace using v3 SDK (start_span creates a trace)
        trace = langfuse.start_span(
            name=f"experiment-{experiment_name}",
            input=query,
            metadata={
                "experiment": experiment_name,
                "model": model,
                "max_studies": max_studies,
                "use_claim_ledger": use_claim_ledger,
                "dataset_item_id": item.id,
                "category": expected.get("category"),
            },
        )
        
        try:
            start_time = time.time()
            
            # Run the query
            response = await agent.chat(query, search_settings=settings)
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Evaluate with MiniCheck
            eval_result = await evaluator.evaluate(
                query=query,
                answer=response.answer,
                contexts=[s.get("text", "") for s in response.citations] if response.citations else [],
                citations=response.citations or []
            )
            
            # Update trace with output
            trace.update(
                output=response.answer[:1000],
                metadata={
                    "faithfulness": eval_result.faithfulness,
                    "citation_recall": eval_result.citation_recall,
                    "citation_precision": eval_result.citation_precision,
                    "latency_ms": latency_ms,
                    "num_sources": response.num_sources,
                }
            )
            
            # End the trace span
            trace.end()
            
            # Log scores using v3 SDK - create_score method
            trace_id = trace.trace_id
            langfuse.create_score(trace_id=trace_id, name="faithfulness", value=eval_result.faithfulness)
            langfuse.create_score(trace_id=trace_id, name="citation_recall", value=eval_result.citation_recall)
            langfuse.create_score(trace_id=trace_id, name="citation_precision", value=eval_result.citation_precision)
            langfuse.create_score(trace_id=trace_id, name="latency_ms", value=latency_ms)
            
            # Note: Dataset item linking uses a different API in v3
            # The scores are still captured with the trace_id for analysis
            
            results.append({
                "query": query[:50],
                "faithfulness": eval_result.faithfulness,
                "citation_recall": eval_result.citation_recall,
                "citation_precision": eval_result.citation_precision,
                "latency_ms": latency_ms,
                "num_sources": response.num_sources,
                "success": True
            })
            
            print(f"   ✅ F={eval_result.faithfulness:.2f} R={eval_result.citation_recall:.2f} P={eval_result.citation_precision:.2f}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            trace.update(output=f"Error: {str(e)}")
            trace.end()
            results.append({
                "query": query[:50],
                "error": str(e),
                "success": False
            })
    
    # Calculate aggregates
    successful = [r for r in results if r.get("success")]
    if successful:
        avg_faith = sum(r["faithfulness"] for r in successful) / len(successful)
        avg_recall = sum(r["citation_recall"] for r in successful) / len(successful)
        avg_precision = sum(r["citation_precision"] for r in successful) / len(successful)
        avg_latency = sum(r["latency_ms"] for r in successful) / len(successful)
        
        print("\n" + "=" * 50)
        print(f"📊 Experiment Results: {experiment_name}")
        print("=" * 50)
        print(f"   Successful: {len(successful)}/{len(results)}")
        print(f"   Avg Faithfulness: {avg_faith:.2%}")
        print(f"   Avg Citation Recall: {avg_recall:.2%}")
        print(f"   Avg Citation Precision: {avg_precision:.2%}")
        print(f"   Avg Latency: {avg_latency:.0f}ms")
        print("\n   View in Langfuse:")
        print(f"   https://cloud.langfuse.com/project/cmjafx1vd00qkad06prpgl80o/datasets/devchat-graduation-tests")
    
    langfuse.flush()
    return results


def main():
    parser = argparse.ArgumentParser(description="Run a DevChat evaluation experiment")
    parser.add_argument("--name", required=True, help="Experiment name (e.g., 'baseline-v1')")
    parser.add_argument("--model", default="openai/gpt-4o", help="Model to use")
    parser.add_argument("--max-studies", type=int, default=5, help="Max studies to retrieve")
    parser.add_argument("--no-claim-ledger", action="store_true", help="Disable claim ledger")
    
    args = parser.parse_args()
    
    asyncio.run(run_experiment(
        experiment_name=args.name,
        model=args.model,
        max_studies=args.max_studies,
        use_claim_ledger=not args.no_claim_ledger,
    ))


if __name__ == "__main__":
    main()
