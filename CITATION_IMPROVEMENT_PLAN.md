# Citation Quality Improvement Plan: SOTA Edition v5

**Created:** December 28, 2025  
**Updated:** January 1, 2025 (v5 - Comprehensive Research-Backed Overhaul)  
**Goal:** Achieve near-perfect citation accuracy (Faithfulness 0.70+) using SOTA techniques

---

## Executive Summary

### Current State (After Deduplication Fix v4)

| Metric | Current | Target | Delta | Status |
|--------|---------|--------|-------|--------|
| **Lane A: Faithfulness** | **0.455** | 0.70+ | -0.245 | ❌ **PRIMARY GAP** |
| Lane B: Citation Recall | 0.868 | 0.70 | +0.168 | ✅ Exceeds ALCE |
| Lane B: Citation Precision | 0.869 | 0.70 | +0.169 | ✅ Exceeds ALCE |
| Citation Coverage | 1.00 | 1.00 | 0 | ✅ Perfect |

### Key Insight

**Citation alignment is excellent** - we already exceed ALCE paper benchmarks (GPT-4: ~55-65% precision/recall). The challenge is **faithfulness** - the LLM generates claims that go beyond what's explicitly stated in retrieved chunks.

### Root Causes for Low Faithfulness (0.455)

| Root Cause | Description | Evidence |
|------------|-------------|----------|
| **LLM Over-generalization** | Model makes reasonable inferences but they're not grounded in source text | Claims like "studies show X" when only 2 studies retrieved |
| **Context Quality Issues** | MinerU output has noise: broken tables, garbled OCR, incomplete sentences | Academic PDFs have complex layouts |
| **Chunk Size Mismatch** | 512-token chunks may split evidence across chunks | Claim needs context from multiple locations |
| **Weak Grounding Constraints** | Prompts encourage synthesis but don't strongly constrain to source text | "Summarize the evidence" vs "Quote directly from" |

### Improvement Roadmap (Prioritized)

| Phase | Technique | Effort | Expected Impact | Priority |
|-------|-----------|--------|-----------------|----------|
| 1 | **Strict Grounding Prompts** | 2 hrs | +0.10-0.15 faithfulness | P0 |
| 2 | **Smart MinerU Post-Processing** | 8 hrs | +0.10 faithfulness | P1 |
| 3 | **Structured Output (Instructor)** | 6 hrs | +0.10 faithfulness | P1 |
| 4 | **Post-Hoc Verification Layer** | 6 hrs | +0.05-0.10 faithfulness | P2 |
| 5 | **Contextual Retrieval** | 8 hrs | +0.05 faithfulness | P2 |
| 6 | **Smaller Chunks (256 tokens)** | 4 hrs | +0.05 faithfulness | P3 |

**Target:** Faithfulness ≥ 0.70 with cumulative improvements

---

## Phase 1: Strict Grounding Prompts (P0 - 2 Hours)

### Problem
Current prompts encourage synthesis ("What do the studies show?") but don't constrain the LLM to only make claims explicitly supported by the text.

### Analysis of Current Prompt

```python
# Current synthesis prompt (src/config/prompts.py)
SYNTHESIS_PROMPT = """You are helping a user explore evidence from a research database.

RETRIEVED STUDIES ({num_studies} found):
{context}

USER QUESTION: {query}

IMPORTANT FRAMING:
- You found {num_studies} relevant studies in the database for this query
- These are SPECIFIC STUDIES, not comprehensive coverage of the topic
- Frame your answer as "These studies show..." not "The evidence shows..."
...
"""
```

**Issues:**
1. No explicit instruction to only quote/paraphrase directly
2. No penalty for making unsupported inferences
3. "Key Findings: What do these specific studies show?" encourages interpretation

### Solution: Strict Grounding Prompt

```python
GROUNDED_SYNTHESIS_PROMPT = """You are an AI assistant providing STRICTLY GROUNDED responses based on retrieved documents.

RETRIEVED DOCUMENTS ({num_studies} found):
{context}

USER QUESTION: {query}

CRITICAL GROUNDING RULES:
1. Every claim you make MUST be directly stated or clearly implied in the documents above
2. Use exact quotes when possible: 'Study X states: "[exact quote]" [1]'
3. For paraphrasing, stay as close to the original wording as possible
4. If information is NOT in the documents, explicitly say "The retrieved documents do not address..."
5. Never generalize beyond what's explicitly stated (e.g., don't say "studies show X works" if only one study mentions it)
6. Never add your own knowledge - only use what's in the context

RESPONSE FORMAT:
For each claim:
- Quote or closely paraphrase the source text
- Cite with [N] immediately after
- If uncertain, hedge: "According to [N], the authors suggest..."

FORBIDDEN:
- Making inferences not explicitly supported
- Generalizing from few studies ("research shows...")
- Adding context not in the documents
- Assuming causation when correlation is stated

Your grounded response:"""
```

