"""
DevChat v2.0 - Structured Answer Synthesizer for Impact Evaluations

Two-pass approach for citation accuracy:
1. First pass: Extract structured evidence from EACH source separately
2. Second pass: Write comprehensive answer using only extracted evidence

Production-ready with:
- Configurable source limits (prevents timeout with large corpus)
- Concurrent LLM calls with semaphore (faster, respects rate limits)
- Graceful error handling and fallbacks
- Request-level timeouts

Designed for Impact Evaluation research, extracting:
- Intervention details
- Outcomes measured  
- Effect sizes and significance
- Study context (location, population, sample size)
- Limitations and caveats

References:
- ALCE benchmark: https://arxiv.org/abs/2305.14627
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
from src.utils.json_utils import extract_json_from_llm_response

logger = get_logger(__name__)


@dataclass
class StudyEvidence:
    """Structured evidence extracted from a single study."""
    source_id: int  # 1-indexed citation number
    title: str
    
    # Core IE elements
    intervention: str  # What was the intervention/program?
    comparison: str  # What was it compared to? (control, alternative)
    outcomes: List[str]  # What outcomes were measured?
    
    # Findings
    key_findings: List[Dict]  # [{outcome, effect, direction, significance}]
    effect_sizes: List[str]  # Quantitative effects if mentioned
    
    # Context
    location: str  # Country/region
    population: str  # Target population
    sample_size: str  # N if mentioned
    study_design: str  # RCT, quasi-experimental, etc.
    
    # Quality/Caveats
    limitations: List[str]
    
    def has_quantitative_findings(self) -> bool:
        """Check if study has effect sizes."""
        return len(self.effect_sizes) > 0


@dataclass
class ClaimLedger:
    """Comprehensive evidence mapping from all sources."""
    query: str
    sources: List[Dict]  # Original citations
    evidence: List[StudyEvidence] = field(default_factory=list)
    
    def to_context_for_writing(self) -> str:
        """Format extracted evidence as context for writing pass."""
        if not self.evidence:
            return "No structured evidence could be extracted from the sources."
        
        lines = ["## Extracted Evidence from Studies\n"]
        
        for study in self.evidence:
            lines.append(f"\n### [{study.source_id}] {study.title}\n")
            
            # Intervention & comparison
            if study.intervention:
                lines.append(f"**Intervention:** {study.intervention}")
            if study.comparison:
                lines.append(f"**Comparison:** {study.comparison}")
            
            # Context
            context_parts = []
            if study.location:
                context_parts.append(f"Location: {study.location}")
            if study.population:
                context_parts.append(f"Population: {study.population}")
            if study.sample_size:
                context_parts.append(f"N={study.sample_size}")
            if study.study_design:
                context_parts.append(f"Design: {study.study_design}")
            if context_parts:
                lines.append(f"**Context:** {'; '.join(context_parts)}")
            
            # Outcomes
            if study.outcomes:
                lines.append(f"**Outcomes measured:** {', '.join(study.outcomes)}")
            
            # Key findings
            if study.key_findings:
                lines.append("**Key findings:**")
                for finding in study.key_findings:
                    outcome = finding.get('outcome', 'Unknown')
                    effect = finding.get('effect', '')
                    direction = finding.get('direction', '')
                    sig = finding.get('significance', '')
                    finding_str = f"  - {outcome}: {direction}"
                    if effect:
                        finding_str += f" ({effect})"
                    if sig:
                        finding_str += f" [{sig}]"
                    lines.append(finding_str)
            
            # Effect sizes
            if study.effect_sizes:
                lines.append("**Effect sizes:**")
                for es in study.effect_sizes:
                    lines.append(f"  - {es}")
            
            # Limitations
            if study.limitations:
                lines.append(f"**Limitations:** {'; '.join(study.limitations)}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def get_sources_with_claims(self) -> List[int]:
        """Get source IDs that have extracted evidence."""
        return [e.source_id for e in self.evidence]


class StructuredSynthesizer:
    """
    Two-pass synthesizer for accurate citations.
    
    Pass 1: Extract claims from each source relevant to query
    Pass 2: Write answer using only extracted claims
    
    Production features:
    - Configurable max sources (settings.max_sources_for_extraction)
    - Concurrent LLM calls (settings.llm_concurrency_limit)
    - Timeout handling per extraction
    """
    
    def __init__(self, llm=None):
        self.llm = llm
        self._setup_llm()
        # Semaphore for concurrent LLM calls
        self._llm_semaphore = asyncio.Semaphore(settings.llm_concurrency_limit)
    
    def _setup_llm(self):
        """Initialize LLM using OpenRouter via OpenAI-like interface."""
        if self.llm is None:
            try:
                from llama_index.llms.openai_like import OpenAILike
                
                # Use GPT-4o-mini via OpenRouter for claim extraction
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
                logger.info("StructuredSynthesizer LLM initialized successfully")
            except ImportError as e:
                logger.error(f"Failed to import OpenAILike: {e}")
                logger.error("Run: pip install llama-index-llms-openai-like")
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}")
    
    async def synthesize(
        self,
        query: QueryClassification,
        context: FormattedContext,
    ) -> Tuple[str, ClaimLedger]:
        """
        Generate answer with verified citations.
        
        Returns:
            Tuple of (answer text, claim ledger for verification)
        """
        # Pass 1: Extract structured evidence from each source
        ledger = await self._extract_evidence_from_sources(
            query=query.original_query,
            context_text=context.text,
            citations=context.citations,
        )
        
        # Pass 2: Write comprehensive answer using extracted evidence
        answer = await self._write_answer_from_evidence(
            query=query.original_query,
            ledger=ledger,
            num_sources=context.num_studies,
        )
        
        return answer, ledger
    
    async def _extract_evidence_from_sources(
        self,
        query: str,
        context_text: str,
        citations: List[Dict],
    ) -> ClaimLedger:
        """
        Pass 1: Extract structured evidence from sources with production limits.
        
        Features:
        - Limits sources to settings.max_sources_for_extraction (default 8)
        - Runs extractions concurrently with semaphore
        - Graceful timeout handling per source
        """
        ledger = ClaimLedger(query=query, sources=citations)
        
        # Apply source limit for production scaling
        max_sources = min(len(citations), settings.max_sources_for_extraction)
        if len(citations) > max_sources:
            logger.info(
                f"Limiting source extraction from {len(citations)} to {max_sources} "
                f"(settings.max_sources_for_extraction={settings.max_sources_for_extraction})"
            )
        
        # Parse context to separate sources
        source_sections = self._split_context_by_source(context_text, len(citations))
        
        # Prepare extraction tasks (limited to max_sources)
        async def extract_with_semaphore(source_id: int, source_text: str, title: str) -> Optional[StudyEvidence]:
            """Extract with concurrency control and timeout."""
            async with self._llm_semaphore:
                try:
                    # Timeout per extraction (30 seconds)
                    return await asyncio.wait_for(
                        self._extract_single_source(
                            source_id=source_id,
                            source_text=source_text,
                            title=title,
                            query=query,
                        ),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Extraction timeout for source {source_id}: {title[:50]}...")
                    return None
                except Exception as e:
                    logger.error(f"Extraction error for source {source_id}: {e}")
                    return None
        
        # Create concurrent tasks for limited sources
        tasks = []
        for source_id, (source_text, citation) in enumerate(
            zip(source_sections[:max_sources], citations[:max_sources]), 1
        ):
            if not source_text.strip():
                continue
            title = citation.get('title', f'Study {source_id}')
            tasks.append(extract_with_semaphore(source_id, source_text, title))
        
        # Run all extractions concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, StudyEvidence):
                    ledger.evidence.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"Extraction task failed: {result}")
        
        # Log which sources we got evidence from
        sources_covered = ledger.get_sources_with_claims()
        logger.info(
            f"Extracted evidence from {len(sources_covered)}/{len(citations)} sources "
            f"(processed {max_sources}, succeeded {len(sources_covered)}): {sources_covered}"
        )
        
        return ledger
    
    def _split_context_by_source(self, context_text: str, num_sources: int) -> List[str]:
        """Split formatted context back into per-source sections."""
        sections = []
        
        # Context builder uses "---" to separate studies, try that first
        if '\n---\n' in context_text or '\n\n---\n\n' in context_text:
            sections = [s.strip() for s in re.split(r'\n+---\n+', context_text) if s.strip()]
        else:
            # Try to split by source markers [1], [2], etc.
            # Context format uses: [N] **Title** (Year)
            pattern = r'\[(\d+)\]\s*\*\*'
            matches = list(re.finditer(pattern, context_text))
            
            if matches:
                for i, match in enumerate(matches):
                    start = match.start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(context_text)
                    sections.append(context_text[start:end].strip())
            else:
                # Last fallback: treat entire text as one section
                sections = [context_text.strip()]
        
        # Log what we found
        logger.debug(f"Split context into {len(sections)} sections (expected {num_sources})")
        
        # Pad with empty strings if needed
        while len(sections) < num_sources:
            sections.append("")
        
        return sections[:num_sources]
    
    async def _extract_single_source(
        self,
        source_id: int,
        source_text: str,
        title: str,
        query: str,
    ) -> Optional[StudyEvidence]:
        """Extract structured evidence from a single source."""
        
        prompt = f"""You are an expert at analyzing impact evaluation research. 
