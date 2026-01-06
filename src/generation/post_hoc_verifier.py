"""
Post-Hoc Verification Layer for Claim Ledger Synthesis.

This module verifies claims in generated answers AFTER synthesis and
removes/flags claims that cannot be grounded in source documents.

Workflow:
1. Extract claims from the generated answer
2. For each claim, run MiniCheck against ALL retrieved passages
3. Filter out claims that fail verification (not supported by any source)
4. Reconstruct the answer with only verified claims

This is Phase 4 of the Citation Improvement Plan.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import os

from src.utils.json_utils import safe_json_loads

logger = logging.getLogger(__name__)


@dataclass
class VerifiedSentence:
    """A sentence with verification results."""
    text: str
    citations: List[int]  # Citation numbers [1], [2], etc.
    is_verified: bool = False
    verification_score: float = 0.0
    verification_reason: str = ""
    original_index: int = 0


@dataclass
class VerificationResult:
    """Result of post-hoc verification."""
    original_answer: str
    verified_answer: str
    total_sentences: int = 0
    verified_sentences: int = 0
    removed_sentences: int = 0
    verification_rate: float = 0.0
    sentence_details: List[VerifiedSentence] = field(default_factory=list)


class PostHocVerifier:
    """
    Verifies generated answers against source documents.
    
    Uses MiniCheck (via LLM API) to check if each sentence in the answer
    is actually supported by the cited sources.
    """
    
    def __init__(
        self,
        api_model: str = 'openai/gpt-4o-mini',
        verification_threshold: float = 0.5,
        remove_unverified: bool = True
    ):
        """
        Initialize the verifier.
        
        Args:
            api_model: LLM model for NLI verification
            verification_threshold: Minimum score to consider verified (0.0-1.0)
            remove_unverified: If True, remove unverified sentences; if False, flag them
        """
        self.api_model = api_model
        self.verification_threshold = verification_threshold
        self.remove_unverified = remove_unverified
        self._llm_client = None
        
    @property
    def llm_client(self):
        """Lazy load LLM client."""
        if self._llm_client is None:
            from openai import OpenAI
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except ImportError:
                pass
            
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY environment variable not set.")
            
            self._llm_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key
            )
        return self._llm_client
    
    def _extract_sentences_with_citations(self, answer: str) -> List[Tuple[str, List[int], int]]:
        """
        Extract sentences that contain citations.
        
        Returns: List of (sentence_text, [citation_numbers], original_index)
        """
        # Remove headers and formatting
        clean_text = re.sub(r'^#+\s*.*$', '', answer, flags=re.MULTILINE)
        clean_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean_text)
        
        # Split into sentences (handling abbreviations)
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(sentence_pattern, clean_text.strip())
        
        result = []
        for idx, sent in enumerate(sentences):
            sent = sent.strip()
            if not sent:
                continue
            
            # Find all citation markers [N] or [N, M, ...]
            citation_pattern = r'\[(\d+(?:,\s*\d+)*)\]'
            citations = []
            for match in re.finditer(citation_pattern, sent):
                nums = [int(n.strip()) for n in match.group(1).split(',')]
                citations.extend(nums)
            
            # Only include sentences with citations (those making claims)
            if citations:
                result.append((sent, list(set(citations)), idx))
        
        return result
    
    def _verify_sentence_against_passages(
        self,
        sentence: str,
        passages: Dict[int, str],
        cited_sources: List[int]
    ) -> Tuple[bool, float, str]:
        """
        Verify if sentence is supported by the cited passages.
        
        Returns: (is_verified, confidence, reason)
        """
        if not cited_sources:
            return False, 0.0, "No citations in sentence"
        
        # Remove citation markers for cleaner NLI
        clean_sentence = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', sentence).strip()
        if not clean_sentence:
            return True, 1.0, "Empty claim after removing citations"
        
        # Check against each cited source
        best_score = 0.0
        best_reason = "Not supported by any cited source"
        any_supported = False
        
        for source_id in cited_sources:
            if source_id not in passages:
                logger.warning(f"Source {source_id} not found in passages")
                continue
            
            passage = passages[source_id]
            if not passage:
                continue
            
            supported, confidence, reason = self._nli_check(passage, clean_sentence)
            
            if supported and confidence > best_score:
                best_score = confidence
                best_reason = f"Supported by source [{source_id}]: {reason}"
                any_supported = True
        
        return any_supported, best_score, best_reason
    
    def _nli_check(self, document: str, claim: str) -> Tuple[bool, float, str]:
        """
        Check if claim is entailed by document using LLM.
        
        Returns: (is_supported, confidence, reason)
        """
        prompt = f"""You are an NLI (Natural Language Inference) evaluator.

Given a DOCUMENT and a CLAIM, determine if the claim is SUPPORTED by the document.
A claim is SUPPORTED if the document contains information that directly entails the claim.
A claim is NOT SUPPORTED if the document contradicts it OR doesn't contain relevant information.