### Implementation

```python
# src/config/prompts.py - Add grounding mode
def get_synthesis_prompt(
    query: str,
    context: str,
    query_type: str,
    num_studies: int,
    strict_grounding: bool = True  # NEW: Enable by default
) -> str:
    if strict_grounding:
        return GROUNDED_SYNTHESIS_PROMPT.format(
            query=query,
            context=context,
            num_studies=num_studies
        )
    return SYNTHESIS_PROMPT.format(...)
```

### Expected Impact
- **Faithfulness:** +0.10-0.15 (LLM constrained to source text)
- **Risk:** Responses may feel less "synthesized" but will be more accurate

---

## Phase 2: Smart MinerU Post-Processing (P1 - 8 Hours)

### Problem
MinerU extracts PDFs to markdown, but academic papers have complex structures that result in:
- Broken tables (columns merged, rows split)
- Garbled OCR from multi-column layouts
- Incomplete sentences at page breaks
- Footnotes/references mixed with main text
- Captions separated from figures

### Current MinerU Output Pipeline

```
PDF → MinerU → raw_markdown → chunking → embedding → Qdrant
```

### Proposed: Smart Post-Processing Layer

```
PDF → MinerU → raw_markdown → SMART POST-PROCESSING → clean_markdown → chunking → embedding → Qdrant
```

### 2.1 Section Detection & Normalization

Academic papers have predictable structure. Detect and normalize sections:

```python
# src/ingestion/post_processing.py

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class DocumentSection:
    """Represents a detected section in the document."""
    type: str  # abstract, introduction, methods, results, discussion, references
    title: str
    content: str
    start_pos: int
    end_pos: int
    confidence: float

SECTION_PATTERNS = {
    "abstract": r"(?i)^#+?\s*abstract|^abstract\s*$",
    "introduction": r"(?i)^#+?\s*(?:\d+\.?\s*)?introduction|background",
    "methods": r"(?i)^#+?\s*(?:\d+\.?\s*)?method|methodology|research design|data|sample",
    "results": r"(?i)^#+?\s*(?:\d+\.?\s*)?results?|findings|empirical",
    "discussion": r"(?i)^#+?\s*(?:\d+\.?\s*)?discussion|conclusion|implications",
    "references": r"(?i)^#+?\s*(?:\d+\.?\s*)?references?|bibliography|works cited",
    "appendix": r"(?i)^#+?\s*(?:\d+\.?\s*)?appendix|supplementary",
}

def detect_sections(markdown: str) -> List[DocumentSection]:
    """
    Detect academic paper sections in markdown content.
    
    Returns list of DocumentSection objects with type and content.
    """
    sections = []
    lines = markdown.split("\n")
    
    current_section = None
    current_content = []
    current_start = 0
    
    for i, line in enumerate(lines):
        # Check if line matches a section header
        for section_type, pattern in SECTION_PATTERNS.items():
            if re.match(pattern, line.strip()):
                # Save previous section
                if current_section:
                    sections.append(DocumentSection(
                        type=current_section,
                        title=lines[current_start].strip(),
                        content="\n".join(current_content),
                        start_pos=current_start,
                        end_pos=i - 1,
                        confidence=0.8
                    ))
                
                current_section = section_type
                current_content = []
                current_start = i
                break
        else:
            current_content.append(line)
    
    # Don't forget last section
    if current_section:
        sections.append(DocumentSection(
            type=current_section,
            title=lines[current_start].strip(),
            content="\n".join(current_content),
            start_pos=current_start,
            end_pos=len(lines) - 1,
            confidence=0.8
        ))
    
    return sections
```

### 2.2 Table Repair with LLM

Tables are often corrupted. Use LLM to repair them:

