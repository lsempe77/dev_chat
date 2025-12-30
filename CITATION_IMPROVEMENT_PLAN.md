# Citation Quality Improvement Plan: Reaching SOTA

**Created:** December 28, 2025  
**Updated:** December 30, 2025 (v4 - After Qdrant deduplication fix)  
**Goal:** Implement SOTA evaluation using correct methodology per evaluation lane

---

## ✅ PHASE 1 COMPLETE: MiniCheck Dual-Lane Evaluator

### Final Results (December 30, 2025 - After Deduplication Fix)

| Metric | Broken (v1) | v3 (full_text) | v4 (deduped) | ALCE Benchmark | Status |
|--------|-------------|----------------|--------------|----------------|--------|
| **faithfulness** | 0.135 | 0.629 | **0.455** | 0.70-0.80 | 🟡 Gap |
| **citation_recall** | 0.192 | 0.851 | **0.868** | 0.45-0.55 | ✅ **Exceeds SOTA** |
| **citation_precision** | 0.217 | 0.841 | **0.869** | 0.55-0.65 | ✅ **Exceeds SOTA** |
| **overall** | 0.181 | 0.774 | **0.731** | - | ✅ Good |

> **Note:** Faithfulness dropped from v3 because retrieval now returns diverse sources (9 docs) instead of 93 duplicates of one doc. More diverse = harder to ground all claims.

### Bug #1: Evaluator used snippet instead of full_text

**Bug:** Evaluator used `snippet` (298 chars) instead of `full_text` (8,453 chars).

```python
# WRONG (v2)
text = cite.get('snippet') or cite.get('full_text')  # snippet wins

# CORRECT (v3)
text = cite.get('full_text') or cite.get('snippet')  # full_text wins
```

The NLI model couldn't verify claims because the snippet didn't contain the relevant text.

### Bug #2: Massive Qdrant Duplication (FIXED Dec 30)

**Symptom:** Search returned 33 results from 1 document, all with identical score (0.541).

**Root Cause:** Modal pipeline generated random UUIDs for each point:
```python
# WRONG - creates new point every run
point_id = str(uuid.uuid4())

# FIXED - deterministic ID enables proper upsert deduplication
point_id = hashlib.md5(f"{doc_id}:{chunk_idx}".encode()).hexdigest()
```

**Impact:**
- Before: 15,489 points (9,959 duplicates!)
- After: 5,530 unique chunks
- Document `033d4e4c_121058373` had chunks duplicated **93x**

**Fix Applied:**
1. `scripts/deduplicate_qdrant.py` - Removed 9,959 duplicates
2. `infrastructure/modal_mineru.py` - Deterministic point IDs + delete-before-upsert

**Retrieval Now Works:**
- Before: 33 results from 1 doc
- After: 20 results from 9 docs with proper score diversity (0.51-0.66)

---

## 🚨 Critical Insight: Three Distinct Evaluation Problems

We were conflating **three different evaluation tasks** into one ladder. This caused confusion.

### The Correct Mental Model

| Lane | What it Measures | Best Tool | Our Metric |
|------|------------------|-----------|------------|
| **A) Groundedness** | Claim ⊥ ANY context → supported? | **MiniCheck** | `faithfulness` |
| **B) Citation Alignment** | Sentence ⊥ CITED passage → entailed? | **ALCE-style + MiniCheck** | `citation_recall`, `citation_precision` |
| **C) Long-form Factual Precision** | Atomic facts across response | **FActScore** | (future) |

### Key References

| Tool | Paper | What it's SOTA for |
|------|-------|-------------------|
| **MiniCheck** | EMNLP 2024 | Groundedness verification (claim vs context) |
| **ALCE AutoAIS** | ACL 2023 | Citation alignment (sentence vs cited passage) |
| **FActScore** | EMNLP 2023 | Long-form factual precision (atomic decomposition) |

**MiniCheck can serve as the NLI backbone for BOTH Lane A and Lane B!**  
The difference is **what you pair together**, not the model.

---

## Current State vs Target (Updated Dec 30)

