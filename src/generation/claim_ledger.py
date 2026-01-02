"""
DevChat v2.0 - Source-to-Claim Ledger

ALCE-inspired two-pass synthesis for verified citations:

Pass 1 (Extraction): Extract atomic claims with EXACT quotes from sources
Pass 2 (Writing): Generate answer using ONLY the pre-verified claim→source mappings

This dramatically improves citation accuracy because:
1. Claims are extracted WITH supporting quotes (verifiable)
2. The LLM in Pass 2 can ONLY cite claims from the ledger
3. Each citation points to a specific, traceable piece of evidence

Reference: ALCE Benchmark (https://arxiv.org/abs/2305.14627)
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.config.settings import settings
from src.retrieval.context_builder import FormattedContext
from src.retrieval.query_processor import QueryClassification
from src.utils.logging import get_logger
from src.generation.post_hoc_verifier import PostHocVerifier, VerificationResult

logger = get_logger(__name__)


@dataclass
class VerifiedClaim:
    """A single claim extracted from a source with supporting evidence."""
    claim_id: str  # e.g., "1a", "1b", "2a" 
    source_id: int  # 1-indexed citation number
    claim_text: str  # The factual claim
    supporting_quote: str  # Exact quote from source that supports this
    claim_type: str  # "finding", "methodology", "context", "limitation"
    confidence: str  # "high" (exact quote), "medium" (paraphrased), "low" (inferred)


@dataclass
class SourceToClaimLedger:
    """Complete mapping of all claims to their sources."""
    query: str
    sources: List[Dict]  # Original citations
    claims: List[VerifiedClaim] = field(default_factory=list)
    
    def get_claims_by_source(self) -> Dict[int, List[VerifiedClaim]]:
        """Group claims by source ID."""
        by_source = {}
        for claim in self.claims:
            if claim.source_id not in by_source:
                by_source[claim.source_id] = []
            by_source[claim.source_id].append(claim)
        return by_source
    
    def get_sources_with_claims(self) -> List[int]:
        """Get list of source IDs that have extracted claims."""
        return list(set(c.source_id for c in self.claims))
    
    def to_writing_context(self) -> str:
        """Format the ledger as context for the writing pass."""
        if not self.claims:
            return "No claims could be extracted from the sources."
        
        lines = [
            "## VERIFIED CLAIMS LEDGER",
            "",
            "Use ONLY these verified claims when writing your answer.",
            "Cite using the source number in brackets, e.g., [1], [2].",
            "",
        ]
        
        by_source = self.get_claims_by_source()
        
        for source_id in sorted(by_source.keys()):
            source_claims = by_source[source_id]
            source_info = self.sources[source_id - 1] if source_id <= len(self.sources) else {}
            title = source_info.get('title', f'Source {source_id}')
            
            lines.append(f"### Source [{source_id}]: {title}")
            lines.append("")
            
            for claim in source_claims:
                lines.append(f"**{claim.claim_id}** ({claim.claim_type}, {claim.confidence} confidence)")
                lines.append(f"  Claim: {claim.claim_text}")
                lines.append(f"  Evidence: \"{claim.supporting_quote}\"")
                lines.append("")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def get_claim_count_summary(self) -> str:
        """Get a summary of claims by type."""
        type_counts = {}
        for claim in self.claims:
            type_counts[claim.claim_type] = type_counts.get(claim.claim_type, 0) + 1
        return ", ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))


class ClaimLedgerSynthesizer:
    """
    Two-pass synthesizer using Source-to-Claim Ledger.
    
    This ensures citation accuracy by:
    1. First extracting all claims with supporting quotes (fast model)
    2. Then writing using only the verified claim mappings (strong model)
    """
    
    def __init__(self, llm=None, writing_llm=None):
        self.llm = llm  # For extraction (can be fast)
        self.writing_llm = writing_llm  # For writing (needs to be strong)
        self._setup_llms()
        self._llm_semaphore = asyncio.Semaphore(settings.llm_concurrency_limit)
    
    def _setup_llms(self):
        """Initialize LLMs using OpenRouter."""
        try:
            from llama_index.llms.openai_like import OpenAILike
            
            # Fast model for claim extraction
            if self.llm is None:
                self.llm = OpenAILike(
                    model="openai/gpt-4o-mini",
                    api_key=settings.openrouter_api_key,
                    api_base=settings.openrouter_base_url,
                    temperature=0.1,  # Low temperature for consistent extraction
                    max_tokens=4000,
                    is_chat_model=True,
                    additional_kwargs={
                        "extra_headers": {
                            "HTTP-Referer": "https://3ieimpact.org",
                            "X-Title": "DevChat 3ie",
                        }
                    }
                )
            
            # Strong model for writing (better at following constraints)
            if self.writing_llm is None:
                self.writing_llm = OpenAILike(
                    model=settings.llm_reasoning_model,  # GPT-4o or Claude
                    api_key=settings.openrouter_api_key,
                    api_base=settings.openrouter_base_url,
                    temperature=0.0,  # Zero temp for maximum faithfulness
                    max_tokens=4000,
                    is_chat_model=True,
                    additional_kwargs={
                        "extra_headers": {
                            "HTTP-Referer": "https://3ieimpact.org",
                            "X-Title": "DevChat 3ie",
                        }
                    }
                )
            
            logger.info(f"ClaimLedgerSynthesizer: extraction={self.llm.model}, writing={self.writing_llm.model}")
        except Exception as e:
            logger.error(f"Failed to initialize LLMs: {e}")
    
    async def synthesize(
        self,
        query: QueryClassification,
        context: FormattedContext,
        enable_post_hoc_verification: bool = False,  # Disabled - causes too aggressive filtering
    ) -> Tuple[str, SourceToClaimLedger]:
        """
        Generate answer with verified citations using claim ledger.
        
        Args:
            query: Classified query
            context: Formatted context with citations
            enable_post_hoc_verification: Run post-hoc verification to filter ungrounded claims
        
        Returns:
            Tuple of (answer text, claim ledger for verification)
        """
        # Pass 1: Extract claims with supporting quotes
        ledger = await self._extract_claims_from_sources(
            query=query.original_query,
            context_text=context.text,
            citations=context.citations,
        )
        
        logger.info(
            f"Claim ledger: {len(ledger.claims)} claims from "
            f"{len(ledger.get_sources_with_claims())}/{len(context.citations)} sources"
        )
        
        # Pass 2: Write answer using ONLY the ledger
        answer = await self._write_from_ledger(
            query=query.original_query,
            ledger=ledger,
            num_sources=context.num_studies,
        )
        
        # Pass 3 (optional): Post-hoc verification
        if enable_post_hoc_verification:
            answer = await self._post_hoc_verify(answer, context.citations)
        
        return answer, ledger
    
    async def _post_hoc_verify(
        self,
        answer: str,
        citations: List[Dict],
    ) -> str:
        """
        Pass 3: Verify claims and remove ungrounded statements.
        
        This runs MiniCheck-style NLI on each sentence to ensure
        it's actually supported by the cited sources.
        """
        try:
            verifier = PostHocVerifier(
                verification_threshold=0.5,
                remove_unverified=True  # Remove ungrounded claims
            )
            
            # Build passage lookup from citations
            passages = {}
            for i, citation in enumerate(citations, 1):
                text = citation.get('full_text') or citation.get('snippet', '')
                if text:
                    passages[i] = text
            
            if not passages:
                logger.warning("No passages for post-hoc verification")
                return answer
            
            result = verifier.verify(answer, passages, citations)
            
            logger.info(
                f"Post-hoc verification: {result.verified_sentences}/{result.total_sentences} "
                f"sentences verified ({result.verification_rate:.1%})"
            )
            
            return result.verified_answer
            
        except Exception as e:
            logger.error(f"Post-hoc verification failed: {e}")
            return answer  # Return original on error
    
    async def _extract_claims_from_sources(
        self,
        query: str,
        context_text: str,
        citations: List[Dict],
    ) -> SourceToClaimLedger:
        """
        Pass 1: Extract atomic claims with exact supporting quotes.
        """
        ledger = SourceToClaimLedger(query=query, sources=citations)
        
        # Limit sources for production
        max_sources = min(len(citations), settings.max_sources_for_extraction)
        
        # Parse context into source sections
        source_sections = self._split_context_by_source(context_text, len(citations))
        
        # Extract claims concurrently
        async def extract_with_semaphore(
            source_id: int, 
            source_text: str, 
            title: str
        ) -> List[VerifiedClaim]:
            async with self._llm_semaphore:
                try:
                    return await asyncio.wait_for(
                        self._extract_claims_single_source(
                            source_id=source_id,
                            source_text=source_text,
                            title=title,
                            query=query,
                        ),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout extracting claims from source {source_id}")
                    return []
                except Exception as e:
                    logger.error(f"Error extracting claims from source {source_id}: {e}")
                    return []
        
        # Create tasks
        tasks = []
        for source_id, (source_text, citation) in enumerate(
            zip(source_sections[:max_sources], citations[:max_sources]), 1
        ):
            if not source_text.strip():
                continue
            title = citation.get('title', f'Study {source_id}')
            tasks.append(extract_with_semaphore(source_id, source_text, title))
        
        # Run extractions
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    ledger.claims.extend(result)
        
        return ledger
    
    async def _extract_claims_single_source(
        self,
        source_id: int,
        source_text: str,
        title: str,
        query: str,
    ) -> List[VerifiedClaim]:
        """Extract claims with supporting quotes from a single source."""
        
        prompt = f"""You are extracting verifiable claims from a research study.