Extract structured information from this study relevant to the user's question.

USER QUESTION: {query}

STUDY TEXT:
{source_text[:6000]}

Extract the following information (use "Not stated" if not mentioned):

Return as JSON:
{{
    "intervention": "What program/policy/treatment was tested?",
    "comparison": "What was it compared to? (control group, alternative, nothing)",
    "outcomes": ["List of outcomes measured"],
    "key_findings": [
        {{
            "outcome": "specific outcome",
            "direction": "positive/negative/no effect/mixed",
            "effect": "effect size or magnitude (e.g., '15% increase', '0.3 SD')",
            "significance": "statistically significant/not significant/p<0.05"
        }}
    ],
    "effect_sizes": ["List any quantitative effect sizes mentioned"],
    "location": "Country or region",
    "population": "Target population (e.g., 'poor rural households', 'school-age children')",
    "sample_size": "Sample size N if mentioned",
    "study_design": "RCT/quasi-experimental/difference-in-differences/etc.",
    "limitations": ["Any stated limitations or caveats"]
}}

IMPORTANT:
- Extract ONLY what is explicitly stated in the text
- Include specific numbers and effect sizes when mentioned
- For key_findings, focus on findings relevant to the user's question
- If something is not mentioned, use "Not stated"

Return ONLY the JSON, no other text."""

        try:
            response = await self.llm.acomplete(prompt)
            text = response.text.strip()
            
            # Parse JSON with automatic fixing of LLM errors
            data = extract_json_from_llm_response(text)
            
            return StudyEvidence(
                source_id=source_id,
                title=title,
                intervention=data.get('intervention', 'Not stated'),
                comparison=data.get('comparison', 'Not stated'),
                outcomes=data.get('outcomes', []),
                key_findings=data.get('key_findings', []),
                effect_sizes=data.get('effect_sizes', []),
                location=data.get('location', 'Not stated'),
                population=data.get('population', 'Not stated'),
                sample_size=data.get('sample_size', 'Not stated'),
                study_design=data.get('study_design', 'Not stated'),
                limitations=data.get('limitations', []),
            )
            
        except Exception as e:
            logger.error(f"Failed to extract from source {source_id}: {e}")
            return None
    
    async def _write_answer_from_evidence(
        self,
        query: str,
        ledger: ClaimLedger,
        num_sources: int,
    ) -> str:
        """
        Pass 2: Write comprehensive answer using extracted evidence.
        
        Structures the answer appropriately for impact evaluation research:
        - Summary of what we found
        - Interventions examined
        - Key findings by outcome
        - Effect sizes where available
        - Context and limitations
        """
        evidence_context = ledger.to_context_for_writing()
        sources_covered = len(ledger.get_sources_with_claims())
        
        prompt = f"""You are a research assistant helping users explore impact evaluation evidence.

