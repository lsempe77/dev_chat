# DevChat v2 - Further Improvements Roadmap

**Purpose:** Map features from leading AI research tools to make DevChat the best-in-class evidence synthesis platform for development research.

**Date:** January 7, 2026

---

## ✅ Infrastructure Improvements (DONE)

### Modal Pipeline Refactoring (January 7, 2026)
- ✅ Refactored monolithic `modal_mineru.py` (1700+ lines) into `modal_lib/` package
- ✅ 8 focused modules: config, extraction, chunking, embedding, indexing, metadata, processing, utils
- ✅ Entry point now ~230 lines (87% code reduction)
- ✅ Background processing via `.spawn()` - prevents webhook timeout
- ✅ Stale job auto-cleanup (jobs > 30 min marked as failed)
- ✅ Successfully tested with 97/97 PDFs processed

**Benefits:**
- Easier to maintain and extend (each module < 200 lines)
- Ready for Contextual Retrieval integration (just modify `chunking.py`)
- Ready for Parent-Child chunking (modify `chunking.py` + `indexing.py`)
- Async webhook prevents Railway timeout issues

---

## 📊 RAG Techniques Audit: Where Do You Stand?

### Current DevChat Implementation vs. State-of-the-Art

| Technique | DevChat | SOTA | Status | Priority |
|-----------|---------|------|--------|----------|
| **Hybrid Search (Dense + Sparse)** | ✅ Cohere + BM25 | ✅ Same | ✅ **Current** | - |
| **Reranking** | ✅ Cohere rerank-v3.5 | ✅ Same | ✅ **Current** | - |
| **Two-Pass Synthesis (ALCE)** | ✅ Claim Ledger | ✅ Same | ✅ **Current** | - |
| **Post-Hoc Verification (NLI)** | ✅ MiniCheck | ✅ Same | ✅ **Current** | - |
| **Page-Aware Chunking** | ✅ 256 words | ✅ Same | ✅ **Current** | - |
| **Metadata Filtering** | ✅ Year, country, sector | ✅ Same | ✅ **Current** | - |
| **Contextual Retrieval** | ✅ GPT-4o-mini | ✅ Anthropic's method | ✅ **DONE** | - |
| **HyDE (Hypothetical Doc Embedding)** | ⚠️ Optional | ✅ Standard | ⚠️ **Partial** | Medium |
| **Parent-Child Chunking** | ❌ Not implemented | ✅ PaperQA2 | 🔴 **Gap** | High |
| **Agentic RAG (Iterative)** | ❌ Single-shot | ✅ PaperQA2 | 🔴 **Gap** | High |
| **Contextual Summarization (RCS)** | ❌ Not implemented | ✅ PaperQA2 | 🔴 **Gap** | High |
| **Multimodal (Images/Tables)** | ❌ Text-only | ✅ PaperQA2 | 🔴 **Gap** | Medium |
| **Late Chunking** | ❌ Not implemented | ✅ Emerging | 🟡 **Future** | Low |
| **Self-RAG / Corrective RAG** | ❌ Not implemented | ✅ Emerging | 🟡 **Future** | Low |

### Verdict: You're 70% there, but missing key innovations

**What You Have (Excellent):**
- Hybrid search with BM25 - matches Anthropic's recommendation
- Cohere rerank - matches PaperQA2 and Anthropic's best practice
- Two-pass Claim Ledger - advanced technique most tools don't have
- Post-hoc MiniCheck verification - cutting edge NLI-based grounding

**What You're Missing (High Impact):**
1. ~~**Contextual Retrieval** - Anthropic's 49% improvement technique~~ ✅ **DONE (Jan 8, 2026)**
2. **Parent-Child Chunking** - Small chunks for search, expand for context
3. **Contextual Summarization (RCS)** - LLM summarizes each chunk before synthesis
4. **Agentic RAG** - Iterative search refinement

---

## ✅ COMPLETED: Contextual Retrieval (Anthropic's 49% Improvement)

**Implemented:** January 8, 2026

### What Was Done
During indexing, each chunk is now prepended with LLM-generated context explaining its role in the document.

### Implementation Details
- **Location:** `infrastructure/modal_lib/embedding.py`
- **Model:** GPT-4o-mini via OpenRouter (fast, cheap, high quality)
- **Parallel processing:** ThreadPoolExecutor with 5 workers for speed
- **Fallback:** Metadata-based prefix if LLM fails