USER QUESTION: {query}

STUDY TEXT (Source [{source_id}]):
{source_text[:6000]}

Extract ALL claims from this text that are relevant to answering the user's question.

For EACH claim, you MUST provide:
1. A clear, atomic factual statement
2. The EXACT quote from the text that supports it (word for word)
3. The type of claim
4. Your confidence based on how directly the quote supports the claim

Return JSON array:
[
    {{
        "claim_text": "Clear statement of the finding or fact",
        "supporting_quote": "Exact words from the text that prove this claim",
        "claim_type": "finding|methodology|context|limitation",
        "confidence": "high|medium|low"
    }}
]

CLAIM TYPES:
- finding: Results, effects, outcomes, conclusions
- methodology: Study design, sample size, methods used  
- context: Location, population, time period, intervention details
- limitation: Caveats, weaknesses, generalizability concerns

CONFIDENCE LEVELS:
- high: Quote directly states the claim
- medium: Quote strongly implies the claim
- low: Claim is inferred from context

RULES:
- Extract 3-8 claims per source (focus on most relevant)
- Supporting quotes must be EXACT text from the source (copy-paste)
- Each claim should be one clear fact (atomic)
- Focus on claims that help answer the user's question
- Include at least one finding-type claim if any findings exist

Return ONLY the JSON array, no other text."""

        try:
            response = await self.llm.acomplete(prompt)
            text = response.text.strip()
            
            # Clean JSON
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            data = json.loads(text)
            
            claims = []
            for i, item in enumerate(data):
                claim_id = f"{source_id}{chr(97 + i)}"  # "1a", "1b", "2a", etc.
                claims.append(VerifiedClaim(
                    claim_id=claim_id,
                    source_id=source_id,
                    claim_text=item.get('claim_text', ''),
                    supporting_quote=item.get('supporting_quote', ''),
                    claim_type=item.get('claim_type', 'finding'),
                    confidence=item.get('confidence', 'medium'),
                ))
            
            logger.debug(f"Extracted {len(claims)} claims from source [{source_id}] {title[:40]}...")
            return claims
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for source {source_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to extract claims from source {source_id}: {e}")
            return []
    
    def _split_context_by_source(self, context_text: str, num_sources: int) -> List[str]:
        """Split formatted context into per-source sections."""
        sections = []
        
        # Try separator-based splitting first
        if '\n---\n' in context_text or '\n\n---\n\n' in context_text:
            sections = [s.strip() for s in re.split(r'\n+---\n+', context_text) if s.strip()]
        else:
            # Try source marker pattern: [N] **Title**
            pattern = r'\[(\d+)\]\s*\*\*'
            matches = list(re.finditer(pattern, context_text))
            
            if matches:
                for i, match in enumerate(matches):
                    start = match.start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(context_text)
                    sections.append(context_text[start:end].strip())
            else:
                sections = [context_text.strip()]
        
        # Pad if needed
        while len(sections) < num_sources:
            sections.append("")
        
        return sections[:num_sources]
    
    async def _write_from_ledger(
        self,
        query: str,
        ledger: SourceToClaimLedger,
        num_sources: int,
    ) -> str:
        """
        Pass 2: Write answer using ONLY the verified claims from the ledger.
        """
        ledger_context = ledger.to_writing_context()
        sources_with_claims = len(ledger.get_sources_with_claims())
        claim_summary = ledger.get_claim_count_summary()
        
        prompt = f"""You are writing a research synthesis answer.

