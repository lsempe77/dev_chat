"""
Dual-Lane Evaluator using MiniCheck as NLI backbone.

Lane A (Faithfulness/Groundedness): Is each claim supported by ANY retrieved context?
Lane B (Citation Alignment - ALCE-style): Does each citation actually entail its sentence?

References:
- MiniCheck (EMNLP 2024): https://arxiv.org/abs/2404.10774
- ALCE (ACL 2023): https://arxiv.org/abs/2305.14627

Backends:
- 'local': Downloads MiniCheck model (~3GB), runs on CPU (development)
- 'api': Uses LLM API for NLI (production, no model download)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Literal
import re
import logging
import os
import nltk

# Ensure NLTK punkt tokenizer is available
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

logger = logging.getLogger(__name__)


@dataclass
class DualLaneResult:
    """Results from dual-lane evaluation."""
    # Lane A: Groundedness
    faithfulness: float = 0.0
    
    # Lane B: Citation Alignment (ALCE-style metrics)
    citation_recall: float = 0.0
    citation_precision: float = 0.0
    
    # Legacy compatibility
    citation_accuracy: float = 0.0  # Average of recall and precision
    context_precision: float = 0.0
    citation_coverage: float = 0.0
    answer_relevancy: float = 0.0
    
    # Details for debugging
    claim_details: List[Dict] = field(default_factory=list)
    sentence_details: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class MiniCheckEvaluator:
    """
    Dual-lane evaluator using MiniCheck as NLI backbone.
    
    Lane A (Faithfulness): Is each claim grounded in ANY retrieved context?
    Lane B (Citation Alignment): Does each citation actually entail its sentence?
    
    MiniCheck can serve as the NLI backbone for BOTH lanes.
    The difference is what you pair together, not the model.
    
    Backends:
    - 'local': Downloads flan-t5-large (~3GB), runs on CPU
    - 'api': Uses LLM API (GPT-4o-mini) for NLI - no download needed
    """
    
    def __init__(
        self, 
        model_name: str = 'flan-t5-large', 
        cache_dir: str = './ckpts',
        backend: Literal['local', 'api'] = 'local',
        api_model: str = 'openai/gpt-4o-mini'
    ):
        """
        Initialize MiniCheck evaluator.
        
        Args:
            model_name: For 'local' backend - 'flan-t5-large' (770M) or 'Bespoke-MiniCheck-7B' (7B)
            cache_dir: Directory to cache model weights (local backend)
            backend: 'local' (download model) or 'api' (use LLM API, production)
            api_model: Model to use for API backend (e.g., 'openai/gpt-4o-mini')
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.backend = backend
        self.api_model = api_model
        self._scorer = None
        self._llm_client = None
        
    @property
    def scorer(self):
        """Lazy load MiniCheck model (local backend only)."""
        if self.backend != 'local':
            raise RuntimeError("scorer property only available for 'local' backend")
        if self._scorer is None:
            try:
                from minicheck.minicheck import MiniCheck
                logger.info(f"Loading MiniCheck model: {self.model_name}")
                self._scorer = MiniCheck(
                    model_name=self.model_name,
                    cache_dir=self.cache_dir
                )
                logger.info("MiniCheck model loaded successfully")
            except ImportError:
                raise ImportError(
                    "MiniCheck not installed. Install with:\n"
                    "pip install 'minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main'"
                )
        return self._scorer
    
    @property
    def llm_client(self):
        """Lazy load LLM client (API backend)."""
        if self._llm_client is None:
            from openai import OpenAI
            # Try to load from .env if not in environment
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except ImportError:
                pass
            
            # Use OpenRouter API (same as rest of project)
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY environment variable not set. "
                    "Required for API backend."
                )
            self._llm_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key
            )
        return self._llm_client
    
    def _nli_check_api(self, doc: str, claim: str) -> Tuple[bool, float]:
        """
        Check if claim is entailed by document using LLM API.
        
        Returns: (is_supported, confidence)
        """
        prompt = f"""You are an NLI (Natural Language Inference) evaluator.

Given a DOCUMENT and a CLAIM, determine if the claim is SUPPORTED by the document.
A claim is SUPPORTED if the document contains information that directly entails the claim.
A claim is NOT SUPPORTED if the document contradicts it OR doesn't contain relevant information.

DOCUMENT:
{doc[:4000]}

CLAIM:
{claim}

Respond with ONLY a JSON object:
{{"supported": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.api_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            # Parse JSON response
            import json
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            result = json.loads(content)
            return result.get("supported", False), result.get("confidence", 0.5)
        except Exception as e:
            logger.warning(f"API NLI check failed: {e}")
            return False, 0.0
    
    def _nli_score(self, docs: List[str], claims: List[str]) -> Tuple[List[int], List[float]]:
        """
        Score claims against documents using configured backend.
        
        Returns: (labels, probabilities) where label=1 means supported
        """
        if self.backend == 'local':
            pred_labels, probs, _, _ = self.scorer.score(docs=docs, claims=claims)
            return pred_labels, probs
        else:
            # API backend - process in parallel would be better but keeping simple
            labels = []
            probs = []
            for doc, claim in zip(docs, claims):
                supported, conf = self._nli_check_api(doc, claim)
                labels.append(1 if supported else 0)
                probs.append(conf)
            return labels, probs
    
    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: List[str],
        citations: List[Dict]
    ) -> DualLaneResult:
        """
        Run dual-lane evaluation.
        
        Args:
            query: User's question
            answer: Generated answer with [N] citation markers
            contexts: List of context strings (can be legacy format)
            citations: List of citation dicts with 'snippet', 'full_text', etc.
            
        Returns:
            DualLaneResult with faithfulness, citation_recall, citation_precision
        """
        errors = []
        claim_details = []
        sentence_details = []
        
        # Build passage lookup: {1: "text", 2: "text", ...}
        passages = self._build_passage_lookup(citations, contexts)
        
        if not passages:
            errors.append("No passages found in citations or contexts")
            return DualLaneResult(errors=errors)
        
        # Lane A: Faithfulness (Groundedness)
        try:
            claims = self._extract_claims(answer)
            faithfulness, claim_details = self._evaluate_faithfulness(claims, passages)
        except Exception as e:
            logger.error(f"Lane A (faithfulness) error: {e}")
            errors.append(f"Faithfulness error: {str(e)}")
            faithfulness = 0.0
        
        # Lane B: Citation Alignment (ALCE-style)
        try:
            sentences = self._extract_sentences_with_citations(answer)
            citation_recall, citation_precision, sentence_details = self._evaluate_citation_alignment(
                sentences, passages
            )
        except Exception as e:
            logger.error(f"Lane B (citation alignment) error: {e}")
            errors.append(f"Citation alignment error: {str(e)}")
            citation_recall = 0.0
            citation_precision = 0.0
        
        # Calculate legacy metrics for compatibility
        citation_accuracy = (citation_recall + citation_precision) / 2 if (citation_recall + citation_precision) > 0 else 0.0
        citation_coverage = self._calculate_coverage(answer, passages)
        
        return DualLaneResult(
            faithfulness=faithfulness,
            citation_recall=citation_recall,
            citation_precision=citation_precision,
            citation_accuracy=citation_accuracy,
            citation_coverage=citation_coverage,
            context_precision=citation_precision,  # Approximation
            answer_relevancy=0.0,  # Not implemented yet
            claim_details=claim_details,
            sentence_details=sentence_details,
            errors=errors if errors else []
        )
    
    def _build_passage_lookup(
        self, 
        citations: List[Dict], 
        contexts: List[str]
    ) -> Dict[int, str]:
        """
        Build a lookup from citation index to passage text.
        
        Args:
            citations: List of citation dicts
            contexts: Fallback list of context strings
            
        Returns:
            Dict mapping 1-indexed citation ID to passage text
        """
        passages = {}
        
        # Try to extract from citations first
        for i, cite in enumerate(citations, 1):
            # Try different keys for the text content
            # IMPORTANT: Prefer full_text over snippet for better NLI coverage
            text = (
                cite.get('full_text') or 
                cite.get('snippet') or 
                cite.get('text') or 
                cite.get('content') or 
                ''
            )
            if text:
                passages[i] = text
        
        # Fallback to contexts if no passages found
        if not passages and contexts:
            for i, ctx in enumerate(contexts, 1):
                if ctx:
                    passages[i] = ctx
        
        return passages
    
    def _extract_claims(self, answer: str) -> List[str]:
        """
        Extract individual claims from the answer.
        
        Uses sentence tokenization and filters out:
        - Very short sentences
        - Markdown headers
        - Meta-commentary (e.g., "I found X studies...")
        - Reference section content
        - Author names and study titles as standalone items
        """
        # Remove citation markers for claim extraction
        clean_answer = re.sub(r'\s*\[\d+\]', '', answer)
        
        # Remove Reference section if present
        ref_patterns = [
            r'## References.*$',
            r'---\s*## References.*$',
            r'\*\*References\*\*.*$',
        ]
        for pattern in ref_patterns:
            clean_answer = re.sub(pattern, '', clean_answer, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove the "Note: Additional evidence" footer
        clean_answer = re.sub(r'\*\*Note\*\*:.*?(?=\n\n|$)', '', clean_answer, flags=re.DOTALL)
        
        # Use NLTK sentence tokenizer
        try:
            sentences = nltk.sent_tokenize(clean_answer)
        except Exception:
            # Fallback to simple splitting
            sentences = re.split(r'(?<=[.!?])\s+', clean_answer)
        
        # Filter claims
        claims = []
        for s in sentences:
            s = s.strip()
            
            # Skip short sentences
            if len(s) <= 20:
                continue
            
            # Skip markdown headers (## Header, # Header)
            if re.match(r'^#+\s*', s):
                continue
            
            # Skip if it's just a markdown header with content on same line
            if s.startswith('##') or s.startswith('#'):
                continue
            
            # Skip meta-commentary about finding studies
            if re.match(r'^I found \d+ stud(y|ies)', s, re.IGNORECASE):
                continue
            
            # Skip lines that look like author lists (- Name, Name...)
            if re.match(r'^-\s+[A-Z][a-z]+\s+[A-Z]', s):
                continue
            
            # Skip lines that are just italicized titles (*Title Here*)
            if re.match(r'^\*[^*]+\*\.?$', s):
                continue
            
            # Skip "Unknown Author" entries
            if 'Unknown Author' in s:
                continue
            
            claims.append(s)
        
        return claims
    
    def _extract_sentences_with_citations(self, answer: str) -> List[Dict]:
        """
        Parse answer into sentences, tracking which citations each has.
        
        Input: "The program showed effects [1]. Participants improved [1][2]."
        Output: [
            {"text": "The program showed effects", "citations": [1]},
            {"text": "Participants improved", "citations": [1, 2]}
        ]
        """
        # Split on sentence boundaries, keeping citation markers
        # Handle both ". " and ".\n" as sentence boundaries
        raw_sentences = re.split(r'(?<=[.!?])(?:\s+|\n)', answer)
        
        result = []
        for sent in raw_sentences:
            sent = sent.strip()
            if not sent:
                continue
                
            # Find all [N] citations in this sentence
            citations = [int(m) for m in re.findall(r'\[(\d+)\]', sent)]
            
            # Remove citation markers from text
            clean_text = re.sub(r'\s*\[\d+\]', '', sent).strip()
            
            if clean_text and len(clean_text) > 10:
                result.append({
                    "text": clean_text,
                    "citations": citations,
                    "original": sent
                })
        
        return result
    
    def _evaluate_faithfulness(
        self, 
        claims: List[str], 
        passages: Dict[int, str]
    ) -> Tuple[float, List[Dict]]:
        """
        Lane A: Is each claim supported by ANY context?
        
        This is groundedness verification - we check if the claim
        is entailed by the combined retrieved passages.
        """
        if not claims:
            return 0.0, []
        
        # Combine all passages into one context
        combined_context = " ".join(passages.values())
        
        if not combined_context.strip():
            return 0.0, []
        
        # MiniCheck expects lists
        docs = [combined_context] * len(claims)
        
        try:
            pred_labels, probs = self._nli_score(docs=docs, claims=claims)
        except Exception as e:
            logger.error(f"NLI scoring failed: {e}")
            return 0.0, []
        
        # Build claim details
        details = []
        for claim, label, prob in zip(claims, pred_labels, probs):
            details.append({
                "claim": claim[:100] + "..." if len(claim) > 100 else claim,
                "supported": bool(label),
                "confidence": float(prob)
            })
        
        # Faithfulness = proportion of claims that are supported
        faithfulness = sum(pred_labels) / len(pred_labels)
        
        return faithfulness, details
    
    def _evaluate_citation_alignment(
        self, 
        sentences: List[Dict],
        passages: Dict[int, str]
    ) -> Tuple[float, float, List[Dict]]:
        """
        Lane B: Does each citation actually support the sentence it's attached to?
        
        ALCE-style metrics:
        - citation_recall: % of sentences entailed by their cited passages (jointly)
        - citation_precision: % of citations that are necessary (single citation entails)
        
        Returns:
            (citation_recall, citation_precision, sentence_details)
        """
        recall_scores = []
        precision_scores = []
        details = []
        
        for sent in sentences:
            if not sent["citations"]:
                continue  # Skip sentences without citations
            
            sent_text = sent["text"]
            sent_citations = sent["citations"]
            
            # CITATION RECALL: Does the joint cited passage entail the sentence?
            # Combine all cited passages for this sentence
            cited_passages_list = [
                passages[c] for c in sent_citations 
                if c in passages
            ]
            
            if cited_passages_list:
                joint_passage = " ".join(cited_passages_list)
                
                try:
                    pred_labels, probs = self._nli_score(
                        docs=[joint_passage], 
                        claims=[sent_text]
                    )
                    recall_score = pred_labels[0]
                    recall_prob = probs[0]
                except Exception as e:
                    logger.warning(f"Recall scoring failed for sentence: {e}")
                    recall_score = 0
                    recall_prob = 0.0
                
                recall_scores.append(recall_score)
            else:
                recall_score = 0
                recall_prob = 0.0
            
            # CITATION PRECISION: Is each citation necessary?
            # Check if each single citation alone entails the sentence
            per_citation_scores = []
            for cite_id in sent_citations:
                if cite_id not in passages:
                    per_citation_scores.append(0)
                    continue
                
                single_passage = passages[cite_id]
                
                try:
                    pred_labels, probs = self._nli_score(
                        docs=[single_passage], 
                        claims=[sent_text]
                    )
                    per_citation_scores.append(pred_labels[0])
                    precision_scores.append(pred_labels[0])
                except Exception as e:
                    logger.warning(f"Precision scoring failed for citation {cite_id}: {e}")
                    per_citation_scores.append(0)
                    precision_scores.append(0)
            
            details.append({
                "sentence": sent_text[:80] + "..." if len(sent_text) > 80 else sent_text,
                "citations": sent_citations,
                "recall_supported": bool(recall_score),
                "recall_confidence": float(recall_prob),
                "per_citation_support": per_citation_scores
            })
        
        # Calculate final scores
        citation_recall = (
            sum(recall_scores) / len(recall_scores) 
            if recall_scores else 0.0
        )
        citation_precision = (
            sum(precision_scores) / len(precision_scores) 
            if precision_scores else 0.0
        )
        
        return citation_recall, citation_precision, details
    
    def _calculate_coverage(self, answer: str, passages: Dict[int, str]) -> float:
        """
        Calculate what proportion of available sources are cited in the answer.
        """
        if not passages:
            return 0.0
        
        # Find all cited source IDs
        cited_ids = set(int(m) for m in re.findall(r'\[(\d+)\]', answer))
        
        # Calculate coverage
        available_ids = set(passages.keys())
        if not available_ids:
            return 0.0
        
        covered = cited_ids & available_ids
        coverage = len(covered) / len(available_ids)
        
        return coverage


# Convenience function for quick evaluation
async def evaluate_with_minicheck(
    query: str,
    answer: str,
    contexts: List[str],
    citations: List[Dict],
    model_name: str = 'flan-t5-large'
) -> DualLaneResult:
    """
    Quick evaluation function using MiniCheck.
    
    Args:
        query: User's question
        answer: Generated answer with [N] citation markers
        contexts: List of context strings
        citations: List of citation dicts
        model_name: MiniCheck model to use
        
    Returns:
        DualLaneResult
    """
    evaluator = MiniCheckEvaluator(model_name=model_name)
    return await evaluator.evaluate(query, answer, contexts, citations)
