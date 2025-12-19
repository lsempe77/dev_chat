"""
DevChat v2.0 - RAGAS Evaluation Framework

Implements evaluation metrics for RAG quality:
- Faithfulness: Answer uses only retrieved context
- Answer Relevancy: Answer addresses the question  
- Context Precision: Retrieved chunks are relevant
- Citation Accuracy: Citations point to correct sources (custom metric)

References:
- RAGAS: https://docs.ragas.io/
- ALCE: https://arxiv.org/abs/2305.14627
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EvaluationResult:
    """Results from evaluating a single query."""
    query: str
    answer: str
    contexts: List[str]
    citations: List[Dict]
    
    # Core RAGAS metrics (0-1 scale)
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    
    # Custom citation metrics
    citation_accuracy: float = 0.0  # % of citations that are verifiable
    citation_coverage: float = 0.0  # % of claims that are cited
    
    # Details for debugging
    claims: List[Dict] = field(default_factory=list)  # Extracted claims with verification
    errors: List[str] = field(default_factory=list)
    
    def overall_score(self) -> float:
        """Weighted average of all metrics."""
        weights = {
            'faithfulness': 0.25,
            'answer_relevancy': 0.20,
            'context_precision': 0.15,
            'citation_accuracy': 0.25,
            'citation_coverage': 0.15,
        }
        return (
            self.faithfulness * weights['faithfulness'] +
            self.answer_relevancy * weights['answer_relevancy'] +
            self.context_precision * weights['context_precision'] +
            self.citation_accuracy * weights['citation_accuracy'] +
            self.citation_coverage * weights['citation_coverage']
        )
    
    def to_dict(self) -> Dict:
        return {
            'query': self.query,
            'answer': self.answer[:500] + '...' if len(self.answer) > 500 else self.answer,
            'metrics': {
                'faithfulness': round(self.faithfulness, 3),
                'answer_relevancy': round(self.answer_relevancy, 3),
                'context_precision': round(self.context_precision, 3),
                'citation_accuracy': round(self.citation_accuracy, 3),
                'citation_coverage': round(self.citation_coverage, 3),
                'overall': round(self.overall_score(), 3),
            },
            'claims_count': len(self.claims),
            'verified_claims': len([c for c in self.claims if c.get('verified')]),
            'errors': self.errors,
        }


@dataclass
class Claim:
    """A single factual claim extracted from the answer."""
    text: str
    cited_sources: List[int]  # Citation numbers [1], [2], etc.
    verified: bool = False
    supporting_context: Optional[str] = None
    verification_reason: str = ""


class RAGASEvaluator:
    """
    Evaluate RAG quality using RAGAS-inspired metrics.
    
    Uses LLM as judge for nuanced evaluation.
    """
    
    def __init__(self, llm=None):
        self.llm = llm
        self._setup_llm()
    
    def _setup_llm(self):
        """Initialize LLM for evaluation."""
        if self.llm is None:
            try:
                from llama_index.llms.openrouter import OpenRouter
                self.llm = OpenRouter(
                    model="openai/gpt-4o-mini",
                    api_key=settings.openrouter_api_key,
                    max_tokens=2000,
                )
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}")
    
    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: List[str],
        citations: List[Dict],
    ) -> EvaluationResult:
        """
        Run full evaluation on a query-answer pair.
        
        Args:
            query: User's original question
            answer: Generated answer
            contexts: Retrieved context chunks (in order)
            citations: Citation metadata list
            
        Returns:
            EvaluationResult with all metrics
        """
        result = EvaluationResult(
            query=query,
            answer=answer,
            contexts=contexts,
            citations=citations,
        )
        
        try:
            # Extract claims from answer
            claims = await self._extract_claims(answer)
            result.claims = claims
            
            # Evaluate each metric
            result.faithfulness = await self._evaluate_faithfulness(answer, contexts)
            result.answer_relevancy = await self._evaluate_relevancy(query, answer)
            result.context_precision = await self._evaluate_context_precision(query, contexts)
            result.citation_accuracy = await self._evaluate_citation_accuracy(claims, contexts)
            result.citation_coverage = self._calculate_citation_coverage(claims)
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            result.errors.append(str(e))
        
        return result
    
    async def _extract_claims(self, answer: str) -> List[Dict]:
        """
        Extract factual claims from the answer.
        
        Returns list of claims with their cited sources.
        """
        prompt = f"""Extract all factual claims from this answer. For each claim, identify which citation numbers [1], [2], etc. support it.