| Metric | Lane | Current | Target | Gap | Priority |
|--------|------|---------|--------|-----|----------|
| **faithfulness** | A | **0.629** | 0.70+ | -0.07 | 🟡 Medium |
| **citation_recall** | B | **0.851** | 0.70+ | ✅ +0.15 | ✅ Done |
| **citation_precision** | B | **0.841** | 0.70+ | ✅ +0.14 | ✅ Done |
| **context_precision** | - | 0.84 | 0.80+ | ✅ | ✅ Done |
| **answer_relevancy** | - | N/A | 0.85+ | - | 🟡 Future |

**ALCE Paper Benchmarks (GPT-4 + Best Methods):**
- Citation Precision: 55-65% → **We achieved 84%!**
- Citation Recall: 45-55% → **We achieved 85%!**
- Correctness (Faithfulness): 70-80% → We're at 63% (gap: 7%)

**Our citation metrics EXCEED ALCE benchmarks.** The remaining gap is in faithfulness.

---

## Debugging Trace (Dec 30, 2025)

### Problem: Initial scores were terrible (Faith: 0.135, CitRecall: 0.192)

### Trace Step 1: Check what contexts the evaluator receives
```
Source [1]: A multifaceted program causes lasting progress...
  snippet: 298 chars
  full_text: 8,453 chars
```
**Finding:** `full_text` has 28x more content than `snippet`.

### Trace Step 2: Check NLI with snippet (298 chars)
```
Sentence: "This method is particularly focused on marginalized families..."
Passage [1] (snippet): "the poorest families... to shift from insecure..."
NLI Result: 2/8 sentences PASS (25%)
```
**Finding:** Snippet too short to verify most claims.

### Trace Step 3: Check NLI with full_text (8,453 chars)
```
Same sentences checked against full_text:
NLI Result: 8/8 sentences PASS (100%)
```
**Finding:** Full text contains all the information needed.

### Root Cause
```python
# _build_passage_lookup() prioritized snippet over full_text
text = cite.get('snippet') or cite.get('full_text')  # WRONG

# Fixed to prioritize full_text
text = cite.get('full_text') or cite.get('snippet')  # CORRECT
```

### Per-Query Results (After Fix)

| Query | Faith | CitRecall | CitPrec |
|-------|-------|-----------|---------|
| Graduation approach | 0.69 | 0.80 | 0.80 |
| Key components | 0.62 | 1.00 | 1.00 |
| Bangladesh evidence | 0.71 | 0.86 | 0.86 |
| Africa studies | 0.77 | 1.00 | 1.00 |
| Long-term effects | 0.34 | 0.60 | 0.55 |
| **Average** | **0.63** | **0.85** | **0.84** |

---

## Phase 1: Implement Dual-Lane Evaluator with MiniCheck ✅ COMPLETE

### 1.1 Architecture Overview

```
evaluation/minicheck_evaluator.py
├── Lane A: Faithfulness (Groundedness)
│   └── For each claim: MiniCheck(any_context, claim) → supported?
│   └── Score = avg(supported claims)
│
├── Lane B: Citation Alignment (ALCE-style)
│   └── For each sentence with [N]: MiniCheck(passage_N, sentence) → entailed?
│   └── citation_recall = avg(sentences supported by their cited passages)
│   └── citation_precision = avg(citations that are necessary)
│
└── NLI Backbone: MiniCheck-Flan-T5-Large (770M) or Bespoke-MiniCheck-7B
```

### 1.2 Install MiniCheck

```bash
# For CPU/small GPU (recommended for dev)
pip install "minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main"

# For GPU with vLLM (production)
pip install "minicheck[llm] @ git+https://github.com/Liyan06/MiniCheck.git@main"
```

### 1.3 Lane A: Faithfulness Implementation

```python
from minicheck.minicheck import MiniCheck

class DualLaneEvaluator:
    def __init__(self, model_name='flan-t5-large'):
        # MiniCheck-Flan-T5-Large: 770M, GPT-4 level accuracy
        self.scorer = MiniCheck(model_name=model_name, cache_dir='./ckpts')
    
    def evaluate_faithfulness(self, claims: List[str], contexts: List[str]) -> float:
        """
        Lane A: Is each claim supported by ANY context?
        This is groundedness verification.
        """
        if not claims or not contexts:
            return 0.0
        
        combined_context = " ".join(contexts)
        docs = [combined_context] * len(claims)
        
        pred_labels, probs, _, _ = self.scorer.score(docs=docs, claims=claims)
        
        # Faithfulness = proportion of claims that are supported
        return sum(pred_labels) / len(pred_labels)
```

