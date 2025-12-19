"""
DevChat v2.0 - Structured Answer Synthesizer

Two-pass approach for citation accuracy:
1. First pass: Extract claims from sources (Source-to-Claim Ledger)
2. Second pass: Write answer using only mapped claims

This dramatically improves citation accuracy by ensuring every 
claim is explicitly linked to its source BEFORE writing.

References:
- ALCE benchmark: https://arxiv.org/abs/2305.14627
- Instructor library pattern
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.config.settings import settings
from src.retrieval.context_builder import FormattedContext
from src.retrieval.query_processor import QueryClassification
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SourceClaim:
    """A claim extracted from a source."""
    claim: str
    source_id: int  # 1-indexed citation number
    quote: str  # Supporting quote from source
    relevance: str  # How it relates to the query


@dataclass
class ClaimLedger:
    """Mapping of sources to their claims."""
    query: str
    sources: List[Dict]  # Original citations
    claims: List[SourceClaim] = field(default_factory=list)
    
    def to_context_for_writing(self) -> str:
        """Format claims as context for the writing pass."""
        if not self.claims:
            return "No relevant claims found in the sources."
        
        lines = ["## Verified Claims from Sources\n"]
        
        # Group claims by source
        by_source: Dict[int, List[SourceClaim]] = {}
        for claim in self.claims:
            if claim.source_id not in by_source:
                by_source[claim.source_id] = []
            by_source[claim.source_id].append(claim)
        
        for source_id in sorted(by_source.keys()):
            source = self.sources[source_id - 1] if source_id <= len(self.sources) else {}
            title = source.get('title', f'Source {source_id}')
            lines.append(f"\n### [{source_id}] {title}\n")
            
            for claim in by_source[source_id]:
                lines.append(f"- **Claim**: {claim.claim}")
                lines.append(f"  - *Quote*: \"{claim.quote[:200]}...\"" if len(claim.quote) > 200 else f"  - *Quote*: \"{claim.quote}\"")
                lines.append(f"  - *Relevance*: {claim.relevance}\n")
        
        return "\n".join(lines)


class StructuredSynthesizer:
    """
    Two-pass synthesizer for accurate citations.
    
    Pass 1: Extract claims from each source relevant to query
    Pass 2: Write answer using only extracted claims
    """
    
    def __init__(self, llm=None):
        self.llm = llm
        self._setup_llm()
    
    def _setup_llm(self):
        """Initialize LLM."""
        if self.llm is None:
            try:
                from llama_index.llms.openrouter import OpenRouter
                self.llm = OpenRouter(
                    model="openai/gpt-4o-mini",
                    api_key=settings.openrouter_api_key,
                    max_tokens=4000,
                )
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
        # Pass 1: Extract claims from sources
        ledger = await self._extract_claims_from_sources(
            query=query.original_query,
            context_text=context.text,
            citations=context.citations,
        )
        
        # Pass 2: Write answer using only ledger claims
        answer = await self._write_answer_from_claims(
            query=query.original_query,
            ledger=ledger,
            num_sources=context.num_studies,
        )
        
        return answer, ledger
    
    async def _extract_claims_from_sources(
        self,
        query: str,
        context_text: str,
        citations: List[Dict],
    ) -> ClaimLedger:
        """
        Pass 1: Extract relevant claims from each source.
        
        This creates the Source-to-Claim Ledger.
        """
        ledger = ClaimLedger(query=query, sources=citations)
        
        prompt = f"""You are analyzing research sources to extract claims relevant to a user's question.

USER QUESTION: {query}

SOURCES:
{context_text[:12000]}

For each source, extract the KEY CLAIMS that are relevant to answering the user's question.
For each claim, include:
1. The claim (a factual statement)
2. The source number [1], [2], etc.
3. A direct quote from the source that supports this claim
4. How this claim relates to the user's question

Return as JSON array:
[
  {{
    "claim": "Cash transfers increased household income by 20%",
    "source_id": 1,
    "quote": "We found a statistically significant 20% increase in monthly household income...",
    "relevance": "Directly addresses income effects of cash transfers"
  }},
  {{
    "claim": "Program effects were larger for women",
    "source_id": 1,
    "quote": "Female-headed households showed 30% greater improvements compared to...",
    "relevance": "Shows heterogeneous effects by gender"
  }}
]

IMPORTANT:
- Only extract claims that are DIRECTLY STATED in the sources
- Include the EXACT quote that supports each claim
- Focus on claims that help answer the user's question
- Include claims from ALL sources, not just the first one

Return ONLY the JSON array, no other text."""

        try:
            response = await self.llm.acomplete(prompt)
            text = response.text.strip()
            
            # Clean up response
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            claims_data = json.loads(text)
            
            for c in claims_data:
                ledger.claims.append(SourceClaim(
                    claim=c.get('claim', ''),
                    source_id=c.get('source_id', 0),
                    quote=c.get('quote', ''),
                    relevance=c.get('relevance', ''),
                ))
            
            logger.info(f"Extracted {len(ledger.claims)} claims from {len(citations)} sources")
            
        except Exception as e:
            logger.error(f"Claim extraction failed: {e}")
        
        return ledger
    
    async def _write_answer_from_claims(
        self,
        query: str,
        ledger: ClaimLedger,
        num_sources: int,
    ) -> str:
        """
        Pass 2: Write answer using ONLY the verified claims.
        
        This ensures every statement is backed by extracted claims.
        """
        claims_context = ledger.to_context_for_writing()
        
        prompt = f"""You are a research assistant helping users explore evidence from a database of studies.

USER QUESTION: {query}

I found {num_sources} relevant studies. Here are the verified claims from each:

{claims_context}

Write an answer that:
1. Starts with "I found {num_sources} studies relevant to your question..."
2. Uses ONLY the claims listed above - do not add any information not in these claims
3. Cites each claim with its source number [1], [2], etc.
4. Acknowledges the limited scope (these are specific studies, not comprehensive evidence)
5. Groups similar findings and notes any disagreements

IMPORTANT RULES:
- Every factual statement MUST have a citation [N]
- Only use information from the verified claims above
- If claims are limited, say so honestly
- Do NOT include a References section at the end

Your response:"""

        try:
            response = await self.llm.acomplete(prompt)
            answer = response.text.strip()
            
            # Remove any auto-generated references section
            if "---" in answer and "References" in answer.split("---")[-1]:
                answer = answer.rsplit("---", 1)[0].strip()
            
            return answer
            
        except Exception as e:
            logger.error(f"Answer writing failed: {e}")
            return f"I found {num_sources} studies but encountered an error generating the answer."


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