ANSWER:
{answer}

Return as JSON array:
[
  {{"claim": "specific factual statement", "citations": [1, 2]}},
  {{"claim": "another claim", "citations": [3]}},
  {{"claim": "claim without citation", "citations": []}}
]

Only include factual claims (things that could be true or false), not opinions or general statements.
Return ONLY the JSON array, no other text."""

        try:
            response = await self.llm.acomplete(prompt)
            text = response.text.strip()
            
            # Clean up response - extract JSON
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            claims_data = json.loads(text)
            
            claims = []
            for c in claims_data:
                claims.append({
                    'text': c.get('claim', ''),
                    'citations': c.get('citations', []),
                    'verified': False,
                    'verification_reason': '',
                })
            
            return claims
            
        except Exception as e:
            logger.error(f"Claim extraction failed: {e}")
            return []
    
    async def _evaluate_faithfulness(self, answer: str, contexts: List[str]) -> float:
        """
        Evaluate if answer only uses information from contexts.
        
        Faithfulness = (claims supported by context) / (total claims)
        """
        combined_context = "\n\n---\n\n".join(contexts)
        
        prompt = f"""Evaluate if the answer is faithful to the provided context.

CONTEXT:
{combined_context[:8000]}

ANSWER:
{answer}

Rate faithfulness from 0.0 to 1.0:
- 1.0: Every claim in the answer is directly supported by the context
- 0.7: Most claims are supported, some minor extrapolations
- 0.5: Mix of supported and unsupported claims
- 0.3: Many claims are not in the context
- 0.0: Answer contradicts or ignores the context

Return ONLY a number between 0.0 and 1.0, nothing else."""

        try:
            response = await self.llm.acomplete(prompt)
            score = float(response.text.strip())
            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.error(f"Faithfulness evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_relevancy(self, query: str, answer: str) -> float:
        """
        Evaluate if answer addresses the question.
        """
        prompt = f"""Evaluate if the answer addresses the user's question.

QUESTION: {query}

ANSWER:
{answer}

Rate answer relevancy from 0.0 to 1.0:
- 1.0: Answer directly and completely addresses the question
- 0.7: Answer mostly addresses the question with some tangents
- 0.5: Answer partially addresses the question
- 0.3: Answer touches on the topic but doesn't really answer
- 0.0: Answer is completely off-topic

Return ONLY a number between 0.0 and 1.0, nothing else."""

        try:
            response = await self.llm.acomplete(prompt)
            score = float(response.text.strip())
            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.error(f"Relevancy evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_context_precision(self, query: str, contexts: List[str]) -> float:
        """
        Evaluate if retrieved contexts are relevant to query.
        """
        if not contexts:
            return 0.0
        
        prompt = f"""Evaluate how relevant the retrieved contexts are to the query.

QUERY: {query}

RETRIEVED CONTEXTS:
{chr(10).join([f"[{i+1}] {c[:500]}..." for i, c in enumerate(contexts)])}

Rate context precision from 0.0 to 1.0:
- 1.0: All contexts are highly relevant to the query
- 0.7: Most contexts are relevant
- 0.5: About half the contexts are relevant
- 0.3: Few contexts are relevant
- 0.0: No contexts are relevant

Return ONLY a number between 0.0 and 1.0, nothing else."""

        try:
            response = await self.llm.acomplete(prompt)
            score = float(response.text.strip())
            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.error(f"Context precision evaluation failed: {e}")
            return 0.0
    
    async def _evaluate_citation_accuracy(
        self,
        claims: List[Dict],
        contexts: List[str],
    ) -> float:
        """
        Verify each claim's citations point to supporting context.
        
        This is the ALCE-style verification.
        """
        if not claims:
            return 0.0
        
        cited_claims = [c for c in claims if c.get('citations')]
        if not cited_claims:
            return 0.0
        
        verified_count = 0
        
        for claim in cited_claims:
            claim_text = claim['text']
            cited_indices = claim['citations']
            
            # Get the cited contexts
            cited_contexts = []
            for idx in cited_indices:
                if 1 <= idx <= len(contexts):
                    cited_contexts.append(contexts[idx - 1])
            
            if not cited_contexts:
                continue
            
            # Verify claim against cited contexts
            combined = "\n\n".join(cited_contexts)
            
            prompt = f"""Does the cited context support this claim?