### 1.4 Lane B: Citation Alignment Implementation (ALCE-style)

```python
def evaluate_citation_alignment(
    self, 
    sentences: List[Dict],  # [{"text": "...", "citations": [1, 2]}]
    passages: Dict[int, str]  # {1: "passage text", 2: "passage text"}
) -> Tuple[float, float]:
    """
    Lane B: Does each citation actually support the sentence it's attached to?
    
    Returns:
        citation_recall: % of sentences entailed by their cited passages (jointly)
        citation_precision: % of citations that are necessary
    """
    recall_scores = []
    precision_scores = []
    
    for sent in sentences:
        if not sent["citations"]:
            continue  # Skip sentences without citations
        
        # CITATION RECALL: Does the joint cited passage entail the sentence?
        cited_passages = " ".join([passages[c] for c in sent["citations"] if c in passages])
        
        if cited_passages:
            pred_label, prob, _, _ = self.scorer.score(
                docs=[cited_passages], 
                claims=[sent["text"]]
            )
            recall_scores.append(pred_label[0])
        
        # CITATION PRECISION: Is each citation necessary? (overcitation detection)
        for cite_id in sent["citations"]:
            if cite_id not in passages:
                continue
            
            # Check if this single citation alone entails the sentence
            single_passage = passages[cite_id]
            pred_label, prob, _, _ = self.scorer.score(
                docs=[single_passage], 
                claims=[sent["text"]]
            )
            precision_scores.append(pred_label[0])
    
    citation_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0.0
    citation_precision = sum(precision_scores) / len(precision_scores) if precision_scores else 0.0
    
    return citation_recall, citation_precision
```

### 1.5 Sentence Extraction with Citations

```python
import re

def extract_sentences_with_citations(answer: str) -> List[Dict]:
    """
    Parse answer into sentences, tracking which citations each has.
    
    Input: "The program showed effects [1]. Participants improved [1][2]."
    Output: [
        {"text": "The program showed effects", "citations": [1]},
        {"text": "Participants improved", "citations": [1, 2]}
    ]
    """
    # Split on sentence boundaries but preserve citation markers
    sentences = re.split(r'(?<=[.!?])\s+', answer)
    
    result = []
    for sent in sentences:
        # Find all [N] citations
        citations = [int(m) for m in re.findall(r'\[(\d+)\]', sent)]
        # Remove citation markers from text
        clean_text = re.sub(r'\s*\[\d+\]', '', sent).strip()
        
        if clean_text:
            result.append({
                "text": clean_text,
                "citations": citations
            })
    
    return result
```

### 1.6 Full Evaluator Class

```python
# evaluation/minicheck_evaluator.py

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import re
from minicheck.minicheck import MiniCheck

@dataclass
class DualLaneResult:
    """Results from dual-lane evaluation."""
    # Lane A: Groundedness
    faithfulness: float
    
    # Lane B: Citation Alignment
    citation_recall: float
    citation_precision: float
    
    # Details for debugging
    claim_details: List[Dict] = None
    sentence_details: List[Dict] = None
    errors: List[str] = None


class MiniCheckEvaluator:
    """
    Dual-lane evaluator using MiniCheck as NLI backbone.
    
    Lane A (Faithfulness): Is each claim grounded in ANY retrieved context?
    Lane B (Citation Alignment): Does each citation actually entail its sentence?
    """
    
    def __init__(self, model_name: str = 'flan-t5-large'):
        self.scorer = MiniCheck(model_name=model_name, cache_dir='./ckpts')
    
    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: List[str],
        citations: List[Dict]
    ) -> DualLaneResult:
        """Run both evaluation lanes."""
        errors = []
        
        # Build passage lookup: {1: "text", 2: "text", ...}
        passages = {}
        for i, cite in enumerate(citations, 1):
            text = cite.get('snippet') or cite.get('full_text') or cite.get('text', '')
            if text:
                passages[i] = text
        
        # Lane A: Faithfulness
        claims = self._extract_claims(answer)
        faithfulness = self._evaluate_faithfulness(claims, contexts)
        
        # Lane B: Citation Alignment
        sentences = self._extract_sentences_with_citations(answer)
        citation_recall, citation_precision = self._evaluate_citation_alignment(sentences, passages)
        
        return DualLaneResult(
            faithfulness=faithfulness,
            citation_recall=citation_recall,
            citation_precision=citation_precision,
            errors=errors if errors else None
        )
```

