# DevChat v2 - Further Improvements Roadmap

**Purpose:** Map features from leading AI research tools to make DevChat the best-in-class evidence synthesis platform for development research.

**Date:** January 6, 2026

---

## 🎯 Executive Summary

After analyzing seven leading AI research platforms, this document maps actionable improvements for DevChat. The goal: become the **definitive tool for evidence-based development research**, combining the best features from:

| Tool | Key Strength | What We Can Learn |
|------|--------------|-------------------|
| **PaperQA2** | Superhuman scientific QA with grounded citations | Agentic RAG, contextual summarization, multimodal support |
| **Haystack** | Modular, production-ready AI pipelines | Component architecture, agents, enterprise scalability |
| **Elicit** | Systematic review automation at scale | Research reports, screening workflows, 1000+ paper analysis |
| **Scite** | Smart Citations (supporting/contrasting) | Citation context classification, evidence quality scoring |
| **Consensus** | Visual consensus meters, study design filters | Meta-analysis visualization, study type classification |
| **Humata** | Simple Q&A with highlighted citations | PDF highlighting, embeddable widgets |
| **PyMuPDF** | Programmatic PDF text highlighting | Visual citation evidence in PDFs |

---

## 🚀 Priority 1: Citation Highlighting in PDFs (Quick Win)

### Current State
- Users can click citations to open PDFs at the right page
- No visual highlighting of the exact text that supports the claim

### Improvement: PyMuPDF Text Highlighting
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

## 🚀 Priority 9: Study Design Classification (Consensus-Inspired)

### Current State
- `item_type` field captures document type (article, report, etc.)
- No classification of study design/methodology

### Improvement: Auto-Classify Study Design

**New Metadata Fields:**
```python
class StudyDesign(str, Enum):
    RCT = "randomized_controlled_trial"
    QUASI_EXPERIMENTAL = "quasi_experimental"
    REGRESSION_DISCONTINUITY = "regression_discontinuity"
    DIFFERENCE_IN_DIFFERENCES = "difference_in_differences"
    INSTRUMENTAL_VARIABLE = "instrumental_variable"
    PROPENSITY_SCORE = "propensity_score_matching"
    INTERRUPTED_TIME_SERIES = "interrupted_time_series"
    OBSERVATIONAL = "observational"
    QUALITATIVE = "qualitative"
    MIXED_METHODS = "mixed_methods"
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    MODELING = "modeling_simulation"
    DESCRIPTIVE = "descriptive"
```

**Classification Prompt:**
```
Analyze this research paper abstract and methodology section.
Classify the primary study design using this hierarchy:

EXPERIMENTAL:
- Randomized Controlled Trial (RCT): Random assignment to treatment/control
- Cluster RCT: Randomization at group level

QUASI-EXPERIMENTAL:
- Regression Discontinuity: Cutoff-based assignment
- Difference-in-Differences: Before/after with comparison group
- Instrumental Variable: Uses exogenous variation
- Propensity Score Matching: Statistical matching

OBSERVATIONAL:
- Cohort study: Follows groups over time
- Cross-sectional: Point-in-time measurement

... [full taxonomy]

Return: {"study_design": "...", "confidence": 0.0-1.0, "evidence_snippets": [...]}
```

**UI Enhancement:**
- Filter documents by study design in metadata view
- Weight RCTs higher in consensus calculations
- Show study design badges on citations

**Effort:** ~8 hours
**Impact:** High - Critical for evidence quality assessment

---

## 🚀 Priority 10: Haystack Integration (Future Architecture)

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
| Feature | Effort | Impact |
|---------|--------|--------|
| PDF Citation Highlighting | 4h | High |
| Study Design Classification | 8h | High |
| **Total** | **12h** | |

### Phase 2: Evidence Quality (Week 3-4)
| Feature | Effort | Impact |
|---------|--------|--------|
| Smart Citations (support/contrast) | 12h | Very High |
| Consensus Meter | 16h | Very High |
| **Total** | **28h** | |

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
