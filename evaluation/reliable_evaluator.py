"""
DevChat v2.0 - Reliable Evaluation Framework

Uses deterministic methods instead of LLM-as-judge:
- NLI model (BART-MNLI) for faithfulness
- Embedding similarity (Cohere) for citation accuracy
- Reranker scores for context precision
- Regex for citation coverage
- LLM only for answer relevancy (hard to automate)

References:
- TRUE: https://arxiv.org/abs/2204.04991
- ALCE: https://arxiv.org/abs/2305.14627
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Lazy load heavy models
_nli_pipeline = None
_cohere_client = None


def get_nli_pipeline():
    """Lazy load NLI model."""
    global _nli_pipeline
    if _nli_pipeline is None:
        try:
            from transformers import pipeline
            logger.info("Loading NLI model (facebook/bart-large-mnli)...")
            _nli_pipeline = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1,  # CPU (use 0 for GPU)
            )
            logger.info("NLI model loaded")
        except Exception as e:
            logger.error(f"Failed to load NLI model: {e}")
            _nli_pipeline = None
    return _nli_pipeline


def get_cohere_client():
    """Lazy load Cohere client."""
    global _cohere_client
    if _cohere_client is None:
        try:
            import cohere
            _cohere_client = cohere.Client(settings.cohere_api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Cohere: {e}")
    return _cohere_client


@dataclass
class ReliableEvaluationResult:
    """Results from reliable evaluation."""
    query: str
    answer: str
    contexts: List[str]
    citations: List[Dict]
    
    # Metrics (0-1 scale)
    faithfulness: float = 0.0          # NLI-based
    citation_accuracy: float = 0.0     # Embedding similarity
    context_precision: float = 0.0     # From reranker scores
    citation_coverage: float = 0.0     # Regex-based
    answer_relevancy: float = 0.0      # LLM-based (only one)
    
    # Details
    claim_details: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def overall_score(self) -> float:
        """Weighted average."""
        weights = {
            'faithfulness': 0.30,
            'citation_accuracy': 0.25,
            'context_precision': 0.15,
            'citation_coverage': 0.15,
            'answer_relevancy': 0.15,
        }
        return (
            self.faithfulness * weights['faithfulness'] +
            self.citation_accuracy * weights['citation_accuracy'] +
            self.context_precision * weights['context_precision'] +
            self.citation_coverage * weights['citation_coverage'] +
            self.answer_relevancy * weights['answer_relevancy']
        )
    
    def to_dict(self) -> Dict:
        return {
            'query': self.query,
            'answer': self.answer[:300] + '...' if len(self.answer) > 300 else self.answer,
            'metrics': {
                'faithfulness': round(self.faithfulness, 3),
                'citation_accuracy': round(self.citation_accuracy, 3),
                'context_precision': round(self.context_precision, 3),
                'citation_coverage': round(self.citation_coverage, 3),
                'answer_relevancy': round(self.answer_relevancy, 3),
                'overall': round(self.overall_score(), 3),
            },
            'claim_count': len(self.claim_details),
            'errors': self.errors,
        }


class ReliableEvaluator:
    """
    Evaluate RAG quality using deterministic methods.
    
    Much more reliable than LLM-as-judge.
    """
    
    def __init__(self):
        self.nli = None
        self.cohere = None
        self.llm = None  # Only for answer relevancy
    
    def _setup(self):
        """Initialize models on first use."""
        if self.nli is None:
            self.nli = get_nli_pipeline()
        if self.cohere is None:
            self.cohere = get_cohere_client()
    
    def _setup_llm(self):
        """Initialize LLM for answer relevancy only."""
        if self.llm is None:
            try:
                from llama_index.llms.openai_like import OpenAILike
                self.llm = OpenAILike(
                    model="openai/gpt-4o-mini",
                    api_base="https://openrouter.ai/api/v1",
                    api_key=settings.openrouter_api_key,
                    max_tokens=100,
                    is_chat_model=True,
                )
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}")
    
    @staticmethod
    def extract_contexts_from_citations(citations: List[Dict]) -> List[str]:
        """
        Extract text content from citations.
        
        Citations may have content in different keys depending on source:
        - 'full_text': Complete study text for evaluation (preferred)
        - 'snippet': Short display snippet (fallback)
        - 'content': Legacy format
        - 'text': Alternative format
        """
        contexts = []
        for c in citations:
            # Try different possible keys, prefer full_text for evaluation
            content = (
                c.get('full_text') or
                c.get('snippet') or 
                c.get('content') or 
                c.get('text') or 
                c.get('chunk_text') or
                ''
            )
            if content:
                contexts.append(content)
        return contexts
    
    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: Optional[List[str]] = None,
        citations: Optional[List[Dict]] = None,
        reranker_scores: Optional[List[float]] = None,
    ) -> ReliableEvaluationResult:
        """
        Run full evaluation.
        
        Args:
            query: User's question
            answer: Generated answer
            contexts: Retrieved context chunks (if not provided, will be extracted from citations)
            citations: Citation metadata
            reranker_scores: Optional reranker scores (for context precision)
        """
        # Auto-extract contexts from citations if not provided
        if (not contexts or all(not c for c in contexts)) and citations:
            contexts = self.extract_contexts_from_citations(citations)
            logger.info(f"Auto-extracted {len(contexts)} contexts from citations")
        
        self._setup()
        
        result = ReliableEvaluationResult(
            query=query,
            answer=answer,
            contexts=contexts or [],
            citations=citations or [],
        )
        
        try:
            # 1. Extract claims from answer (simple regex, no LLM)
            claims = self._extract_claims_regex(answer)
            
            # 2. Faithfulness via NLI
            if claims and contexts:
                result.faithfulness = self._evaluate_faithfulness_nli(claims, contexts)
            
            # 3. Citation accuracy via embedding similarity
            if claims and contexts:
                result.citation_accuracy, result.claim_details = await self._evaluate_citation_accuracy_embeddings(
                    claims, contexts
                )
            
            # 4. Context precision from reranker scores
            if reranker_scores:
                result.context_precision = self._evaluate_context_precision_scores(reranker_scores)
            elif contexts:
                # Fallback: use embedding similarity to query
                result.context_precision = await self._evaluate_context_precision_embeddings(query, contexts)
            
            # 5. Citation coverage (regex-based)
            result.citation_coverage = self._calculate_citation_coverage_regex(answer, claims)
            
            # 6. Answer relevancy (only metric using LLM)
            result.answer_relevancy = await self._evaluate_relevancy_llm(query, answer)
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            result.errors.append(str(e))
        
        return result
    
    def _extract_claims_regex(self, answer: str) -> List[Dict]:
        """
        Extract claims using regex (no LLM).
        
        Splits answer into sentences, identifies citation patterns.
        """
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', answer)
        
        claims = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Skip very short
                continue
            
            # Find citation numbers [1], [2], etc.
            citation_pattern = r'\[(\d+)\]'
            cited_nums = [int(m) for m in re.findall(citation_pattern, sentence)]
            
            # Remove citations from sentence for cleaner claim
            clean_sentence = re.sub(citation_pattern, '', sentence).strip()
            
            if clean_sentence:
                claims.append({
                    'text': clean_sentence,
                    'original': sentence,
                    'citations': cited_nums,
                })
        
        return claims
    
    def _evaluate_faithfulness_nli(
        self, 
        claims: List[Dict], 
        contexts: List[str]
    ) -> float:
        """
        Evaluate faithfulness using NLI model.
        
        For each claim, check if context ENTAILS it.
        """
        if not self.nli or not claims:
            return 0.0
        
        combined_context = " ".join(contexts)[:4000]  # Truncate for model
        
        entailed_count = 0
        for claim in claims:
            try:
                # Use zero-shot classification with entailment
                result = self.nli(
                    combined_context,
                    candidate_labels=[claim['text']],
                    hypothesis_template="This text supports: {}",
                )
                
                # Score > 0.5 means entailed
                if result['scores'][0] > 0.5:
                    entailed_count += 1
                    claim['entailed'] = True
                    claim['entailment_score'] = result['scores'][0]
                else:
                    claim['entailed'] = False
                    claim['entailment_score'] = result['scores'][0]
                    
            except Exception as e:
                logger.warning(f"NLI failed for claim: {e}")
        
        return entailed_count / len(claims) if claims else 0.0
    
    async def _evaluate_citation_accuracy_embeddings(
        self,
        claims: List[Dict],
        contexts: List[str],
    ) -> Tuple[float, List[Dict]]:
        """
        Verify citations using embedding similarity.
        
        For each claim with citations, check if cited context is semantically similar.
        """
        if not self.cohere:
            logger.warning("Cohere client not available for citation accuracy")
            return 0.0, []
        
        cited_claims = [c for c in claims if c.get('citations')]
        if not cited_claims:
            logger.warning("No claims with citations found")
            return 0.0, claims
        
        logger.info(f"Evaluating citation accuracy: {len(cited_claims)} claims with citations, {len(contexts)} contexts")
        
        verified_count = 0
        skipped_no_context = 0
        
        for claim in cited_claims:
            try:
                # Get cited contexts
                cited_contexts = []
                for idx in claim['citations']:
                    if 1 <= idx <= len(contexts):
                        ctx = contexts[idx - 1]
                        if ctx:  # Only add non-empty contexts
                            cited_contexts.append(ctx)
                        else:
                            logger.debug(f"Claim cites [{idx}] but context is empty")
                    else:
                        logger.debug(f"Claim cites [{idx}] but only {len(contexts)} contexts available")
                
                if not cited_contexts:
                    claim['citation_verified'] = False
                    claim['similarity'] = 0.0
                    skipped_no_context += 1
                    continue
                
                # Embed claim and cited contexts
                texts_to_embed = [claim['text']] + [c[:2000] for c in cited_contexts]  # Truncate for embedding
                response = self.cohere.embed(
                    texts=texts_to_embed,
                    model="embed-v4.0",
                    input_type="search_document",
                )
                
                claim_embedding = np.array(response.embeddings[0])
                context_embeddings = [np.array(e) for e in response.embeddings[1:]]
                
                # Max cosine similarity with any cited context
                max_similarity = 0.0
                for ctx_emb in context_embeddings:
                    similarity = np.dot(claim_embedding, ctx_emb) / (
                        np.linalg.norm(claim_embedding) * np.linalg.norm(ctx_emb)
                    )
                    max_similarity = max(max_similarity, similarity)
                
                # Threshold: 0.6 for semantic similarity
                if max_similarity >= 0.6:
                    verified_count += 1
                    claim['citation_verified'] = True
                    logger.debug(f"Claim verified (sim={max_similarity:.3f}): {claim['text'][:50]}...")
                else:
                    claim['citation_verified'] = False
                    logger.debug(f"Claim NOT verified (sim={max_similarity:.3f}): {claim['text'][:50]}...")
                
                claim['similarity'] = float(max_similarity)
                
            except Exception as e:
                logger.warning(f"Embedding similarity failed: {e}")
                claim['citation_verified'] = False
        
        logger.info(f"Citation accuracy: {verified_count}/{len(cited_claims)} verified (skipped {skipped_no_context} with no context)")
        accuracy = verified_count / len(cited_claims) if cited_claims else 0.0
        return accuracy, claims
    
    def _evaluate_context_precision_scores(self, reranker_scores: List[float]) -> float:
        """
        Calculate context precision from reranker scores.
        
        Uses the actual reranker output (already computed during retrieval).
        """
        if not reranker_scores:
            return 0.0
        
        # Proportion of contexts with score > 0.5 (relevant)
        relevant_count = sum(1 for s in reranker_scores if s > 0.5)
        return relevant_count / len(reranker_scores)
    
    async def _evaluate_context_precision_embeddings(
        self,
        query: str,
        contexts: List[str],
    ) -> float:
        """
        Fallback: measure query-context similarity with embeddings.
        """
        if not self.cohere or not contexts:
            return 0.0
        
        try:
            # Embed query and contexts
            texts = [query] + contexts[:10]  # Limit to 10
            response = self.cohere.embed(
                texts=texts,
                model="embed-v4.0",
                input_type="search_query",
            )
            
            query_emb = np.array(response.embeddings[0])
            context_embs = [np.array(e) for e in response.embeddings[1:]]
            
            # Calculate similarities
            similarities = []
            for ctx_emb in context_embs:
                sim = np.dot(query_emb, ctx_emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(ctx_emb)
                )
                similarities.append(sim)
            
            # Proportion with similarity > 0.5
            relevant = sum(1 for s in similarities if s > 0.5)
            return relevant / len(similarities)
            
        except Exception as e:
            logger.error(f"Context precision embedding failed: {e}")
            return 0.0
    
    def _calculate_citation_coverage_regex(
        self, 
        answer: str, 
        claims: List[Dict]
    ) -> float:
        """
        Calculate citation coverage using regex.
        
        What % of claims have at least one citation?
        """
        if not claims:
            return 0.0
        
        cited_claims = sum(1 for c in claims if c.get('citations'))
        return cited_claims / len(claims)
    
    async def _evaluate_relevancy_llm(self, query: str, answer: str) -> float:
        """
        Evaluate answer relevancy using LLM.
        
        This is the ONLY metric using LLM (hardest to automate).
        """
        self._setup_llm()
        
        if not self.llm:
            return 0.5  # Default if LLM unavailable
        
        prompt = f"""Does this answer address the question? Rate 0-10.