CLAIM: {claim_text}

CITED CONTEXT:
{combined[:3000]}

Answer with ONLY "yes" or "no"."""

            try:
                response = await self.llm.acomplete(prompt)
                if 'yes' in response.text.lower():
                    verified_count += 1
                    claim['verified'] = True
                    claim['verification_reason'] = 'Supported by cited context'
                else:
                    claim['verification_reason'] = 'Not supported by cited context'
            except Exception as e:
                logger.error(f"Citation verification failed: {e}")
        
        return verified_count / len(cited_claims)
    
    def _calculate_citation_coverage(self, claims: List[Dict]) -> float:
        """
        Calculate what percentage of claims have citations.
        """
        if not claims:
            return 0.0
        
        cited_claims = len([c for c in claims if c.get('citations')])
        return cited_claims / len(claims)


async def run_evaluation_batch(
    test_cases: List[Dict],
    agent,
) -> List[EvaluationResult]:
    """
    Run evaluation on a batch of test cases.
    
    Args:
        test_cases: List of {query, ...} dicts
        agent: DevChatAgent instance
        
    Returns:
        List of EvaluationResult objects
    """
    evaluator = RAGASEvaluator()
    results = []
    
    for i, case in enumerate(test_cases):
        query = case.get('question', case.get('query', ''))
        logger.info(f"Evaluating {i+1}/{len(test_cases)}: {query[:50]}...")
        
        try:
            # Get agent response
            response = await agent.chat(query)
            
            # Extract contexts from citations
            contexts = [c.get('snippet', c.get('text', '')) for c in response.citations]
            
            # Run evaluation
            result = await evaluator.evaluate(
                query=query,
                answer=response.answer,
                contexts=contexts,
                citations=response.citations,
            )
            results.append(result)
            
        except Exception as e:
            logger.error(f"Test case {i+1} failed: {e}")
            results.append(EvaluationResult(
                query=query,
                answer="",
                contexts=[],
                citations=[],
                errors=[str(e)],
            ))
    
    return results


def generate_report(results: List[EvaluationResult]) -> Dict:
    """Generate summary report from evaluation results."""
    if not results:
        return {'error': 'No results'}
    
    valid_results = [r for r in results if not r.errors]
    
    def avg(values):
        return sum(values) / len(values) if values else 0
    
    return {
        'timestamp': datetime.now().isoformat(),
        'total_cases': len(results),
        'successful': len(valid_results),
        'failed': len(results) - len(valid_results),
        'aggregate_metrics': {
            'faithfulness': round(avg([r.faithfulness for r in valid_results]), 3),
            'answer_relevancy': round(avg([r.answer_relevancy for r in valid_results]), 3),
            'context_precision': round(avg([r.context_precision for r in valid_results]), 3),
            'citation_accuracy': round(avg([r.citation_accuracy for r in valid_results]), 3),
            'citation_coverage': round(avg([r.citation_coverage for r in valid_results]), 3),
            'overall': round(avg([r.overall_score() for r in valid_results]), 3),
        },
        'per_query': [r.to_dict() for r in results],
    }


if __name__ == "__main__":
    # Quick test
    async def test():
        evaluator = RAGASEvaluator()
        
        result = await evaluator.evaluate(
            query="What is the impact of cash transfers on poverty?",
            answer="Cash transfers have been shown to reduce poverty [1]. Studies in Bangladesh found significant improvements in household income [2].",
            contexts=[
                "Study 1 found that cash transfers reduced poverty rates by 15%.",
                "Research in Bangladesh showed 20% increase in household income after cash transfers.",
            ],
            citations=[
                {"study_id": "study1", "title": "Cash Transfer Study"},
                {"study_id": "study2", "title": "Bangladesh Income Study"},
            ],
        )
        
        print(json.dumps(result.to_dict(), indent=2))
    
    asyncio.run(test())