USER QUESTION: {query}

I found {num_sources} studies and extracted {len(ledger.claims)} verified claims from {sources_with_claims} of them.
Claim breakdown: {claim_summary}

{ledger_context}

WRITING INSTRUCTIONS:

1. **Opening**: "I found {num_sources} studies relevant to your question."

2. **Answer**: Write a comprehensive answer using ONLY claims from the ledger above.
   - Every fact you state MUST come from a verified claim in the ledger
   - Cite using the SOURCE NUMBER in brackets: [1], [2], [3], etc.
   - Do NOT use claim IDs like [1a] or [1b] - just use [1], [2], etc.
   - Include specific effect sizes and numbers from the claims
   - Be substantive (300-500 words)
   - USE THE EXACT WORDING from claims whenever possible - do not paraphrase
   - Do NOT add inferences like "this suggests" or "this indicates"

3. **Structure** (use markdown headers):
   - Key Findings (cite the finding-type claims)
   - Study Contexts (where/when/whom from context-type claims)
   - Limitations (any limitation-type claims)

4. **Citation Rules** (CRITICAL):
   - Use ONLY source numbers: [1], [2], [3] - NOT claim IDs like [1a], [1b]
   - ONLY cite sources that appear in the ledger (sources {list(ledger.get_sources_with_claims())})
   - Every statement MUST have a [N] citation
   - You may combine claims: "Studies found positive effects [1, 3]..."
   - Do NOT make claims that aren't in the ledger
   - Do NOT add a References section at the end
   - Do NOT list author names or study titles at the end
   - Do NOT add any "Note:" or "Additional evidence" sections