USER QUESTION: {query}

I found {num_sources} studies, and extracted detailed evidence from {sources_covered} of them:

{evidence_context}

Write a COMPREHENSIVE answer that:

1. **Opening**: Start with "I found {num_sources} studies relevant to your question about {query}."

2. **Overview of Studies**: Briefly describe what interventions were examined and in what contexts
   - What programs/policies were tested?
   - Where and with whom?
   - What study designs were used?

3. **Key Findings**: Present the main findings organized by outcome or theme
   - What effects were found?
   - Include specific effect sizes when available (e.g., "15% increase", "0.3 standard deviations")
   - Note direction and statistical significance
   - Cite each finding with [1], [2], etc.

4. **Comparison/Synthesis**: If multiple studies, compare findings
   - Do studies agree or disagree?
   - Are effects consistent across contexts?

5. **Caveats**: Note important limitations
   - These are specific studies, not a comprehensive review
   - Any stated limitations from the studies themselves

IMPORTANT FORMATTING RULES:
- Every factual statement MUST have a citation [N] 
- Use markdown formatting (headers, bullets, bold) for readability
- Include SPECIFIC numbers and effect sizes - don't just say "positive effect"
- EVERY source number mentioned in the evidence MUST appear in your citations
- If a study is [1] and [2], both must be cited at least once
- Do NOT include a References section at the end (that will be added separately)