### New Qdrant Payload Fields
- `text` - Original chunk text (preserved)
- `contextual_prefix` - The LLM-generated 2-3 sentence context
- `text_with_context` - Combined prefix + original text (what's embedded)

### Example Contextual Prefix
```
"This chunk is part of a working paper that presents a multi-arm randomized 
controlled trial (RCT) evaluating the Government of Zambia's Supporting Women's 
Livelihoods (SWL) program, which aims to alleviate poverty among extremely poor 
women in rural areas through a combination of financial capital, skills training, 
and mentorship."
```

### Results
- **97 PDFs reprocessed** with contextual retrieval enabled
- **6,769 chunks** indexed with contextual prefixes
- **0 failures** during processing

### Expected Impact
- **Anthropic's tests:** 49% reduction in retrieval failures
- **With reranking (which we have):** 67% reduction in retrieval failures

---

## 🔴 Critical Gap #2: Parent-Child Chunking

### What It Is
Create small chunks for precise retrieval, but expand to parent chunks for synthesis context.

### Current DevChat
- 256-word chunks for both retrieval AND synthesis
- Problem: Small chunks lose context

### PaperQA2 Approach
- **Child chunks:** 128-256 tokens (for search)
- **Parent chunks:** 1000-2000 tokens (for synthesis)
- When a child matches, expand to parent for LLM context

### Implementation
```python
@dataclass
class ChunkWithParent:
    child_id: str
    child_text: str  # Small, for embedding
    parent_id: str
    parent_text: str  # Large, for synthesis
    page_numbers: List[int]

class ParentChildChunker:
    def __init__(self, child_size: int = 200, parent_size: int = 1000):
        self.child_size = child_size
        self.parent_size = parent_size
    
    def chunk(self, document: str) -> List[ChunkWithParent]:
        # Create overlapping parent chunks
        parents = self._create_parents(document)
        
        # Split each parent into children
        chunks = []
        for parent in parents:
            children = self._split_into_children(parent)
            for child in children:
                chunks.append(ChunkWithParent(
                    child_id=child.id,
                    child_text=child.text,
                    parent_id=parent.id,
                    parent_text=parent.text,
                    page_numbers=parent.pages
                ))
        return chunks
```

### Qdrant Schema Change
```python
# Store child for retrieval, parent for expansion
payload = {
    "text": child_text,           # Embedded
    "parent_text": parent_text,   # Stored but not embedded
    "parent_id": parent_id,
    "page_numbers": [1, 2]
}
```

### Impact
- Better retrieval precision (small chunks match better)
- Better synthesis context (large chunks for LLM)

### Effort: ~12 hours (chunking + Qdrant schema + retrieval changes)

---

## 🔴 Critical Gap #3: Contextual Summarization (RCS)

### What It Is (PaperQA2's Key Innovation)
Before using a chunk for synthesis, create an LLM summary of how it relates to the query.

### Current DevChat Flow
```
Query → Retrieve chunks → Pass raw chunks to synthesis LLM
```

### PaperQA2 Flow (with RCS)
```
Query → Retrieve chunks → For each chunk: LLM creates relevance summary → 
        Score summaries → Pass top summaries to synthesis LLM
```

### Implementation
```python
async def create_contextual_summary(
    chunk: str, 
    query: str,
    metadata: dict
) -> tuple[str, float]:
    """
    Create a summary of the chunk in context of the query.
    Returns (summary, relevance_score).
    """
    prompt = f"""Question: {query}

Document excerpt from "{metadata.get('title', 'Unknown')}" ({metadata.get('year', 'n.d.')}):
{chunk}

Task: Summarize ONLY the information from this excerpt that is relevant to answering the question.
If nothing is relevant, respond with "Not relevant."

Return JSON:
{{
    "summary": "...",
    "relevance_score": 0.0-1.0,
    "key_findings": ["...", "..."]
}}"""
    
    response = await llm.complete(prompt)
    data = json.loads(response)
    return data["summary"], data["relevance_score"]
```

### Why This Matters
1. **Filters irrelevant chunks** before synthesis (cheaper, faster)
2. **Extracts only relevant info** from each chunk
3. **LLM scoring** is more nuanced than embedding similarity
4. **Summaries are easier** for synthesis LLM to process

### Integration with Claim Ledger
Your Claim Ledger extraction is already close to RCS! The difference:
- **RCS:** Summarize relevance, then synthesize
- **Claim Ledger:** Extract claims with quotes, then synthesize

Consider: Add relevance scoring to claim extraction, filter low-relevance claims.

### Effort: ~8 hours (new step between retrieval and synthesis)

---

## 🔴 Critical Gap #4: Agentic RAG (Multi-Step)

### What It Is
Instead of single-shot retrieval, let an LLM agent decide when to search again.

### Current DevChat
```
User Query → Single Search → Rerank → Synthesize → Answer
```

### PaperQA2 Agentic Flow
```
User Query → Agent decides: Search Tool
          → Agent reviews results: "Not enough evidence"
          → Agent: Search with different keywords
          → Agent reviews: "Found 5 relevant papers"
          → Agent: Gather Evidence Tool (create summaries)
          → Agent: "Need more on methodology"
          → Agent: Search again
          → Agent: Generate Answer Tool
          → Final Answer
```

### Implementation Sketch
```python
class AgenticRAG:
    tools = [
        SearchTool(),        # Search vector DB
        GatherEvidenceTool(), # Create RCS summaries
        GenerateAnswerTool()  # Final synthesis
    ]
    
    async def run(self, query: str, max_iterations: int = 3) -> str:
        context = AgentContext(query=query, evidence=[])
        
        for i in range(max_iterations):
            # Agent decides next action
            action = await self.agent_llm.decide(
                query=query,
                current_evidence=context.evidence,
                tools=self.tools
            )
            
            if action.tool == "generate_answer":
                return await self.generate_answer(context)
            
            # Execute tool
            result = await action.tool.execute(action.params)
            context.update(result)
            
            # Check if we have enough evidence
            if self._sufficient_evidence(context):
                break
        
        return await self.generate_answer(context)
```

### Benefits
- Handles complex, multi-part questions
- Can recognize when initial search is insufficient
- More thorough evidence coverage
- Better for systematic review use cases

### Effort: ~20 hours (significant architecture change)

---

## 🟡 Future Techniques (Lower Priority)

### Late Chunking (Emerging)
Embed the full document, then chunk the embeddings (not the text).
- **Status:** Experimental, not widely adopted
- **Skip for now**

### Self-RAG / Corrective RAG
LLM self-critiques and corrects its retrieval.
- **You already have this** via MiniCheck post-hoc verification
- **No action needed**

### RAPTOR (Hierarchical Summarization)
Create a tree of summaries at different abstraction levels.
- **Complex to implement**
- **Lower priority** - your Claim Ledger approach may be sufficient

### GraphRAG
Build knowledge graphs from documents for relationship queries.
- **Overkill** for your current use case
- **Future consideration** for complex policy analysis

---

## 🎯 Executive Summary

### RAG Improvement Priorities (NEW)

| Priority | Technique | Effort | Impact | Source |
|----------|-----------|--------|--------|--------|
| 🔴 1 | **Contextual Retrieval** | 8h | 49% fewer failures | Anthropic |
| 🔴 2 | **Parent-Child Chunking** | 12h | Better context | PaperQA2 |
| 🔴 3 | **Contextual Summarization (RCS)** | 8h | Higher precision | PaperQA2 |
| 🔴 4 | **Agentic RAG** | 20h | Complex queries | PaperQA2 |
| 🟡 5 | Multimodal (images/tables) | 24h | More content | PaperQA2 |

**Total RAG improvements: ~72 hours**

### Feature Improvement Priorities (Competitive)

After analyzing seven leading AI research platforms, this document maps actionable improvements for DevChat. The goal: become the **definitive tool for evidence-based development research**, combining the best features from:

---

## ✅ Priority 1: Citation Highlighting in PDFs (DONE)

### Implementation (January 6, 2026)
- ✅ PyMuPDF endpoint: `/rags/{id}/documents/{doc_id}/pdf-highlighted`
- ✅ Inline PDF viewer replaces Evidence panel with toggle button
- ✅ Full Qdrant chunk text (1500 chars) used for highlighting
- ✅ Overlapping 6-word groups for better PDF text matching
- ✅ Evidence snippet card with page number and copy button
- ✅ Public RAG support without authentication

### Original Plan (Completed)
When a user clicks a citation, generate a PDF with the source text highlighted.

**Implementation:**
```python
import pymupdf

def highlight_citation(pdf_path: str, page_num: int, source_text: str) -> bytes:
    """Highlight the cited text in the PDF and return highlighted PDF bytes."""
    doc = pymupdf.open(pdf_path)
    page = doc[page_num - 1]  # 0-indexed
    
    # Search for the source text
    rects = page.search_for(source_text)
    
    if rects:
        # Add yellow highlight annotation
        annot = page.add_highlight_annot(rects)
        annot.set_colors(stroke=(1, 0.8, 0))  # Yellow
        annot.update()
    
    # Return as bytes for streaming
    return doc.tobytes()
```

**Frontend Changes:**
- Add a new API endpoint: `GET /api/documents/{id}/highlighted?page={n}&text={encoded_text}`
- PDF viewer opens with highlight already applied
- Users can see exactly what text supports each claim

**Effort:** ~4 hours
**Impact:** High - Visual proof of grounding increases trust

---

## 🚀 Priority 2: Smart Citations (Scite-Inspired)

### Current State
- Citations show page references but not citation context
- No indication if a study supports or contradicts a claim

### Improvement: Citation Context Classification

**Database Schema Addition:**
```sql
-- Add to documents table or create citation_analysis table
ALTER TABLE documents ADD COLUMN citation_analysis JSONB DEFAULT '{}';

-- Structure:
{
  "citations_received": [
    {
      "citing_doi": "10.1234/...",
      "citing_title": "...",
      "context": "supporting" | "contrasting" | "mentioning",
      "snippet": "This confirms the findings of...",
      "confidence": 0.92
    }
  ],
  "citation_count": 45,
  "supporting_count": 38,
  "contrasting_count": 3,
  "mentioning_count": 4
}
```

**Implementation Approach:**
1. **Enrich from OpenAlex/Semantic Scholar:** Fetch citing papers metadata
2. **LLM Classification:** For each citation context snippet, classify as supporting/contrasting/mentioning
3. **UI Display:** Show badges on documents: "38 Supporting | 3 Contrasting"

**New Prompt for Classification:**
```
Given this citation context from a research paper:
"{citation_snippet}"

The cited paper's main finding is: "{cited_paper_finding}"

Classify this citation as one of:
- SUPPORTING: The citing paper agrees with or builds upon the finding
- CONTRASTING: The citing paper disagrees or presents conflicting evidence
- MENTIONING: Neutral reference without explicit agreement/disagreement

Return: {"classification": "...", "confidence": 0.0-1.0, "reasoning": "..."}
```

**Effort:** ~12 hours
**Impact:** Very High - Transforms evidence evaluation

---

## 🚀 Priority 3: Consensus Meter Visualization

### Current State
- Responses synthesize evidence but don't quantify agreement
- No visual representation of scientific consensus

### Improvement: Evidence Consensus Visualization

**New Component: ConsensusMeter**
```typescript
interface ConsensusData {
  query: string;
  studies_analyzed: number;
  consensus: "strong_support" | "moderate_support" | "mixed" | "moderate_against" | "strong_against" | "insufficient";
  support_percentage: number;
  study_breakdown: {
    rct: { support: number; against: number; neutral: number };
    observational: { support: number; against: number; neutral: number };
    qualitative: { support: number; against: number; neutral: number };
  };
}
```

**UI Visualization:**
```
╔══════════════════════════════════════════════════════╗
║  Scientific Consensus: Strong Support (85%)           ║
╠══════════════════════════════════════════════════════╣
║  ███████████████████░░░░  17/20 studies support      ║
║                                                       ║
║  By Study Type:                                       ║
║  • RCTs (8):     ████████░░  80% support             ║
║  • Quasi-exp (6): █████████░  90% support            ║
║  • Qualitative (6): ██████████ 100% support          ║
╚══════════════════════════════════════════════════════╝
```

**Backend Changes:**
1. Extend ClaimLedgerSynthesizer to track:
   - Number of studies cited
   - Study type per citation (from metadata)
   - Whether each citation supports/contradicts the answer
2. Return `consensus_data` in query response

**Effort:** ~16 hours
**Impact:** Very High - Makes DevChat uniquely useful for evidence synthesis

---

## 🚀 Priority 4: Agentic RAG (PaperQA2-Inspired)

### Current State
- Single-shot retrieval: query → retrieve → synthesize
- No iterative refinement or follow-up searches

### Improvement: Multi-Step Agentic Workflow

**PaperQA2 Algorithm Adaptation:**
```
1. Paper Search
   - Generate keyword queries from user question
   - Search vector DB for relevant chunks
   - OPTIONAL: Search external APIs (Semantic Scholar, OpenAlex)

2. Gather Evidence (Iterative)
   - For top-k chunks, create contextual summaries
   - LLM scores each summary for relevance
   - If relevance < threshold, search with refined query
   - Repeat until sufficient evidence OR max iterations

3. Generate Answer
   - Combine best summaries with claim-ledger synthesis
   - Include confidence score based on evidence quality
```

**New Agent Architecture:**
```python
class DevChatAgent:
    tools = [
        SearchTool(),      # Search within RAG collection
        GatherEvidenceTool(),  # Summarize and score chunks
        ExternalSearchTool(),  # Optional: search external APIs
        GenerateAnswerTool(),  # Final synthesis
    ]
    
    async def run(self, query: str, max_iterations: int = 3):
        # LLM decides tool sequence
        # Can iterate: search → gather → refine search → gather more → answer
```

**Benefits:**
- Better handling of complex, multi-part questions
- Can recognize when initial search is insufficient
- More thorough evidence coverage

**Effort:** ~20 hours
**Impact:** High - Significant quality improvement for complex queries

---

## 🚀 Priority 5: Systematic Review Automation (Elicit-Inspired)

### Current State
- Good for ad-hoc queries
- No structured workflow for systematic reviews

### Improvement: Systematic Review Mode

**New Feature: SR Workflow**
```
1. Define Protocol
   - Research question
   - Inclusion/exclusion criteria
   - Data extraction fields

2. Automated Screening
   - AI screens all documents against criteria
   - Confidence scores per document
   - Human reviews low-confidence cases

3. Data Extraction
   - AI extracts predefined fields from included studies
   - Side-by-side view: PDF + extraction form
   - Human validation with "Mark as validated" checkbox

4. Synthesis Report
   - Auto-generated evidence tables
   - Risk of bias summary
   - PRISMA flow diagram
```

**Database Schema:**
```sql
CREATE TABLE systematic_reviews (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES rag_projects(id),
    title TEXT,
    protocol JSONB,  -- {question, pico, criteria}
    status TEXT,     -- draft, screening, extraction, synthesis, complete
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sr_screenings (
    id UUID PRIMARY KEY,
    review_id UUID REFERENCES systematic_reviews(id),
    document_id UUID REFERENCES documents(id),
    ai_decision TEXT,  -- include, exclude, uncertain
    ai_confidence FLOAT,
    ai_reasoning TEXT,
    human_decision TEXT,
    human_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sr_extractions (
    id UUID PRIMARY KEY,
    review_id UUID REFERENCES systematic_reviews(id),
    document_id UUID REFERENCES documents(id),
    extracted_data JSONB,
    validated BOOLEAN DEFAULT FALSE,
    validated_by UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Effort:** ~40 hours
**Impact:** Very High - Opens enterprise/academic market

---

## 🚀 Priority 6: Multimodal Support (PaperQA2-Inspired)

### Current State
- Text-only extraction and synthesis
- Images and tables in PDFs are ignored

### Improvement: Image/Table Understanding

**PaperQA2 Approach:**
1. During PDF parsing, extract images and tables
2. Use vision LLM to generate "enrichment captions" for each
3. Store captions alongside text chunks
4. Include images in retrieval when relevant

**Implementation:**
```python
# During MinerU processing
async def extract_media(pdf_content: bytes) -> List[ParsedMedia]:
    """Extract images and tables with AI-generated captions."""
    media = []
    for page in pdf.pages:
        for image in page.images:
            caption = await vision_llm.describe(image, context=page.text)
            media.append(ParsedMedia(
                type="image",
                page=page.num,
                content=image,
                caption=caption,
                embedding=embed(caption)
            ))
    return media
```

**Storage:**
- Store media in R2 alongside PDFs
- Store captions + embeddings in Qdrant with `media_type` field
- Link media to text chunks via page number

**Synthesis Enhancement:**
- When a chunk is used, check for co-located media
- Pass media to vision-capable LLM during synthesis
- Citation format: "Figure 3 on page 12 shows..."

**Effort:** ~24 hours
**Impact:** High - Captures information lost in text-only extraction

---

## 🚀 Priority 7: Research Reports (Elicit-Inspired)

### Current State
- Single-question Q&A
- No structured report generation

### Improvement: Auto-Generated Research Reports

**New Feature: Research Reports**
```
User Input:
- Topic: "Impact of cash transfer programs on child nutrition in Sub-Saharan Africa"
- Report type: Literature review | Evidence map | Policy brief
- Depth: Quick (10 papers) | Standard (30 papers) | Comprehensive (100 papers)

Output:
- Executive summary
- Methodology section
- Findings organized by theme
- Evidence tables
- Gap analysis
- Bibliography
```

**Implementation:**
```python
class ResearchReportGenerator:
    async def generate(self, topic: str, depth: int, report_type: str):
        # 1. Generate search queries for different aspects
        queries = await self.decompose_topic(topic)
        
        # 2. Gather evidence for each query
        evidence = {}
        for query in queries:
            evidence[query] = await self.gather_evidence(query, k=depth)
        
        # 3. Identify themes via clustering
        themes = await self.cluster_evidence(evidence)
        
        # 4. Generate report sections
        sections = []
        for theme in themes:
            section = await self.synthesize_theme(theme)
            sections.append(section)
        
        # 5. Generate executive summary
        summary = await self.generate_summary(sections)
        
        return ResearchReport(summary=summary, sections=sections)
```

**Output Formats:**
- Markdown (for editing)
- PDF (for sharing)
- Word (for academic submission)

**Effort:** ~30 hours
**Impact:** Very High - Major differentiation from competitors

---

## 🚀 Priority 8: Embeddable Widget (Humata-Inspired)

### Current State
- DevChat only accessible via dedicated UI
- No way to embed in external sites

### Improvement: Embeddable Chat Widget

**Use Case:** 3ie embeds a "Research Assistant" on their evidence portal

**Implementation:**
```html
<!-- Embed code for external sites -->
<script src="https://devchat.3ieimpact.org/widget.js"></script>
<div id="devchat-widget" 
     data-project="graduation-programs"
     data-theme="light"
     data-position="bottom-right">
</div>
```

**Widget Features:**
- Floating chat button → opens chat panel
- Answers grounded in the specified RAG collection
- Branded with 3ie/partner colors
- Optional: require login for full access

**Backend Changes:**
- New endpoint: `POST /api/widget/query` (CORS-enabled)
- Widget API key for authentication
- Rate limiting per widget key

**Effort:** ~16 hours
**Impact:** Medium - Extends reach beyond direct users

---

## ✅ Priority 9: Study Design Classification (Consensus-Inspired) - COMPLETE

### Implementation (January 7, 2026)
- ✅ `StudyDesign` enum created with 22 comprehensive design types
- ✅ Evidence weights defined (RCT=1.0, DiD=0.8, Qualitative=0.4, etc.)
- ✅ LLM classification prompt and service implemented
- ✅ Classification script: `scripts/run_study_design_classification.py`
- ✅ Qdrant full-text fallback when abstract missing
- ✅ Frontend `StudyDesignBadge` component with color-coded badges
- ✅ 96 documents classified (81 with design, 15 unknown)
- ⏳ Pending: Study design filter dropdown in Evidence panel
- ⏳ Pending: Integrate into ingestion pipeline for auto-classification

### Implementation Files:
- `src/config/study_designs.py` - Full taxonomy with 22 design types + evidence weights
- `src/ingestion/study_design_classifier.py` - LLM classification with Qdrant fallback
- `scripts/run_study_design_classification.py` - Batch classification script
- `frontend/src/components/workbench/StudyDesignBadge.tsx` - Color-coded badge component

### Classification Results (96 documents):
| Study Design | Count |
|--------------|-------|
| RCT | 34 |
| Unknown | 15 |
| Difference-in-Differences | 10 |
| Qualitative | 7 |
| Theory | 6 |
| Panel | 4 |
| Cluster RCT | 4 |
| Cohort | 3 |
| Descriptive | 3 |
| Other designs | 10 |

**Effort:** ~8h (complete)
**Impact:** High - Critical for evidence quality assessment

---

## 🚀 Priority 10: Document Enrichment Pipeline (Structured Data Extraction)

### Overview
A unified pipeline that runs **after PDF processing** to extract structured, searchable metadata from documents. This enables quantitative queries, filtering by geography/intervention, and meta-analysis preparation.

### Current State
- ✅ MinerU extracts text from PDFs with good quality
- ✅ CrossRef/OpenAlex enrichment for bibliographic metadata
- ✅ Study Design Classification (just built - needs pipeline integration)
- ❌ Tables converted to markdown but not structured
- ❌ Effect sizes, sample sizes, outcomes not extracted
- ❌ No ability to answer quantitative queries

### Architecture: Document Enrichment Pipeline

```
PDF Upload → MinerU Extract → Metadata Resolve → ENRICHMENT PIPELINE → Index to Qdrant
                                                        ↓
                                              ┌─────────────────────┐
                                              │  Enrichment Agents  │
                                              ├─────────────────────┤
                                              │ 1. Study Design     │ ← Already built!
                                              │ 2. Geography        │
                                              │ 3. Intervention     │
                                              │ 4. Effect Sizes     │
                                              │ 5. Sample/Methods   │
                                              └─────────────────────┘
                                                        ↓
                                              Store in documents.metadata
                                              + Qdrant payload for filtering
```

### Implementation Location
**File:** `infrastructure/modal_mineru.py` - line ~1159

```python
# After: enriched_metadata = resolve_metadata(...)
# Before: embed_and_index(...)

# NEW: Document Enrichment Pipeline
enriched_metadata = await run_enrichment_pipeline(
    content=result["content"],
    metadata=enriched_metadata,
    tables=result.get("tables", []),  # If MinerU extracts tables
)
```

---

### Enrichment Agent 1: Study Design Classification ✅ READY

**Status:** Code complete, needs Modal integration

**Files:**
- `src/config/study_designs.py` - 22 design types with evidence weights
- `src/ingestion/study_design_classifier.py` - LLM classifier

**Integration:**
```python
from src.ingestion.study_design_classifier import classify_study_design

study_design, confidence, reasoning = await classify_study_design(
    title=metadata.get("title"),
    abstract=metadata.get("abstract") or content[:8000]  # Fallback to full text
)
enriched_metadata["study_design"] = study_design
enriched_metadata["study_design_confidence"] = confidence
enriched_metadata["study_design_reasoning"] = reasoning
```

**Effort:** 2h (just integration)

---

### Enrichment Agent 2: Geographic Extraction

**Goal:** Extract countries, regions, and geographic scope

**Output Schema:**
```python
@dataclass
class GeographicExtraction:
    countries: List[str]           # ["Bangladesh", "Ethiopia", "Peru"]
    regions: List[str]             # ["South Asia", "Sub-Saharan Africa"]
    sub_national: List[str]        # ["Punjab province", "Oromia region"]
    urban_rural: str               # "urban", "rural", "mixed", "unknown"
    geographic_scope: str          # "single_country", "multi_country", "global"
```

**Prompt Template:**
```
Extract geographic information from this research document.

Title: {title}
Abstract: {abstract}

Return JSON:
{
    "countries": ["list of countries where study was conducted"],
    "regions": ["geographic regions (e.g., South Asia, Sub-Saharan Africa)"],
    "sub_national": ["provinces, states, districts if mentioned"],
    "urban_rural": "urban|rural|mixed|unknown",
    "geographic_scope": "single_country|multi_country|global"
}
```

**Validation:** Cross-check extracted countries against known country list

**Effort:** 4h

---

### Enrichment Agent 3: Intervention Extraction

**Goal:** Extract intervention details for filtering and comparison

**Output Schema:**
```python
@dataclass
class InterventionExtraction:
    intervention_type: str          # From taxonomy: "cash_transfer", "training", etc.
    intervention_category: str      # "social_protection", "education", "health"
    intervention_description: str   # Brief description
    transfer_amount: Optional[str]  # "$20/month", "500 USD lump sum"
    transfer_frequency: str         # "monthly", "quarterly", "lump_sum"
    duration_months: Optional[int]  # 24
    conditionality: str             # "conditional", "unconditional", "labeled"
    target_population: str          # "Ultra-poor households", "Adolescent girls"
    implementing_org: Optional[str] # "BRAC", "Government of Ethiopia"
```

**Intervention Taxonomy:**
```python
INTERVENTION_TYPES = [
    # Social Protection
    "cash_transfer", "asset_transfer", "food_transfer", "voucher",
    # Livelihoods
    "skills_training", "financial_literacy", "savings_group", "microcredit",
    # Education
    "school_feeding", "scholarship", "teacher_training", "curriculum",
    # Health
    "nutrition_supplement", "vaccination", "health_education", "facility_upgrade",
    # Agriculture
    "input_subsidy", "extension_service", "irrigation", "market_access",
    # Governance
    "information_campaign", "community_mobilization", "decentralization",
    # Infrastructure
    "road_construction", "electrification", "water_sanitation",
    # Other
    "multi_component", "unknown"
]
```

**Effort:** 6h

---

### Enrichment Agent 4: Effect Size Extraction

**Goal:** Extract quantitative results for meta-analysis and comparison

**Output Schema:**
```python
@dataclass
class EffectSizeExtraction:
    outcome: str                    # "household_consumption", "school_enrollment"
    outcome_category: str           # "economic", "education", "health"
    effect_size: float              # 0.23
    effect_type: str                # "smd", "percentage_point", "odds_ratio", "percent_change"
    confidence_interval: tuple      # (0.15, 0.31)
    standard_error: Optional[float] # 0.04
    p_value: Optional[float]        # 0.001
    significance: str               # "significant", "not_significant", "marginal"
    sample_size_treatment: int      # 1500
    sample_size_control: int        # 1500
    timepoint: str                  # "12_months", "24_months", "endline"
    subgroup: Optional[str]         # "female_headed", "bottom_tercile"
    table_source: Optional[str]     # "Table 3, Column 2"
```

**Extraction Strategy:**
1. **Table Detection:** Identify results tables in document
2. **Table Parsing:** Extract structured data from markdown tables
3. **LLM Interpretation:** Have LLM interpret each row
4. **Validation:** Check numeric values are plausible (effect sizes typically -2 to 2 for SMD)

**Effort:** 12h (most complex agent)

---

### Enrichment Agent 5: Sample & Methods Extraction

**Goal:** Extract methodological details for evidence assessment

**Output Schema:**
```python
@dataclass
class MethodsExtraction:
    sample_size_total: int          # 3000
    sample_size_treatment: int      # 1500
    sample_size_control: int        # 1500
    unit_of_randomization: str      # "individual", "household", "village", "school"
    attrition_rate: Optional[float] # 0.08
    baseline_year: Optional[int]    # 2013
    endline_year: Optional[int]     # 2016
    data_sources: List[str]         # ["household_survey", "admin_data", "qualitative"]
    pre_registered: Optional[bool]  # True
    pre_registration_id: Optional[str]  # "AEARCTR-0000123"
```

**Effort:** 6h

---

### Quantitative Query Agent

**Goal:** Answer queries using structured metadata

**Example Queries:**
| Query | Uses | Response |
|-------|------|----------|
| "What are effect sizes for cash transfers on school enrollment?" | effect_sizes + intervention_type | Table of effects |
| "Which countries have graduation program studies?" | countries + intervention_type | Country list |
| "Compare RCT vs quasi-experimental effects" | study_design + effect_sizes | Comparison table |
| "Show studies with sample size > 1000" | sample_size | Filtered list |
| "What's the average effect on consumption?" | effect_sizes + outcome | Aggregate stats |

**Implementation:**
```python
class QuantitativeQueryAgent:
    tools = [
        FilterByMetadataTool(),       # Filter docs by structured fields
        AggregateEffectsTool(),       # Calculate averages, ranges
        CompareGroupsTool(),          # Compare by study design, country
        GenerateTableTool(),          # Format results as table
        GenerateForestPlotTool(),     # Visual effect size display
    ]
```

**Effort:** 10h

---

### Accuracy & Validation Strategy

**Problem:** LLM extraction can hallucinate or make errors

**Solutions:**

1. **Confidence Scoring:**
   - Each extraction includes confidence score (0-1)
   - Low confidence items flagged for human review
   - UI shows confidence badges

2. **Source Validation:**
   - For effect sizes: validate against plausible ranges
   - For countries: validate against known country list
   - For years: validate in reasonable range (1990-2026)

3. **Human-in-the-Loop:**
   - Metadata Review UI already exists
   - Add "Extracted Fields" tab showing all enrichments
   - Mark as reviewed checkbox for each section

4. **Cross-Validation:**
   - Compare extracted DOI metadata with LLM extraction
   - Flag discrepancies for review

5. **Batch Quality Checks:**
   - Periodic sampling of extractions
   - Compute accuracy on validated subset
   - Retrain prompts if accuracy drops

---

### Storage Schema Update

```python
# documents.metadata JSONB
{
    # Existing bibliographic
    "title": "...",
    "authors": [...],
    "doi": "...",
    
    # NEW: Study Design (already implemented)
    "study_design": "rct",
    "study_design_confidence": 0.95,
    "study_design_reasoning": "...",
    
    # NEW: Geographic
    "countries": ["Bangladesh", "Ethiopia"],
    "regions": ["South Asia", "Sub-Saharan Africa"],
    "urban_rural": "rural",
    
    # NEW: Intervention
    "intervention_type": "graduation_program",
    "intervention_category": "social_protection",
    "transfer_amount": "USD 500 asset + 24 months stipend",
    "target_population": "Ultra-poor households",
    
    # NEW: Effects (array)
    "effect_sizes": [
        {
            "outcome": "household_consumption",
            "outcome_category": "economic",
            "effect": 0.23,
            "effect_type": "smd",
            "ci_lower": 0.15,
            "ci_upper": 0.31,
            "timepoint": "36_months",
            "extraction_confidence": 0.85
        }
    ],
    
    # NEW: Methods
    "sample_size_treatment": 1500,
    "sample_size_control": 1500,
    "baseline_year": 2013,
    "endline_year": 2016,
    
    # NEW: Quality flags
    "enrichment_status": "complete",  # "pending", "partial", "complete", "failed"
    "enrichment_reviewed": false,
    "enrichment_timestamp": "2026-01-07T..."
}
```

---

### Frontend Enhancements

1. **Metadata Review Tab:**
   - Show all extracted fields with confidence badges
   - Edit/correct any extraction
   - "Mark as Reviewed" per section

2. **Study Cards:**
   - Display study design badge (already done)
   - Add country flags/chips
   - Show effect size summary

3. **Evidence Panel Filters:**
   - Filter by study design (dropdown)
   - Filter by country (multi-select)
   - Filter by intervention type
   - Filter by effect size range

4. **Quantitative View:**
   - Effect size comparison table
   - Forest plot visualization
   - Export to CSV for meta-analysis

---

### Implementation Roadmap

| Phase | Agent | Effort | Dependencies |
|-------|-------|--------|--------------|
| 1a | Study Design Integration | 2h | Already built |
| 1b | Geographic Extraction | 4h | None |
| 1c | Frontend filters | 4h | 1a, 1b |
| 2a | Intervention Extraction | 6h | None |
| 2b | Methods Extraction | 6h | None |
| 3a | Effect Size Extraction | 12h | Table parsing |
| 3b | Quantitative Query Agent | 10h | 3a |
| 3c | Forest Plot UI | 6h | 3a, 3b |
| 4 | Validation & Review UI | 8h | All above |
| **Total** | | **58h** | |

### Priority Order
1. **Study Design + Geography** (10h) - Quick wins, high value for filtering
2. **Intervention + Methods** (12h) - Important for comparison queries
3. **Effect Sizes + Quantitative Agent** (28h) - Complex but transformative
4. **Validation & Review** (8h) - Critical for accuracy

---

### Impact Summary
- **Very High** - Enables quantitative evidence synthesis
- Unique differentiator: No competitor does structured effect extraction
- Opens door to automated meta-analysis preparation
- Enables queries like "What's the average effect of cash transfers on school enrollment across RCTs in Sub-Saharan Africa?"

---

## 🚀 Priority 11: Haystack Integration (Future Architecture)

### Current State
- Custom-built pipeline with Cohere + Qdrant + OpenRouter

### Improvement: Adopt Haystack for Pipeline Orchestration

**Benefits of Haystack:**
- Production-ready component library
- Built-in support for agents and tools
- Easy swapping of LLMs, embedders, retrievers
- Active community and enterprise support

**Migration Path:**
```python
from haystack import Pipeline
from haystack.components.retrievers import QdrantEmbeddingRetriever
from haystack.components.generators import OpenAIGenerator
from haystack.components.builders import PromptBuilder

# DevChat pipeline in Haystack
pipeline = Pipeline()
pipeline.add_component("retriever", QdrantEmbeddingRetriever(...))
pipeline.add_component("reranker", CohereReranker(...))
pipeline.add_component("prompt", PromptBuilder(template=CLAIM_LEDGER_TEMPLATE))
pipeline.add_component("llm", OpenAIGenerator(model="gpt-4o"))

pipeline.connect("retriever", "reranker")
pipeline.connect("reranker", "prompt")
pipeline.connect("prompt", "llm")
```

**Custom Components to Create:**
- `ClaimLedgerExtractor`: Extracts claims from chunks
- `ClaimLedgerSynthesizer`: Synthesizes grounded response
- `ConsensusCalculator`: Calculates evidence agreement
- `CitationHighlighter`: Generates highlighted PDFs

**Effort:** ~40 hours (major refactor)
**Impact:** Medium-term - Better maintainability and extensibility

---

## 📊 Implementation Roadmap

### Phase 1: Quick Wins (Week 1-2)
| Feature | Effort | Impact | Status |
|---------|--------|--------|--------|
| ~~PDF Citation Highlighting~~ | ~~4h~~ | High | ✅ Done |
| ~~Study Design Classification~~ | ~~8h~~ | High | ✅ Done |
| **Total** | **0h remaining** | | |

### Phase 2: Evidence Quality (Week 3-6)
| Feature | Effort | Impact |
|---------|--------|--------|
| Document Enrichment Pipeline | 58h | Very High |
| Smart Citations (support/contrast) | 12h | Very High |
| Consensus Meter | 16h | Very High |
| **Total** | **86h** | |

### Phase 3: Advanced Features (Month 2)
| Feature | Effort | Impact |
|---------|--------|--------|
| Agentic RAG | 20h | High |
| Multimodal Support | 24h | High |
| Embeddable Widget | 16h | Medium |
| **Total** | **60h** | |

### Phase 4: Enterprise Features (Month 3-4)
| Feature | Effort | Impact |
|---------|--------|--------|
| Systematic Review Workflow | 40h | Very High |
| Research Reports | 30h | Very High |
| Haystack Migration | 40h | Medium |
| **Total** | **110h** | |

---

## 🏆 Competitive Positioning

After implementing these improvements, DevChat would:

| Capability | DevChat | Elicit | Scite | Consensus | PaperQA2 |
|------------|---------|--------|-------|-----------|----------|
| Grounded citations with pages | ✅ | ⚠️ | ✅ | ⚠️ | ✅ |
| PDF highlighting | ✅ | ❌ | ❌ | ❌ | ❌ |
| Smart citations (support/contrast) | ✅ | ❌ | ✅ | ❌ | ❌ |
| Consensus visualization | ✅ | ❌ | ❌ | ✅ | ❌ |
| Study design classification | ✅ | ⚠️ | ❌ | ✅ | ❌ |
| Custom document collections | ✅ | ❌ | ❌ | ❌ | ✅ |
| Systematic review workflow | ✅ | ✅ | ❌ | ❌ | ❌ |
| Research report generation | ✅ | ✅ | ❌ | ❌ | ⚠️ |
| Agentic multi-step RAG | ✅ | ⚠️ | ❌ | ❌ | ✅ |
| Multimodal (images/tables) | ✅ | ❌ | ❌ | ❌ | ✅ |
| Embeddable widget | ✅ | ❌ | ❌ | ❌ | ❌ |
| Development research focus | ✅ | ❌ | ❌ | ❌ | ❌ |

**Unique Value Proposition:**
> DevChat is the only AI research assistant purpose-built for development research, combining grounded citations, consensus visualization, and systematic review automation—all within your own curated evidence collections.

---

## 📚 References

- [PaperQA2 GitHub](https://github.com/future-house/paper-qa) - Superhuman RAG for scientific papers
- [Haystack Docs](https://docs.haystack.deepset.ai/) - Production AI pipeline framework
- [Elicit](https://elicit.com/) - Systematic review automation
- [Scite](https://scite.ai/) - Smart Citations platform
- [Consensus](https://consensus.app/) - Scientific consensus search
- [Humata](https://humata.ai/) - PDF Q&A assistant
- [PyMuPDF Highlighting](https://medium.com/@pymupdf/highlighting-text-with-pymupdf-08b228044da7) - PDF text highlighting

---

*This document is a living roadmap. Priorities may shift based on user feedback and strategic direction.*