DOCUMENT:
{document[:4000]}

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
            
            # Parse JSON with safe handling of LLM errors
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            result = safe_json_loads(content)
            return (
                result.get("supported", False),
                result.get("confidence", 0.5),
                result.get("reason", "")
            )
        except Exception as e:
            logger.warning(f"NLI check failed: {e}")
            return False, 0.0, f"Error: {str(e)}"
    
    def verify(
        self,
        answer: str,
        passages: Dict[int, str],
        citations: Optional[List[Dict]] = None
    ) -> VerificationResult:
        """
        Verify all claims in the answer against source documents.
        
        Args:
            answer: Generated answer with [N] citation markers
            passages: Dict mapping source ID (1-indexed) to passage text
            citations: Optional list of citation metadata
            
        Returns:
            VerificationResult with verified answer and statistics
        """
        # Extract sentences with citations
        sentences = self._extract_sentences_with_citations(answer)
        
        if not sentences:
            logger.info("No sentences with citations found")
            return VerificationResult(
                original_answer=answer,
                verified_answer=answer,
                total_sentences=0,
                verified_sentences=0,
                removed_sentences=0,
                verification_rate=1.0
            )
        
        # Verify each sentence
        verified_sentences = []
        
        for sent_text, cited_sources, idx in sentences:
            is_verified, score, reason = self._verify_sentence_against_passages(
                sent_text, passages, cited_sources
            )
            
            vs = VerifiedSentence(
                text=sent_text,
                citations=cited_sources,
                is_verified=is_verified or score >= self.verification_threshold,
                verification_score=score,
                verification_reason=reason,
                original_index=idx
            )
            verified_sentences.append(vs)
        
        # Count verified vs removed
        num_verified = sum(1 for vs in verified_sentences if vs.is_verified)
        num_removed = len(verified_sentences) - num_verified
        
        # Reconstruct answer
        if self.remove_unverified:
            verified_answer = self._reconstruct_answer(answer, verified_sentences)
        else:
            verified_answer = self._flag_unverified(answer, verified_sentences)
        
        verification_rate = num_verified / len(verified_sentences) if verified_sentences else 1.0
        
        logger.info(
            f"Post-hoc verification: {num_verified}/{len(verified_sentences)} sentences verified "
            f"({verification_rate:.1%}), {num_removed} removed"
        )
        
        return VerificationResult(
            original_answer=answer,
            verified_answer=verified_answer,
            total_sentences=len(verified_sentences),
            verified_sentences=num_verified,
            removed_sentences=num_removed,
            verification_rate=verification_rate,
            sentence_details=verified_sentences
        )
    
    def _reconstruct_answer(
        self,
        original: str,
        verified_sentences: List[VerifiedSentence]
    ) -> str:
        """
        Reconstruct answer keeping only verified sentences.
        
        Preserves headers and structure, removes unverified claims.
        """
        result = original
        
        # Sort by original position (reverse to avoid index shifting)
        unverified = [vs for vs in verified_sentences if not vs.is_verified]
        unverified.sort(key=lambda x: x.original_index, reverse=True)
        
        for vs in unverified:
            # Find and remove the unverified sentence
            # Use a more careful approach to avoid breaking structure
            sent_pattern = re.escape(vs.text)
            # Remove sentence and trailing space/newline
            result = re.sub(sent_pattern + r'\s*', '', result)
        
        # Clean up any double spaces or empty lines
        result = re.sub(r'\n{3,}', '\n\n', result)
        result = re.sub(r' {2,}', ' ', result)
        
        return result.strip()
    
    def _flag_unverified(
        self,
        original: str,
        verified_sentences: List[VerifiedSentence]
    ) -> str:
        """
        Flag unverified sentences with [UNVERIFIED] marker.
        """
        result = original
        
        for vs in verified_sentences:
            if not vs.is_verified:
                # Add marker before the sentence
                result = result.replace(
                    vs.text,
                    f"[⚠️ UNVERIFIED] {vs.text}"
                )
        
        return result


async def verify_answer(
    answer: str,
    citations: List[Dict],
    contexts: Optional[List[str]] = None,
    remove_unverified: bool = True,
    threshold: float = 0.5
) -> VerificationResult:
    """
    Convenience function to verify an answer.
    
    Args:
        answer: Generated answer with citations
        citations: List of citation dicts with 'snippet' or 'full_text'
        contexts: Optional fallback context strings
        remove_unverified: Remove unverified sentences vs flagging
        threshold: Verification confidence threshold
        
    Returns:
        VerificationResult
    """
    # Build passage lookup
    passages = {}
    for i, citation in enumerate(citations, 1):
        # Prefer full_text, fallback to snippet
        text = citation.get('full_text') or citation.get('snippet', '')
        if text:
            passages[i] = text
    
    # Fallback to contexts if no passages from citations
    if not passages and contexts:
        for i, ctx in enumerate(contexts, 1):
            if ctx:
                passages[i] = ctx
    
    verifier = PostHocVerifier(
        remove_unverified=remove_unverified,
        verification_threshold=threshold
    )
    
    return verifier.verify(answer, passages, citations)