Write a substantive, informative answer (aim for 300-500 words):"""

        try:
            response = await self.llm.acomplete(prompt)
            answer = response.text.strip()
            
            # Remove any auto-generated references section
            # Split on common reference section markers and keep only the first part
            ref_markers = [
                '\n---\n\n## References',
                '\n---\n\n**References',
                '\n\n---\n\n## References',
                '\n\n## References',
                '\n\n**References**',
                '\n\n**Sources**',
                '\n---\n\n- ',  # Catch pattern like "---" followed by bullet list
            ]
            
            for marker in ref_markers:
                if marker in answer:
                    answer = answer.split(marker)[0].strip()
                    logger.debug(f"Removed references section at marker: {marker[:20]}...")
                    break
            
            # Verify all sources are cited
            answer = self._ensure_all_sources_cited(answer, ledger)
            
            return answer
            
        except Exception as e:
            logger.error(f"Answer writing failed: {e}")
            return f"I found {num_sources} studies but encountered an error generating the answer."
    
    def _ensure_all_sources_cited(self, answer: str, ledger: ClaimLedger) -> str:
        """Ensure all sources with evidence are cited at least once."""
        sources_with_evidence = ledger.get_sources_with_claims()
        
        # Find which sources are cited
        cited_pattern = r'\[(\d+)\]'
        cited = set(int(m) for m in re.findall(cited_pattern, answer))
        
        # Check for missing
        missing = [s for s in sources_with_evidence if s not in cited]
        
        if missing and ledger.evidence:
            # Add a note about uncited sources
            uncited_studies = []
            for evidence in ledger.evidence:
                if evidence.source_id in missing:
                    uncited_studies.append(f"[{evidence.source_id}] {evidence.title}")
            
            if uncited_studies:
                addition = "\n\n**Additional relevant studies**: " + ", ".join(uncited_studies)
                answer += addition
                logger.warning(f"Added {len(missing)} uncited sources to answer: {missing}")
        
        return answer


async def verify_citations_post_hoc(
    answer: str,
    contexts: List[str],
    llm=None,
) -> Dict:
    """
    ALCE-style post-hoc verification of citations.
    
    Checks each cited claim against its source to verify support.
    
    Returns:
        Dict with verification results and accuracy score
    """
    if llm is None:
        from llama_index.llms.openrouter import OpenRouter
        llm = OpenRouter(
            model="openai/gpt-4o-mini",
            api_key=settings.openrouter_api_key,
        )
    
    # Extract sentences with citations
    citation_pattern = r'([^.!?]*\[(\d+(?:,\s*\d+)*)\][^.!?]*[.!?])'
    matches = re.findall(citation_pattern, answer)
    
    if not matches:
        return {
            'verified': 0,
            'total': 0,
            'accuracy': 0.0,
            'details': [],
        }
    
    results = []
    verified_count = 0
    
    for sentence, citation_nums in matches:
        # Parse citation numbers
        nums = [int(n.strip()) for n in citation_nums.split(',')]
        
        # Get cited contexts
        cited_contexts = []
        for n in nums:
            if 1 <= n <= len(contexts):
                cited_contexts.append(f"[{n}]: {contexts[n-1]}")
        
        if not cited_contexts:
            results.append({
                'sentence': sentence.strip(),
                'citations': nums,
                'verified': False,
                'reason': 'Invalid citation number',
            })
            continue
        
        # Verify with LLM
        verify_prompt = f"""Does the following sentence accurately represent information from the cited sources?

