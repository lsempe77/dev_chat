#!/usr/bin/env python
"""
DevChat v2.0 SOTA - Evaluation Script

Run evaluation on a test set using RAGAS metrics.

Usage:
    python scripts/run_evaluation.py --test-file evaluation/test_cases.json
    python scripts/run_evaluation.py --test-file evaluation/test_cases.json --output results.json
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.devchat_agent import DevChatAgent
from src.utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def load_test_cases(file_path: str) -> List[Dict]:
    """Load test cases from JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if isinstance(data, list):
        return data
    elif "test_cases" in data:
        return data["test_cases"]
    else:
        raise ValueError("Invalid test file format")


def evaluate_with_ragas(
    questions: List[str],
    answers: List[str],
    contexts: List[List[str]],
    ground_truths: List[str] = None,
) -> Dict:
    """
    Evaluate using RAGAS metrics.
    
    Metrics:
    - Faithfulness: Is the answer faithful to the context?
    - Answer Relevancy: Is the answer relevant to the question?
    - Context Precision: Is the context relevant?
    - Context Recall: Does the context contain the answer?
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        
        # Prepare dataset
        data = {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
        }
        
        if ground_truths:
            data["ground_truth"] = ground_truths
        
        dataset = Dataset.from_dict(data)
        
        # Select metrics
        metrics = [faithfulness, answer_relevancy, context_precision]
        if ground_truths:
            metrics.append(context_recall)
        
        # Run evaluation
        result = evaluate(dataset, metrics=metrics)
        
        return result.to_pandas().to_dict()
        
    except ImportError:
        logger.warning("RAGAS not installed. Using simple evaluation.")
        return simple_evaluate(questions, answers, contexts, ground_truths)


def simple_evaluate(
    questions: List[str],
    answers: List[str],
    contexts: List[List[str]],
    ground_truths: List[str] = None,
) -> Dict:
    """Simple evaluation without RAGAS."""
    results = {
        "total_questions": len(questions),
        "avg_answer_length": sum(len(a) for a in answers) / len(answers),
        "avg_context_chunks": sum(len(c) for c in contexts) / len(contexts),
        "empty_answers": sum(1 for a in answers if len(a) < 50),
    }
    
    if ground_truths:
        # Simple keyword overlap
        overlaps = []
        for answer, truth in zip(answers, ground_truths):
            answer_words = set(answer.lower().split())
            truth_words = set(truth.lower().split())
            overlap = len(answer_words & truth_words) / max(len(truth_words), 1)
            overlaps.append(overlap)
        results["avg_keyword_overlap"] = sum(overlaps) / len(overlaps)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run evaluation on DevChat"
    )
    
    parser.add_argument(
        "--test-file",
        type=str,
        default="evaluation/test_cases.json",
        help="Path to test cases JSON file",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for results",
    )
    
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Maximum number of test cases to run",
    )
    
    parser.add_argument(
        "--use-ragas",
        action="store_true",
        help="Use RAGAS for evaluation",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("DevChat v2.0 SOTA - Evaluation")
    logger.info("=" * 60)
    
    # Load test cases
    logger.info(f"\n📂 Loading test cases from: {args.test_file}")
    
    if not Path(args.test_file).exists():
        logger.error(f"Test file not found: {args.test_file}")
        logger.info("Creating sample test file...")
        create_sample_test_file(args.test_file)
        logger.info(f"Sample test file created: {args.test_file}")
        logger.info("Please edit and re-run evaluation.")
        return
    
    test_cases = load_test_cases(args.test_file)
    
    if args.max_cases:
        test_cases = test_cases[:args.max_cases]
    
    logger.info(f"✅ Loaded {len(test_cases)} test cases")
    
    # Initialize agent
    logger.info("\n🤖 Initializing DevChat agent...")
    agent = DevChatAgent()
    
    # Run evaluation
    logger.info("\n🧪 Running evaluation...")
    
    questions = []
    answers = []
    contexts = []
    ground_truths = []
    timings = []
    
    for i, case in enumerate(test_cases):
        question = case["question"]
        ground_truth = case.get("expected_answer", case.get("ground_truth"))
        
        logger.info(f"\n[{i+1}/{len(test_cases)}] {question[:60]}...")
        
        start_time = time.time()
        
        try:
            response = agent.chat_sync(question, include_citations=False)
            
            questions.append(question)
            answers.append(response.answer)
            contexts.append([c.get("title", "") for c in response.citations])
            if ground_truth:
                ground_truths.append(ground_truth)
            timings.append(response.total_time_ms)
            
            logger.info(f"  ✅ {response.total_time_ms:.0f}ms | {len(response.answer)} chars")
            
        except Exception as e:
            logger.error(f"  ❌ Error: {e}")
            questions.append(question)
            answers.append("")
            contexts.append([])
            if ground_truth:
                ground_truths.append(ground_truth)
            timings.append(0)
    
    # Calculate metrics
    logger.info("\n📊 Calculating metrics...")
    
    if args.use_ragas:
        metrics = evaluate_with_ragas(
            questions, answers, contexts,
            ground_truths if ground_truths else None
        )
    else:
        metrics = simple_evaluate(
            questions, answers, contexts,
            ground_truths if ground_truths else None
        )
    
    # Add timing metrics
    metrics["timing"] = {
        "avg_ms": sum(timings) / len(timings),
        "p50_ms": sorted(timings)[len(timings) // 2],
        "p95_ms": sorted(timings)[int(len(timings) * 0.95)],
    }
    
    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("📊 EVALUATION RESULTS")
    logger.info("=" * 60)
    
    for key, value in metrics.items():
        if isinstance(value, dict):
            logger.info(f"\n{key}:")
            for k, v in value.items():
                logger.info(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")
        else:
            logger.info(f"{key}: {value:.2f}" if isinstance(value, float) else f"{key}: {value}")
    
    # Save results
    if args.output:
        output_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "test_file": args.test_file,
            "num_cases": len(test_cases),
            "metrics": metrics,
            "detailed_results": [
                {
                    "question": q,
                    "answer_length": len(a),
                    "num_sources": len(c),
                    "time_ms": t,
                }
                for q, a, c, t in zip(questions, answers, contexts, timings)
            ],
        }
        
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        
        logger.info(f"\n💾 Results saved to: {args.output}")


def create_sample_test_file(file_path: str):
    """Create a sample test file."""
    sample = {
        "description": "Sample evaluation test cases for DevChat",
        "test_cases": [
            {
                "question": "What are the effects of conditional cash transfers on education?",
                "expected_answer": "Conditional cash transfers have been shown to improve school enrollment and attendance.",
                "category": "synthesis"
            },
            {
                "question": "List recent studies on microfinance",
                "expected_answer": "Studies on microfinance include...",
                "category": "lookup"
            },
            {
                "question": "Compare school meals and cash transfers for education",
                "expected_answer": "Both interventions show positive effects...",
                "category": "comparison"
            },
        ]
    }
    
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2)


if __name__ == "__main__":
    main()