QUESTION: {query}

ANSWER: {answer[:1000]}

Reply with ONLY a number 0-10."""

        try:
            response = await self.llm.acomplete(prompt)
            score = float(response.text.strip()) / 10.0
            return max(0.0, min(1.0, score))
        except Exception as e:
            logger.error(f"Relevancy LLM failed: {e}")
            return 0.5


async def run_reliable_evaluation(
    test_cases: List[Dict],
    agent,
) -> List[ReliableEvaluationResult]:
    """
    Run reliable evaluation on test cases.
    """
    evaluator = ReliableEvaluator()
    results = []
    
    for i, case in enumerate(test_cases):
        query = case.get('question', case.get('query', ''))
        print(f"\n[{i+1}/{len(test_cases)}] {query[:50]}...")
        
        try:
            # Get agent response
            print("  → Running agent...")
            response = await agent.chat(query)
            
            # Extract data
            contexts = [c.get('snippet', c.get('text', '')) for c in response.citations]
            
            # Get reranker scores if available
            reranker_scores = None
            if hasattr(response, 'reranker_scores'):
                reranker_scores = response.reranker_scores
            
            # Evaluate
            print("  → Evaluating (NLI + embeddings)...")
            result = await evaluator.evaluate(
                query=query,
                answer=response.answer,
                contexts=contexts,
                citations=response.citations,
                reranker_scores=reranker_scores,
            )
            
            print(f"  ✓ Score: {result.overall_score():.3f}")
            print(f"    Faith:{result.faithfulness:.2f} CitAcc:{result.citation_accuracy:.2f} "
                  f"CtxPrec:{result.context_precision:.2f} CitCov:{result.citation_coverage:.2f} "
                  f"Rel:{result.answer_relevancy:.2f}")
            
            results.append(result)
            
        except Exception as e:
            logger.error(f"Test case failed: {e}")
            results.append(ReliableEvaluationResult(
                query=query,
                answer="",
                contexts=[],
                citations=[],
                errors=[str(e)],
            ))
    
    return results