### 1.7 Expected Impact

| Metric | Before | After Phase 1 |
|--------|--------|---------------|
| faithfulness | Broken (wrong model) | 0.85+ (MiniCheck) |
| citation_recall | 0.00 (embedding sim) | 0.50-0.70 (NLI) |
| citation_precision | N/A | 0.50-0.70 (NLI) |

---

## Phase 2: Legacy Debugging (Optional - Skip if Phase 1 works)

The old embedding-based evaluation had bugs. With MiniCheck, this is largely obsolete.

### 2.1 Old Citation Accuracy Issues (DEPRECATED)
**Issue:** Returns 0% even with visible citations

**Root Cause:** Using embedding similarity instead of NLI entailment
- Embedding similarity measures "topic overlap"
- NLI entailment measures "does passage SUPPORT claim"
- These are fundamentally different!

**Fix:** Use MiniCheck for NLI (Phase 1)

### 2.2 Old Context Precision Issues (DEPRECATED)
**Issue:** Returns 0%
- [ ] Log what contexts are being matched
- [ ] Lower similarity threshold from 0.8 to 0.6
- [ ] Use sentence-level matching instead of full chunk

### 1.2 Debug Context Precision Metric  
**Issue:** Returns 0% 

**Investigation:**
```python
# Current: Uses reranker scores or embedding similarity to query
# Bug: Contexts list may be empty or scores not propagated
```

**Fix:** Use MiniCheck (Phase 1)

### 2.3 Better Claim Extraction
**Current:** Regex sentence splitting
**Problem:** Doesn't align with what LLM actually claims

**Fix:** See Phase 1.5 - `extract_sentences_with_citations()`

---

## Phase 3: Structured Output (Days 2-3) 🎯 HIGH IMPACT

The biggest improvement comes from **forcing structured JSON output**.

### 2.1 Install Instructor Library
```bash
pip install instructor
```

### 2.2 Define Pydantic Schema
```python
from pydantic import BaseModel, Field
from typing import List

class CitedClaim(BaseModel):
    """A single claim with its supporting citation."""
    claim: str = Field(description="A single factual statement")
    source_id: int = Field(description="1-indexed source number")
    quote: str = Field(description="Exact text from source supporting this claim")
    
class StructuredAnswer(BaseModel):
    """Complete answer with structured citations."""
    claims: List[CitedClaim]
    summary: str = Field(description="2-3 sentence overview")
    limitations: str = Field(description="Caveats about the evidence")
```

### 2.3 Replace Free-Text Generation
```python
import instructor
from openai import OpenAI

client = instructor.from_openai(OpenAI())

response = client.chat.completions.create(
    model="gpt-4o-mini",
    response_model=StructuredAnswer,
    messages=[{
        "role": "user",
        "content": f"Answer: {query}\n\nSources:\n{context}"
    }]
)

# Now we have GUARANTEED structure:
for claim in response.claims:
    # We can VERIFY: does source_id actually contain this quote?
    source_text = sources[claim.source_id - 1]['content']
    is_valid = claim.quote in source_text
```

### 3.4 Expected Impact
- **citation_recall:** +0.10-0.15 (we can verify quotes exist via MiniCheck)
- **faithfulness:** Already good with MiniCheck
- **citation_precision:** +0.10 (every claim has explicit source)

---

## Phase 4: Smaller Chunks (Day 4) 🎯 MEDIUM IMPACT

256-word chunks are still too large for precise attribution.

### 3.1 Reduce to 100-150 Words
```python
# src/config/settings.py
chunk_size_words: int = 128  # Down from 256
chunk_overlap_words: int = 32  # 25% overlap
```