SENTENCE: {sentence.strip()}

CITED SOURCES:
{chr(10).join(cited_contexts)}

Answer "SUPPORTED" if the sentence is accurate based on the sources.
Answer "NOT SUPPORTED" if the sentence makes claims not found in or contradicting the sources.
Answer "PARTIALLY" if some parts are supported but others are not.

Then briefly explain why.

Format: VERDICT: [explanation]"""

        try:
            response = await llm.acomplete(verify_prompt)
            response_text = response.text.strip()
            
            if response_text.startswith('SUPPORTED'):
                verified = True
                verified_count += 1
            elif response_text.startswith('PARTIALLY'):
                verified = True  # Count partial as verified
                verified_count += 0.5
            else:
                verified = False
            
            results.append({
                'sentence': sentence.strip(),
                'citations': nums,
                'verified': verified,
                'reason': response_text,
            })
            
        except Exception as e:
            results.append({
                'sentence': sentence.strip(),
                'citations': nums,
                'verified': False,
                'reason': f'Verification failed: {e}',
            })
    
    total = len(matches)
    accuracy = verified_count / total if total > 0 else 0.0
    
    return {
        'verified': int(verified_count),
        'total': total,
        'accuracy': round(accuracy, 3),
        'details': results,
    }


if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test the structured synthesizer
        from src.retrieval.context_builder import FormattedContext
        from src.retrieval.query_processor import QueryClassification, QueryType
        
        synth = StructuredSynthesizer()
        
        # Mock data
        query = QueryClassification(
            original_query="What is the impact of cash transfers on poverty?",
            primary_query="cash transfers poverty impact",
            query_type=QueryType.SYNTHESIS,
        )
        
        context = FormattedContext(
            text="""[1] **Cash Transfer Study** (2020)
The randomized controlled trial found that cash transfers reduced poverty rates by 15% among recipient households. Monthly income increased from $50 to $75 on average.

---

[2] **Bangladesh Income Study** (2018)
Research in Bangladesh showed 20% increase in household income after cash transfers. The program particularly benefited female-headed households, showing 30% greater improvements.""",
            num_chunks=2,
            num_studies=2,
            citations=[
                {"study_id": "study1", "title": "Cash Transfer Study", "year": 2020},
                {"study_id": "study2", "title": "Bangladesh Income Study", "year": 2018},
            ],
        )
        
        answer, ledger = await synth.synthesize(query, context)
        
        print("=== CLAIM LEDGER ===")
        for claim in ledger.claims:
            print(f"[{claim.source_id}] {claim.claim}")
            print(f"    Quote: {claim.quote[:100]}...")
        
        print("\n=== GENERATED ANSWER ===")
        print(answer)
        
        # Verify citations
        print("\n=== POST-HOC VERIFICATION ===")
        contexts = [
            "The randomized controlled trial found that cash transfers reduced poverty rates by 15% among recipient households. Monthly income increased from $50 to $75 on average.",
            "Research in Bangladesh showed 20% increase in household income after cash transfers. The program particularly benefited female-headed households, showing 30% greater improvements.",
        ]
        verification = await verify_citations_post_hoc(answer, contexts)
        print(json.dumps(verification, indent=2))
    
    asyncio.run(test())