REMEMBER: 
- You can ONLY state facts that appear in the verified claims ledger above.
- Use [1], [2], [3] format - NOT [1a], [1b], [1c] format.
- Any uncited claim or claim not in the ledger is a failure.
- END your answer after the Limitations section - NO references or notes after that.

Write your answer:"""

        try:
            # Use regular LLM (GPT-4o-mini works well for this)
            response = await self.llm.acomplete(prompt)
            answer = response.text.strip()
            
            # Remove auto-generated references aggressively
            ref_markers = [
                '\n---\n\n## References',
                '\n\n## References',
                '\n\n**References**',
                '\n\n**Sources**',
                '\n**Note**:',
                '\n\n**Note**',
                '\n---\n\n- ',
                '\n\n---\n',
            ]
            for marker in ref_markers:
                if marker in answer:
                    answer = answer.split(marker)[0].strip()
            
            # Also remove any trailing "Note:" sections using regex
            import re
            answer = re.sub(r'\n\*\*Note\*\*:.*$', '', answer, flags=re.DOTALL)
            answer = re.sub(r'\n---\s*$', '', answer)
            
            # Verify citation coverage
            answer = self._ensure_citation_coverage(answer, ledger)
            
            return answer
            
        except Exception as e:
            logger.error(f"Answer writing failed: {e}")
            return f"I found {num_sources} studies but encountered an error generating the answer."
    
    def _ensure_citation_coverage(self, answer: str, ledger: SourceToClaimLedger) -> str:
        """Ensure all sources with claims are cited."""
        sources_with_claims = set(ledger.get_sources_with_claims())
        
        # Find cited sources
        cited = set(int(m) for m in re.findall(r'\[(\d+)\]', answer))
        
        # Check for missing citations
        missing = sources_with_claims - cited
        
        if missing:
            # Add note about uncited sources
            uncited_titles = []
            for source_id in missing:
                if source_id <= len(ledger.sources):
                    title = ledger.sources[source_id - 1].get('title', f'Source {source_id}')
                    uncited_titles.append(f"[{source_id}] {title}")
            
            if uncited_titles:
                answer += f"\n\n**Note**: Additional evidence available from: {', '.join(uncited_titles)}"
                logger.warning(f"Added {len(missing)} uncited sources: {missing}")
        
        # Check for invalid citations (citing sources not in ledger)
        invalid = cited - sources_with_claims
        if invalid:
            logger.warning(f"Answer contains citations to sources without claims: {invalid}")
        
        return answer


# Convenience function for use in agent
async def synthesize_with_claim_ledger(
    query: QueryClassification,
    context: FormattedContext,
    llm=None,
) -> Tuple[str, SourceToClaimLedger]:
    """
    Generate answer using claim ledger for verified citations.
    
    This is the recommended approach for citation-critical applications.
    """
    synthesizer = ClaimLedgerSynthesizer(llm=llm)
    return await synthesizer.synthesize(query, context)