```python
async def repair_table(broken_table: str, context_before: str, context_after: str) -> str:
    """
    Use LLM to repair a broken markdown table.
    
    Args:
        broken_table: The corrupted table markdown
        context_before: ~100 chars before table for context
        context_after: ~100 chars after table for context
        
    Returns:
        Repaired table markdown
    """
    prompt = f"""You are a document repair assistant. Fix this broken markdown table.

CONTEXT BEFORE: {context_before[:200]}

BROKEN TABLE:
{broken_table}

CONTEXT AFTER: {context_after[:200]}

REPAIR RULES:
1. Align columns properly
2. Ensure header row has correct separators
3. Fill obvious missing cells with appropriate values
4. If a table is beyond repair, describe its content in prose instead
5. Keep all numeric data exactly as shown

Return ONLY the repaired table markdown (or prose description if unrepairable):"""
    
    # Use local LLM or API
    response = await llm.generate(prompt)
    return response.strip()
```

### 2.3 Reference Section Removal

References clutter the retrieval and cause false matches:

```python
def remove_references_section(markdown: str) -> str:
    """
    Remove the references/bibliography section to prevent citation noise.
    
    References often match queries but don't contain useful content.
    """
    sections = detect_sections(markdown)
    
    for section in sections:
        if section.type == "references":
            # Cut everything from references to end (or next non-reference section)
            lines = markdown.split("\n")
            return "\n".join(lines[:section.start_pos])
    
    return markdown
```

### 2.4 OCR Artifact Cleanup

```python
def clean_ocr_artifacts(text: str) -> str:
    """Clean common OCR artifacts from MinerU output."""
    
    cleanups = [
        # Fix common OCR errors
        (r"\bl\b(?=\d)", "1"),  # l -> 1 when followed by digit
        (r"\bO\b(?=\d)", "0"),  # O -> 0 when followed by digit
        (r"\brn\b", "m"),  # rn -> m (common OCR error)
        
        # Fix hyphenation across lines
        (r"(\w+)-\s*\n\s*(\w+)", r"\1\2"),
        
        # Remove page numbers and headers
        (r"^\s*\d+\s*$", "", re.MULTILINE),  # Standalone page numbers
        (r"^.*Page \d+ of \d+.*$", "", re.MULTILINE),
        
        # Fix spacing issues
        (r"  +", " "),  # Multiple spaces
        (r"\n{3,}", "\n\n"),  # Multiple newlines
        
        # Fix common symbol errors
        (r"¬", "-"),  # Logical not -> hyphen
        (r"­", ""),  # Soft hyphen
    ]
    
    result = text
    for pattern, replacement, *flags in cleanups:
        flag = flags[0] if flags else 0
        result = re.sub(pattern, replacement, result, flags=flag)
    
    return result
```

### 2.5 Sentence Boundary Repair

```python
def repair_sentence_boundaries(text: str) -> str:
    """
    Repair sentences broken by page breaks or column switches.
    
    Looks for sentences that end mid-word or start with lowercase.
    """
    lines = text.split("\n")
    repaired = []
    buffer = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            if buffer:
                repaired.append(buffer)
                buffer = ""
            continue
        
        # Check if previous line ended mid-sentence
        if buffer:
            # Previous line didn't end with punctuation
            if not buffer.rstrip()[-1] in ".!?:":
                # And this line starts with lowercase
                if line[0].islower():
                    buffer = buffer.rstrip() + " " + line
                    continue
        
        if buffer:
            repaired.append(buffer)
        buffer = line
    
    if buffer:
        repaired.append(buffer)
    
    return "\n".join(repaired)
```

### 2.6 Master Post-Processing Pipeline