### 3.2 Re-chunk Existing Documents
```bash
# Script to re-process with smaller chunks
python scripts/rechunk_documents.py --chunk-size 128
```

### 3.3 Increase Retrieval Count
```python
# More smaller chunks needed to cover same content
retrieval_top_k: int = 30  # Up from 20
rerank_top_k: int = 15  # Up from 10
```

### 4.4 Expected Impact
- **citation_recall:** +0.10-0.15 (easier to match exact text)
- **faithfulness:** +0.05-0.10 (less noise per chunk)

---

## Phase 5: Post-Hoc Verification Layer (Day 5) 🎯 HIGH IMPACT

Even with structured output, LLM can hallucinate quotes.

### 4.1 Quote Verification
```python
def verify_citation(claim: CitedClaim, sources: List[Dict]) -> bool:
    """Check if the claimed quote actually exists in the source."""
    source_text = sources[claim.source_id - 1]['content']
    
    # Exact match
    if claim.quote in source_text:
        return True
    
    # Fuzzy match (handle minor formatting differences)
    from rapidfuzz import fuzz
    similarity = fuzz.partial_ratio(claim.quote.lower(), source_text.lower())
    return similarity > 85
```

### 4.2 Citation Repair
```python
def repair_citation(claim: CitedClaim, sources: List[Dict]) -> Optional[CitedClaim]:
    """If quote not found, try to find best matching source."""
    best_match = None
    best_score = 0
    
    for i, source in enumerate(sources):
        similarity = compute_similarity(claim.quote, source['content'])
        if similarity > best_score:
            best_score = similarity
            best_match = i + 1
    
    if best_score > 0.7:
        return CitedClaim(
            claim=claim.claim,
            source_id=best_match,
            quote=extract_best_quote(claim.quote, sources[best_match-1]['content'])
        )
    return None  # Remove this claim as unverifiable
```

### 5.3 Filter Unverifiable Claims
```python
verified_claims = []
for claim in response.claims:
    if verify_citation(claim, sources):
        verified_claims.append(claim)
    else:
        repaired = repair_citation(claim, sources)
        if repaired:
            verified_claims.append(repaired)
        else:
            logger.warning(f"Dropping unverifiable claim: {claim.claim[:50]}...")
```

### 5.4 Expected Impact
- **citation_precision:** +0.15-0.25 (guaranteed quote verification)
- **faithfulness:** +0.05-0.10 (only verified claims in output)

---

## Phase 6: Contextual Retrieval (Day 6-7)

Add Anthropic-style chunk prefixes for better context.

### 5.1 Generate Chunk Context at Ingestion
```python
async def add_chunk_context(chunk: str, document: str) -> str:
    """Add document-level context to each chunk."""
    prompt = f"""
    Document: {document[:2000]}...
    
    Chunk: {chunk}
    
    Write a 1-2 sentence context that situates this chunk within the document.
    Focus on: What study is this from? What section? What is being discussed?
    """
    context = await llm.generate(prompt)
    return f"[Context: {context}]\n\n{chunk}"
```

### 5.2 Store Enriched Chunks
```python
# In Qdrant payload
{
    "text": chunk_text,
    "context_prefix": "This chunk is from a 2019 RCT in Bangladesh examining...",
    "pdf_name": "brac_graduation_2019.pdf",
    "page_number": 12
}
```

### 6.3 Expected Impact
- **context_precision:** +0.20-0.30 (chunks self-identify)
- **faithfulness:** +0.05-0.10 (LLM has better study context)

---

## Phase 7: Self-RAG Retrieval Critique (Day 8)

Let LLM evaluate its own retrieval before synthesis.

### 7.1 Relevance Grading
```python
async def grade_retrieved_chunks(query: str, chunks: List[str]) -> List[Tuple[str, float]]:
    """Have LLM grade each chunk's relevance."""
    graded = []
    for chunk in chunks:
        score = await llm.generate(f"""
        Query: {query}
        Chunk: {chunk}
        
        Grade relevance 0-10. Just output the number.
        """)
        graded.append((chunk, float(score) / 10))
    return [(c, s) for c, s in graded if s > 0.6]
```