```python
async def post_process_mineru_output(
    raw_markdown: str,
    content_list: list,  # MinerU's structured content
    doc_metadata: dict
) -> str:
    """
    Complete post-processing pipeline for MinerU output.
    
    Args:
        raw_markdown: MinerU's markdown output
        content_list: Structured content with page/type info
        doc_metadata: PDF metadata (title, authors, year)
        
    Returns:
        Cleaned, enhanced markdown ready for chunking
    """
    # Step 1: Clean OCR artifacts
    cleaned = clean_ocr_artifacts(raw_markdown)
    
    # Step 2: Repair sentence boundaries
    cleaned = repair_sentence_boundaries(cleaned)
    
    # Step 3: Detect and normalize sections
    sections = detect_sections(cleaned)
    
    # Step 4: Remove references section (prevents citation noise)
    cleaned = remove_references_section(cleaned)
    
    # Step 5: Add document context header
    header = f"""# {doc_metadata.get('title', 'Unknown Title')}
**Authors:** {', '.join(doc_metadata.get('authors', ['Unknown']))}
**Year:** {doc_metadata.get('year', 'Unknown')}
**Source:** {doc_metadata.get('pdf_name', 'Unknown')}

---

"""
    cleaned = header + cleaned
    
    # Step 6: Repair broken tables (async, uses LLM)
    # Detect tables and repair if needed
    table_pattern = r"(\|[^\n]+\|\n)+(?:\|[-:| ]+\|\n)?(\|[^\n]+\|\n)+"
    for match in re.finditer(table_pattern, cleaned):
        table = match.group()
        # Check if table seems broken (e.g., inconsistent columns)
        if is_table_broken(table):
            context_before = cleaned[max(0, match.start()-100):match.start()]
            context_after = cleaned[match.end():min(len(cleaned), match.end()+100)]
            repaired = await repair_table(table, context_before, context_after)
            cleaned = cleaned[:match.start()] + repaired + cleaned[match.end():]
    
    return cleaned

def is_table_broken(table: str) -> bool:
    """Heuristic to detect broken tables."""
    lines = table.strip().split("\n")
    if len(lines) < 2:
        return True
    
    # Check for consistent column counts
    col_counts = [line.count("|") for line in lines]
    if len(set(col_counts)) > 2:  # Allow some variance
        return True
    
    return False
```

### Integration Point in Modal Pipeline

```python
# infrastructure/modal_mineru.py - After MinerU extraction

# Mode 2: Full extraction with MinerU
result = run_mineru(pdf_path)

if result["success"]:
    # NEW: Apply smart post-processing
    from src.ingestion.post_processing import post_process_mineru_output
    
    enhanced_markdown = await post_process_mineru_output(
        raw_markdown=result["content"],
        content_list=result.get("content_list", []),
        doc_metadata={
            "title": result.get("title"),
            "authors": result.get("authors", []),
            "year": result.get("year"),
            "pdf_name": pdf_key.split("/")[-1]
        }
    )
    
    # Use enhanced markdown for chunking
    result["content"] = enhanced_markdown
```

### Expected Impact
- **Faithfulness:** +0.10 (cleaner chunks = better grounding)
- **Retrieval Quality:** +0.05-0.10 (no reference section noise)
- **Risk:** Moderate - must test thoroughly to avoid breaking existing pipeline

---

## Phase 3: Structured Output with Instructor (P1 - 6 Hours)

### Problem
Current LLM output is free-form text. We can't enforce that every claim has a citation.

### Solution: Pydantic Models + Instructor

```python
# src/generation/structured_output.py

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from instructor import from_openai

class CitedClaim(BaseModel):
    """A single claim with its supporting citation."""
    claim: str = Field(description="The factual claim being made")
    quote: str = Field(description="Direct quote or close paraphrase from source")
    source_id: int = Field(description="Citation number [N] from the context")
    confidence: str = Field(description="high/medium/low confidence in the claim")
    
    @field_validator('claim')
    @classmethod
    def claim_not_too_long(cls, v):
        if len(v) > 300:
            raise ValueError("Claim too long - split into multiple claims")
        return v

class GroundedResponse(BaseModel):
    """Fully grounded response with explicit citations."""
    summary: str = Field(description="One-sentence summary of findings")
    claims: List[CitedClaim] = Field(description="List of cited claims")
    limitations: str = Field(description="Limitations of the evidence")
    unanswered: Optional[str] = Field(
        default=None,
        description="Aspects of the question not addressed by the sources"
    )
    
    def to_markdown(self) -> str:
        """Convert to citation-rich markdown."""
        lines = [f"**Summary:** {self.summary}\n"]
        
        for claim in self.claims:
            lines.append(f"- {claim.claim} [{claim.source_id}]")
            if claim.confidence != "high":
                lines.append(f"  *(confidence: {claim.confidence})*")
        
        lines.append(f"\n**Limitations:** {self.limitations}")
        
        if self.unanswered:
            lines.append(f"\n**Not addressed:** {self.unanswered}")
        
        return "\n".join(lines)

# Usage with Instructor
async def synthesize_structured(
    query: str,
    context: str,
    citations: List[dict]
) -> GroundedResponse:
    """Generate a structured, grounded response."""
    client = from_openai(OpenAI())
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",  # or local model
        response_model=GroundedResponse,
        messages=[
            {
                "role": "system",
                "content": """You are a research assistant that provides STRICTLY GROUNDED responses.
                Every claim must be directly supported by the provided sources.
                Include direct quotes where possible."""
            },
            {
                "role": "user", 
                "content": f"""SOURCES:
{context}

QUESTION: {query}

Provide a grounded response with explicit citations for each claim."""
            }
        ],
        max_retries=2  # Instructor will retry on validation failure
    )
    
    return response
```