### 7.2 Retrieval Augmentation
```python
if len(relevant_chunks) < 3:
    # Query expansion
    expanded = await expand_query(query)
    additional = await retrieve(expanded)
    relevant_chunks.extend(additional)
```

### 7.3 Expected Impact
- **context_precision:** +0.15-0.25 (only relevant chunks used)
- **faithfulness:** +0.05-0.10 (less noise in context)

---

## Implementation Order & Timeline (UPDATED)

| Phase | Task | Effort | Impact | Priority |
|-------|------|--------|--------|----------|
| **1** | MiniCheck Dual-Lane Evaluator | 6 hrs | ⭐⭐⭐⭐ | **P0** |
| **2** | Debug Existing Evaluation | 2 hrs | 🔧 | P0 |
| **3** | Structured Output (Instructor) | 8 hrs | ⭐⭐⭐ | P1 |
| **4** | Post-Hoc Verification | 6 hrs | ⭐⭐⭐ | P1 |
| **5** | Smaller Chunks | 4 hrs | ⭐⭐ | P2 |
| **6** | Contextual Retrieval | 8 hrs | ⭐⭐ | P2 |

**Total: ~34 hours**

---

## Expected Final Metrics (Dual-Lane)

After implementing Phase 1 (MiniCheck Dual-Lane):

| Metric | Lane | Current | After MiniCheck | Target |
|--------|------|---------|-----------------|--------|
| faithfulness | A | 0.95 | 0.90+ | 0.90+ |
| citation_recall | B | 0.00 | 0.55-0.65 | 0.70 |
| citation_precision | B | 0.00 | 0.55-0.65 | 0.70 |
| context_precision | - | 0.00 | 0.60 | 0.80 |
| answer_relevancy | - | 0.82 | 0.82 | 0.85 |

**Note:** ALCE paper benchmarks for GPT-4 are ~55-65% citation precision/recall, so 0.55-0.65 is actually SOTA-competitive!

---

## Quick Wins (Do Today)

1. ✅ **Install MiniCheck** - `pip install "minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main"`
2. ✅ **Create `evaluation/minicheck_evaluator.py`** - Dual-lane architecture
3. ✅ **Update `run_claim_ledger_eval.py`** - Use new evaluator
4. ✅ **Run evaluation** - Compare to old metrics

This alone should give us real, meaningful citation metrics!

---

## Files to Create/Modify (UPDATED)

| File | Change |
|------|--------|
| `evaluation/minicheck_evaluator.py` | **NEW**: Dual-lane MiniCheck evaluator |
| `run_claim_ledger_eval.py` | UPDATE: Use MiniCheckEvaluator |
| `pyproject.toml` | ADD: minicheck dependency |
| `evaluation/reliable_evaluator.py` | DEPRECATE: Old embedding-based approach |
| `src/generation/structured_output.py` | NEW: Instructor-based synthesizer (Phase 3) |

---

## References (UPDATED)

### Core Papers
1. **MiniCheck** (EMNLP 2024): https://arxiv.org/abs/2404.10774
   - SOTA for groundedness verification
   - GPT-4 level accuracy at 400x lower cost
   - LLM-AggreFact benchmark

2. **ALCE Benchmark** (ACL 2023): https://arxiv.org/abs/2305.14627
   - Citation quality metrics (precision/recall)
   - AutoAIS methodology for sentence-level entailment

3. **FActScore** (EMNLP 2023): https://arxiv.org/abs/2305.14251
   - Atomic fact decomposition
   - Long-form factual precision

### Key Distinction
- **MiniCheck** = groundedness verifier (claim ⊥ context)
- **ALCE** = citation alignment metric (sentence ⊥ cited passage)
- **FActScore** = atomic factual precision (response-level)

MiniCheck can be the **NLI backbone** for both Lane A and Lane B. The difference is **what you pair together**.

### Other References
4. **Instructor Library**: https://python.useinstructor.com/
5. **Contextual Retrieval**: https://www.anthropic.com/news/contextual-retrieval
6. **Self-RAG**: https://arxiv.org/abs/2310.11511
7. **REC (Rate, Explain, Cite)**: https://arxiv.org/abs/2404.11844 - Emerging meta-evaluation

---

*Start with Phase 1 (MiniCheck Dual-Lane) for correct evaluation methodology!*