### Expected Impact
- **Faithfulness:** +0.10 (enforced citation structure)
- **Debugging:** Easier to trace claims to sources
- **Risk:** May need fallback for complex queries

---

## Phase 4: Post-Hoc Verification Layer (P2 - 6 Hours)

### Problem
Even with structured output, some claims may not be fully grounded.

### Solution: Verify-and-Repair Pipeline

```python
# src/generation/verification.py

from evaluation.minicheck_evaluator import MiniCheckEvaluator

class ClaimVerifier:
    """Verify and optionally repair ungrounded claims."""
    
    def __init__(self):
        self.minicheck = MiniCheckEvaluator(backend='local')
    
    async def verify_response(
        self,
        response: GroundedResponse,
        passages: Dict[int, str]
    ) -> GroundedResponse:
        """
        Verify each claim against its cited passage.
        Remove or repair ungrounded claims.
        """
        verified_claims = []
        
        for claim in response.claims:
            passage = passages.get(claim.source_id, "")
            
            # Use MiniCheck to verify
            labels, probs = self.minicheck._nli_score(
                docs=[passage],
                claims=[claim.claim]
            )
            
            if labels[0] == 1:  # Supported
                verified_claims.append(claim)
            else:
                # Try to repair with direct quote
                repaired = await self._repair_claim(claim, passage)
                if repaired:
                    verified_claims.append(repaired)
                else:
                    logger.warning(f"Dropping unverifiable claim: {claim.claim[:50]}...")
        
        response.claims = verified_claims
        return response
    
    async def _repair_claim(
        self,
        claim: CitedClaim,
        passage: str
    ) -> Optional[CitedClaim]:
        """Try to find a supportable version of the claim."""
        prompt = f"""The following claim is NOT supported by the passage.

CLAIM: {claim.claim}

PASSAGE: {passage[:2000]}

Can you rewrite the claim to be DIRECTLY SUPPORTED by the passage?
If the passage doesn't support any version of this claim, respond with "UNSUPPORTED".

Rewritten claim:"""
        
        response = await llm.generate(prompt)
        
        if "UNSUPPORTED" in response:
            return None
        
        return CitedClaim(
            claim=response.strip(),
            quote=claim.quote,
            source_id=claim.source_id,
            confidence="medium"  # Downgrade confidence
        )
```

### Expected Impact
- **Faithfulness:** +0.05-0.10 (catch remaining ungrounded claims)
- **Trade-off:** May reduce answer completeness

---

## Phase 5: Contextual Retrieval (P2 - 8 Hours)

### Problem
Chunks lose document-level context (what study is this from? What section?).

### Solution: Anthropic-Style Context Prefixes

```python
# src/ingestion/contextual_retrieval.py

async def add_chunk_context(
    chunk: str,
    document: str,
    section_type: str,
    pdf_metadata: dict
) -> str:
    """
    Add document-level context prefix to each chunk.
    
    This helps the LLM understand where the chunk fits.
    """
    prompt = f"""Document Title: {pdf_metadata.get('title', 'Unknown')}
Section: {section_type}

Document excerpt (for context):
{document[:1500]}

Chunk to contextualize:
{chunk}

Write a 1-2 sentence context that situates this chunk within the document.
Focus on: What study is this? What is being discussed? What section?

Context:"""
    
    context = await llm.generate(prompt)
    
    return f"[Context: {context.strip()}]\n\n{chunk}"
```

### Store in Qdrant Payload

```python
# Enhanced payload structure
{
    "text": chunk_text,
    "context_prefix": "This chunk is from a 2019 RCT in Bangladesh evaluating BRAC's TUP program...",
    "section_type": "results",
    "pdf_name": "brac_tup_2019.pdf",
    "page_range": "12-14"
}
```

### Expected Impact
- **Faithfulness:** +0.05 (LLM has better study context)
- **Retrieval:** +0.10 (chunks self-identify, better matches)

---

## Phase 6: Smaller Chunks (P3 - 4 Hours)

### Current State
- Chunk size: 512 tokens
- Overlap: 50 tokens

### Proposed Change
- Chunk size: 256 tokens
- Overlap: 64 tokens (25%)

### Rationale
Smaller chunks = more precise retrieval = easier to ground claims in specific text.

### Trade-off
More chunks to embed and retrieve, potentially more API costs.

---

## Implementation Timeline

### Week 1: Quick Wins (P0)

| Day | Task | Hours |
|-----|------|-------|
| 1 | Implement strict grounding prompts | 2 |
| 1 | Run evaluation to measure impact | 1 |
| 2 | Create post_processing.py module | 4 |
| 3 | Integrate post-processing into Modal | 4 |
| 4 | Re-process sample PDFs and evaluate | 4 |

### Week 2: Structured Pipeline (P1)

| Day | Task | Hours |
|-----|------|-------|
| 5-6 | Implement Instructor integration | 6 |
| 7 | Implement verification layer | 6 |
| 8 | Integration testing | 4 |

### Week 3: Optimization (P2-P3)

| Day | Task | Hours |
|-----|------|-------|
| 9 | Contextual retrieval | 8 |
| 10 | Smaller chunks + re-indexing | 4 |
| 11-12 | Full evaluation + tuning | 8 |

---

## Expected Final Metrics

| Metric | Current | After Phase 1 | After All Phases | Target |
|--------|---------|---------------|------------------|--------|
| Faithfulness | 0.455 | 0.55-0.60 | **0.70-0.80** | 0.70+ |
| Citation Recall | 0.868 | 0.87 | 0.85-0.90 | 0.70 |
| Citation Precision | 0.869 | 0.87 | 0.85-0.90 | 0.70 |

---

## Risk Mitigation for MinerU Post-Processing

Since post-processing modifies the content before indexing, we need safeguards:

### 1. A/B Storage

```python
# Store both versions in R2
r2_client.put_object(Key=f"outputs/json/{doc_id}_raw.json", ...)
r2_client.put_object(Key=f"outputs/json/{doc_id}_enhanced.json", ...)
```

### 2. Validation Pipeline

```python
def validate_enhancement(raw: str, enhanced: str) -> bool:
    """Ensure enhancement didn't remove important content."""
    # Check we didn't lose too much content
    if len(enhanced) < len(raw) * 0.5:
        logger.warning("Enhanced content is less than 50% of raw - investigate")
        return False
    
    # Check key sections are preserved
    raw_sections = detect_sections(raw)
    enhanced_sections = detect_sections(enhanced)
    
    for section_type in ["abstract", "methods", "results"]:
        raw_has = any(s.type == section_type for s in raw_sections)
        enhanced_has = any(s.type == section_type for s in enhanced_sections)
        if raw_has and not enhanced_has:
            logger.warning(f"Lost {section_type} section in enhancement")
            return False
    
    return True
```

### 3. Fallback to Raw

```python
if not validate_enhancement(raw_markdown, enhanced_markdown):
    logger.warning("Enhancement failed validation, using raw markdown")
    enhanced_markdown = raw_markdown
```

---

## Appendix: Historical Bugs & Fixes

### Bug #1: Evaluator used snippet instead of full_text (Fixed v3)

```python
# WRONG (v2)
text = cite.get('snippet') or cite.get('full_text')  # snippet wins

# CORRECT (v3)
text = cite.get('full_text') or cite.get('snippet')  # full_text wins
```

### Bug #2: Massive Qdrant Duplication (Fixed v4)

- Before: 15,489 points (9,959 duplicates!)
- After: 5,530 unique chunks
- Fix: Deterministic point IDs + delete-before-upsert

### Bug #3: UTF-8 Encoding Errors (Fixed Dec 31)

```python
# Added sanitize_text() to handle surrogate characters
def sanitize_text(text: str) -> str:
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")
```

---

## References

### Core Papers
1. **MiniCheck** (EMNLP 2024): https://arxiv.org/abs/2404.10774
2. **ALCE Benchmark** (ACL 2023): https://arxiv.org/abs/2305.14627
3. **FActScore** (EMNLP 2023): https://arxiv.org/abs/2305.14251
4. **Self-RAG** (NeurIPS 2023): https://arxiv.org/abs/2310.11511
5. **Contextual Retrieval** (Anthropic 2024): https://www.anthropic.com/news/contextual-retrieval

### Tools
- **Instructor**: https://python.useinstructor.com/
- **MinerU**: https://github.com/opendatalab/MinerU
- **LlamaIndex**: https://docs.llamaindex.ai/

---

*Next Step: Implement Phase 1 (Strict Grounding Prompts) and measure impact on faithfulness.*
