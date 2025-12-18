# DevChat v2.0 SOTA - Setup & Debug Tracker

**Created:** December 17, 2025  
**Last Updated:** December 18, 2025  
**Status:** ✅ COMPLETE - Full RAG Pipeline + UI + Production PDF Processing Working

---

## 📋 Overview

This document tracks every step of setting up and debugging the DevChat v2.0 SOTA RAG system.

---

## 🔑 Prerequisites Checklist

### API Keys Required
- [x] **OpenRouter API Key** - ✅ Configured
- [x] **Cohere API Key** - ✅ Configured

### Optional API Keys
- [x] Langfuse (observability) - ✅ Configured
- [x] Voyage AI (alternative embeddings) - ✅ Configured
- [ ] Anthropic (fallback) - Not configured
- [ ] OpenAI (fallback) - Not configured

### Infrastructure
- [x] Qdrant Vector Database - ✅ Qdrant Cloud (EU region)
- [x] Python 3.12 - ✅ Installed
- [ ] Docker (optional, for containerized deployment)

---

## 📦 Phase 1: Environment Setup ✅ COMPLETE

### Step 1.1: Install Dependencies ✅
```powershell
pip install -r requirements.txt
pip install llama-index-llms-openai-like  # Added for OpenRouter
```

**Status:** ✅ Complete  
**Date Completed:** Dec 17, 2025  
**Notes:** All dependencies installed successfully

---

### Step 1.2: Configure Environment Variables ✅
**Status:** ✅ Complete  
**Date Completed:** Dec 17, 2025  
**Notes:** .env file created with all keys

---

### Step 1.3: Verify Settings Load Correctly ✅
**Status:** ✅ Complete  
**Date Completed:** Dec 17, 2025  
**Output:**
```
Settings loaded!
Provider: LLMProvider.OPENROUTER
```

---

### Step 1.4: Test API Connections ✅

| Service | Status | Notes |
|---------|--------|-------|
| Qdrant Cloud | ✅ | Connected to EU cluster |
| Cohere Embeddings | ✅ | embed-v4.0 working (dim=1536) |
| OpenRouter LLM | ✅ | GPT-4o-mini working |
| OpenRouter Reasoning | ✅ | GPT-4o working |

**Note:** Claude models via OpenRouter hit rate limits (free tier). Switched to OpenAI models which have better availability.  

---

### Step 2.2: Verify Qdrant Connection
```powershell
# Test Qdrant connection
python -c "from qdrant_client import QdrantClient; client = QdrantClient('http://localhost:6333'); print('Connected!'); print(client.get_collections())"
```

**Expected Output:**
```
Connected!
CollectionsResponse(collections=[])
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

## 📄 Phase 3: Document Ingestion

### Step 3.1: Prepare Source Documents
- [ ] Place markdown files in `./data/markdown/`
- [ ] Create metadata CSV in `./data/metadata.csv`

**PDF Source:** https://3ie.sharepoint.com/:f:/s/DEPChatbot/IgCdLWmj1g8OR5L-m5ikM-dfAZN8J2CFCpv_B5EPwZKy28o?e=hB8isv

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

### Step 3.2: Test Document Loader
```powershell
# Test document loading
python -c "
from src.ingestion.document_loader import DocumentLoader
loader = DocumentLoader()
docs = loader.load_all()
print(f'Loaded {len(docs)} documents')
if docs:
    print(f'First doc metadata: {docs[0].metadata}')
"
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

### Step 3.3: Run Full Ingestion
```powershell
# Run ingestion script
python scripts/ingest_documents.py --source ./data/markdown --collection devchat_v2
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

## 🔍 Phase 4: Retrieval Testing

### Step 4.1: Test Embeddings
```powershell
# Test Cohere embeddings
python -c "
from src.ingestion.embeddings import get_embedding_model
embed = get_embedding_model()
result = embed.get_text_embedding('test query')
print(f'Embedding dimension: {len(result)}')
print(f'First 5 values: {result[:5]}')
"
```

**Expected:** Embedding dimension should be 1024

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

### Step 4.2: Test Query Processing
```powershell
# Test query processor
python -c "
import asyncio
from src.retrieval.query_processor import QueryProcessor
processor = QueryProcessor()
result = asyncio.run(processor.process('What is the impact of cash transfers on education?'))
print(f'Query Type: {result.query_type}')
print(f'Expanded: {result.expanded_queries}')
"
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

### Step 4.3: Test Retrieval
```powershell
# Test hybrid retrieval
python -c "
import asyncio
from src.retrieval.hybrid_retriever import HybridRetriever
retriever = HybridRetriever()
results = asyncio.run(retriever.retrieve('cash transfers education'))
print(f'Retrieved {len(results)} chunks')
"
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

## 🤖 Phase 5: LLM Generation Testing

### Step 5.1: Test OpenRouter Connection
```powershell
# Test LLM via OpenRouter
python -c "
from src.generation.router import ModelRouter
router = ModelRouter()
from src.retrieval.query_processor import QueryType
from src.generation.router import RoutingDecision, ModelTier

decision = router.route(QueryType.SIMPLE, context_length=1000, num_studies=2)
print(f'Routed to: {decision.model_name}')

llm = router.get_llm(decision)
print(f'LLM created: {type(llm).__name__}')
"
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

### Step 5.2: Test Simple Generation
```powershell
# Test LLM generation
python -c "
import asyncio
from src.generation.router import ModelRouter
from src.retrieval.query_processor import QueryType

router = ModelRouter()
decision = router.route(QueryType.SIMPLE)
llm = router.get_llm(decision)

response = asyncio.run(llm.acomplete('Say hello in one sentence.'))
print(f'Response: {response.text}')
"
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

## 🎨 Phase 6: Research Workbench UI (Next.js Frontend)

**Status:** ✅ COMPLETE - Connected to Backend  
**Started:** Dec 18, 2025  
**Completed:** Dec 18, 2025  
**Frontend Location:** `frontend/`

---

### ✅ Completed Components

| Component | File | Description | Status |
|-----------|------|-------------|--------|
| Split Layout | `SplitLayout.tsx` | Resizable Answer/Evidence panels | ✅ Done |
| Answer Panel | `AnswerPanel.tsx` | Structured response with [1][2] clickable citations | ✅ Done |
| Evidence Panel | `EvidencePanel.tsx` | Scrollable study cards + CSV/JSON export | ✅ Done |
| Study Card | `StudyCard.tsx` | Title, year, country, snippet, Compare/Exclude/PDF | ✅ Done |
| Filter Chips | `FilterChips.tsx` | Active filters with ✕ to remove | ✅ Done |
| Filter Drawer | `FilterDrawer.tsx` | Add filters (Country, Sector, Year, etc.) | ✅ Done |
| Settings Drawer | `SettingsDrawer.tsx` | Relevance threshold, max studies, answer style | ✅ Done |
| Compare Modal | `CompareModal.tsx` | Side-by-side study comparison + CSV export | ✅ Done |
| Search Input | `SearchInput.tsx` | Query input with loading state | ✅ Done |
| Evidence Health | `AnswerPanel.tsx` | Coverage signals, gaps detected (embedded) | ✅ Done |
| Query Coaching | `AnswerPanel.tsx` | "Try next" suggestions (embedded) | ✅ Done |

### 📦 Tech Stack Installed

```json
{
  "next": "^16.0.10",
  "react": "^19.1.0",
  "typescript": "^5.8.3",
  "tailwindcss": "^4.1.8",
  "react-resizable-panels": "^2.1.9",
  "lucide-react": "^0.513.0"
}
```

**shadcn/ui components:** button, card, badge, input, scroll-area, separator, sheet, dialog, table, tabs, tooltip, resizable, slider, switch, select, label

---

### 🔌 Frontend-Backend Wiring Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js @ :3000)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  SearchInput ──┬── SettingsDrawer ── FilterDrawer                       │
│       │        │         │                │                              │
│       │        └─────────┼────────────────┘                              │
│       ▼                  ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ page.tsx::handleSearch(query, filters, settings)                 │    │
│  │ → api.queryEvidence(query, filters, settings)                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                 │                                        │
└─────────────────────────────────┼────────────────────────────────────────┘
                                  │ POST /api/query
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI @ :8000)                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  POST /api/query                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Request:                                                           │  │
│  │ {                                                                  │  │
│  │   "query": "What are effects of cash transfers?",                 │  │
│  │   "filters": [{"type": "country", "value": "kenya"}],             │  │
│  │   "settings": {                                                    │  │
│  │     "relevanceThreshold": 0.5,                                     │  │
│  │     "maxStudies": 10,                                              │  │
│  │     "answerStyle": "executive",                                    │  │
│  │     "useReranking": true,                                          │  │
│  │     "minConfidence": "all"                                         │  │
│  │   }                                                                │  │
│  │ }                                                                  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                 │                                        │
│  ┌──────────────────────────────▼────────────────────────────────────┐  │
│  │                      RAG PIPELINE                                  │  │
│  │  1. Query Processing (expand, classify, extract filters)          │  │
│  │  2. Hybrid Retrieval (dense + sparse + metadata filters)          │  │
│  │  3. Reranking (Cohere rerank-v3.5)                                │  │
│  │  4. Context Building (dedupe, attach citations)                   │  │
│  │  5. Synthesis (route to fast/reasoning model)                     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                 │                                        │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Response:                                                          │  │
│  │ {                                                                  │  │
│  │   "answer": "Based on the evidence... [1] found...",              │  │
│  │   "citations": [{id: 1, studyId: "TEST001", text: "...", ...}],   │  │
│  │   "studies": [{id, title, authors, year, country, ...}],          │  │
│  │   "suggestions": ["Narrow to Sub-Saharan Africa?", ...],          │  │
│  │   "evidenceHealth": {studyCount: 6, dateRange: "2018-2024", ...}  │  │
│  │ }                                                                  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 🔧 API Endpoints Required

| Endpoint | Method | Purpose | Frontend Usage | Backend Status |
|----------|--------|---------|----------------|----------------|
| `/api/query` | POST | Main search | `handleSearch()` | ✅ Complete |
| `/api/compare` | POST | Compare studies | `CompareModal` | ⬜ TODO |
| `/api/suggest` | POST | Query coaching | `handleSuggestionClick()` | ⬜ TODO |
| `/api/export` | POST | PDF/Word export | `EvidencePanel` | ⬜ TODO |
| `/api/filters` | GET | Available options | `FilterDrawer` | ✅ Complete |

---

### 📋 Backend Wiring Checklist

#### Step 1: Update API Schemas (api/schemas.py)

```python
from pydantic import BaseModel
from typing import List, Optional

# Request schemas
class FilterInput(BaseModel):
    type: str  # country, sector, studyType, yearRange, confidence
    value: str

class SearchSettings(BaseModel):
    relevanceThreshold: float = 0.5
    maxStudies: int = 10
    answerStyle: str = "executive"
    useReranking: bool = True
    minConfidence: str = "all"
    yearCutoff: int = 2010

class QueryRequest(BaseModel):
    query: str
    filters: Optional[List[FilterInput]] = None
    settings: Optional[SearchSettings] = None

# Response schemas
class Study(BaseModel):
    id: str
    title: str
    authors: str
    year: int
    country: str
    sector: str
    studyType: str
    confidence: str
    snippet: str
    score: float
    pdfUrl: Optional[str] = None

class Citation(BaseModel):
    id: int
    studyId: str
    text: str
    study: Study

class EvidenceHealth(BaseModel):
    studyCount: int
    dateRange: str
    gaps: List[str]
    coverageWarning: Optional[str] = None

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    studies: List[Study]
    suggestions: List[str]
    evidenceHealth: EvidenceHealth
```

#### Step 2: Add CORS (api/server.py)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### Step 3: Update page.tsx to use real API

```typescript
// Replace mock data simulation with:
const handleSearch = useCallback(async (searchQuery: string) => {
  setIsLoading(true);
  try {
    const response = await queryEvidence(searchQuery, filters, searchSettings);
    setStudies(response.studies);
    setCitations(response.citations);
    setAnswer(response.answer);
    setSuggestions(response.suggestions);
    setEvidenceHealth(response.evidenceHealth);
  } catch (error) {
    console.error("Search failed:", error);
  } finally {
    setIsLoading(false);
  }
}, [filters, searchSettings]);
```

#### Step 4: Environment variables

**Frontend (frontend/.env.local):**
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

### 🚀 Running Both Services

**Terminal 1 - Backend:**
```powershell
cd devchat_v2_sota
.\venv\Scripts\Activate.ps1
uvicorn api.server:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```powershell
cd devchat_v2_sota/frontend
npm run dev
```

**Access:**
- Frontend: http://localhost:3000
- Backend Swagger: http://localhost:8000/docs

---

### 🗂️ Frontend File Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx           # Root layout
│   │   ├── page.tsx             # Main Research Workbench page
│   │   └── globals.css          # Tailwind imports
│   │
│   ├── components/
│   │   ├── ui/                  # shadcn/ui components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── badge.tsx
│   │   │   ├── input.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── sheet.tsx
│   │   │   ├── slider.tsx
│   │   │   ├── switch.tsx
│   │   │   ├── select.tsx
│   │   │   └── ...
│   │   │
│   │   └── workbench/           # Custom components
│   │       ├── index.ts         # Barrel export
│   │       ├── SplitLayout.tsx  # Resizable panels
│   │       ├── AnswerPanel.tsx  # Left panel (answer + citations)
│   │       ├── EvidencePanel.tsx# Right panel (study cards)
│   │       ├── StudyCard.tsx    # Individual study card
│   │       ├── FilterChips.tsx  # Active filter badges
│   │       ├── FilterDrawer.tsx # Add filter sheet
│   │       ├── SettingsDrawer.tsx# Search settings sheet
│   │       ├── CompareModal.tsx # Study comparison dialog
│   │       └── SearchInput.tsx  # Query input
│   │
│   ├── lib/
│   │   ├── api.ts               # FastAPI client functions
│   │   └── utils.ts             # Utility functions (cn)
│   │
│   └── types/
│       └── index.ts             # TypeScript interfaces
│
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── next.config.ts
```

---

### 🎯 Settings Available to Users

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Relevance Threshold | Slider 0-100% | 50% | Minimum score to include |
| Max Studies | Slider 3-25 | 10 | Maximum results |
| Answer Style | Select | Executive | Executive/Research/Policy/Citations |
| Min Confidence | Select | All | All/Medium+/High only |
| Use Reranking | Toggle | On | Apply Cohere reranking |
| Year Cutoff | Slider 1990-2024 | 2010 | Include studies from year+ |

---

───────────────────────────────────────────────────────────────────
│                     BACKEND (FastAPI) ✅ Already built          │
│  • /query → returns structured response + evidence              │
│  • /compare → compares selected studies                         │
│  • /export → generates PDF/docx                                 │
│  • /suggest → query coaching suggestions                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     RAG PIPELINE ✅ Already built               │
│  Qdrant + Cohere + OpenRouter                                   │
└─────────────────────────────────────────────────────────────────┘
```

### UI Layout Mockup

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Active filters: [Kenya ✕] [RCT ✕] [2018-2024 ✕]            [+ Add]    │
├─────────────────────────────────────────────────────────────────────────┤
│  🔍 What are the effects of cash transfers on food security?           │
├─────────────────────────────┬───────────────────────────────────────────┤
│                             │                                           │
│     💬 ANSWER PANEL         │     📚 EVIDENCE PANEL                     │
│                             │                                           │
│  Structured response with   │  Study cards ranked by relevance          │
│  inline [1] [2] citations   │                                           │
│                             │  ┌─────────────────────────────────────┐  │
│  Click [1] → highlights     │  │ [1] Smith et al. (2023)             │  │
│  snippet on right           │  │ Kenya | RCT | High confidence       │  │
│                             │  │ "35% increase in food security..."  │  │
│  ─────────────────────────  │  │ [Open PDF] [Compare] [Exclude]      │  │
│                             │  └─────────────────────────────────────┘  │
│  📊 Evidence Health         │                                           │
│  • 6 studies used           │  ┌─────────────────────────────────────┐  │
│  • 2018-2024 coverage       │  │ [2] Patel et al. (2022)             │  │
│  • ⚠️ No studies from Asia  │  │ India | RCT | Medium confidence     │  │
│                             │  │ "Computer-assisted learning..."     │  │
│  ─────────────────────────  │  │ [Open PDF] [Compare] [Exclude]      │  │
│                             │  └─────────────────────────────────────┘  │
│  💡 Try next:               │                                           │
│  • Narrow to Sub-Saharan    │                                           │
│    Africa?                  │                                           │
│  • Compare CCT vs UCT?      │                                           │
└─────────────────────────────┴───────────────────────────────────────────┘
```

### UI Components to Build

| Component | File | Description | Status |
|-----------|------|-------------|--------|
| Split Layout | `SplitLayout.tsx` | Resizable Answer/Evidence panels | ⬜ TODO |
| Answer Panel | `AnswerPanel.tsx` | Structured response with [1][2] citations | ⬜ TODO |
| Evidence Panel | `EvidencePanel.tsx` | Scrollable list of study cards | ⬜ TODO |
| Study Card | `StudyCard.tsx` | Title, year, country, snippet, actions | ⬜ TODO |
| Filter Chips | `FilterChips.tsx` | Active filters with ✕ to remove | ⬜ TODO |
| Filter Drawer | `FilterDrawer.tsx` | Add new filters (year, country, etc.) | ⬜ TODO |
| Compare Table | `CompareTable.tsx` | Side-by-side study comparison | ⬜ TODO |
| Query Coaching | `QueryCoaching.tsx` | Suggested next queries | ⬜ TODO |
| Evidence Health | `EvidenceHealth.tsx` | Coverage signals, gaps detected | ⬜ TODO |
| Answer Styles | `AnswerStyles.tsx` | Toggle: Executive/Research/Policy | ⬜ TODO |
| Export Modal | `ExportModal.tsx` | PDF/Word/Markdown export options | ⬜ TODO |
| Search Input | `SearchInput.tsx` | Query input with history | ⬜ TODO |

### API Endpoints to Add

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/api/query` | POST | Main query → answer + evidence | ✅ Exists (needs update) |
| `/api/compare` | POST | Compare selected studies | ⬜ TODO |
| `/api/suggest` | POST | Query coaching suggestions | ⬜ TODO |
| `/api/export` | POST | Generate PDF/Word/Markdown | ⬜ TODO |
| `/api/filters` | GET | Available filter options | ⬜ TODO |

### Step-by-Step Build Plan

#### Week 1: Foundation
- [ ] 6.1 Create Next.js project with TypeScript + Tailwind
- [ ] 6.2 Install shadcn/ui components
- [ ] 6.3 Build SplitLayout with react-resizable-panels
- [ ] 6.4 Create StudyCard component
- [ ] 6.5 Connect to FastAPI backend (basic query)

#### Week 2: Core Features
- [ ] 6.6 Build AnswerPanel with citation rendering
- [ ] 6.7 Build EvidencePanel with study cards
- [ ] 6.8 Implement citation click → highlight sync
- [ ] 6.9 Add FilterChips component
- [ ] 6.10 Add streaming response support

#### Week 3: Advanced Features
- [ ] 6.11 Build CompareTable component
- [ ] 6.12 Add /compare API endpoint
- [ ] 6.13 Build QueryCoaching component
- [ ] 6.14 Add /suggest API endpoint
- [ ] 6.15 Build ExportModal + /export endpoint
- [ ] 6.16 Add EvidenceHealth widget
- [ ] 6.17 Add AnswerStyles toggle

### Tech Stack

| Library | Purpose |
|---------|---------|
| **Next.js 14** | React framework with App Router |
| **TypeScript** | Type safety |
| **Tailwind CSS** | Utility-first styling |
| **shadcn/ui** | Pre-built accessible components |
| **react-resizable-panels** | Split pane layout |
| **TanStack Table** | Comparison table |
| **Vercel AI SDK** | Streaming LLM responses |
| **react-pdf** | PDF generation |
| **docx** | Word document generation |

### Hosting Options

| Option | Cost | Pros |
|--------|------|------|
| **Vercel** | Free tier | Best Next.js support, easy deploy |
| **Railway** | ~$5/mo | Backend + Frontend together |
| **Render** | Free tier | Good for FastAPI + static frontend |  

---

## 🧪 Phase 7: Integration Testing

### Step 7.1: Run Unit Tests
```powershell
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_retrieval.py -v
pytest tests/test_generation.py -v
pytest tests/test_integration.py -v
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

### Step 7.2: End-to-End Test
```powershell
# Full pipeline test
python -c "
import asyncio
from src.agents.devchat_agent import DevChatAgent

async def test():
    agent = DevChatAgent()
    response = await agent.query('What are the effects of cash transfers on school enrollment?')
    print('Query successful!')
    print(f'Answer: {response.answer[:200]}...')
    print(f'Citations: {len(response.citations)}')

asyncio.run(test())
"
```

**Status:** ⬜ Not Started  
**Date Completed:**  
**Issues:**  

---

## 🐛 Debug Log

| Date | Issue | File/Component | Error Message | Resolution | Status |
|------|-------|----------------|---------------|------------|--------|
| Dec 17 | Claude rate limits | OpenRouter | 429 Too Many Requests | Switched to OpenAI models | ✅ |
| Dec 17 | Embedding dim mismatch | embeddings.py, settings.py | Index has 1536, config said 1024 | Updated to dim=1536 | ✅ |
| Dec 17 | Qdrant API changed | hybrid_retriever.py | search() deprecated | Use query_points() | ✅ |
| Dec 17 | Hybrid returns 0 | hybrid_retriever.py | Sparse vectors broken | Set HYBRID_ALPHA=1.0 | ✅ |
| Dec 17 | Wrong filters applied | query_processor.py | sectors=['food security'] extracted from topic | Disabled filters in agent | ✅ |
| Dec 17 | Reranker error | reranker.py | return_documents param | Graceful fallback working | ⚠️ |

---

## 📝 Notes

### Useful Commands
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Check Python version
python --version

# List installed packages
pip list

# Clear Qdrant collection
python -c "from qdrant_client import QdrantClient; QdrantClient('http://localhost:6333').delete_collection('devchat_v2')"
```

### Common Issues & Solutions

1. **Import Error: Module not found**
   - Ensure virtual environment is activated
   - Run `pip install -r requirements.txt`

2. **API Key Error**
   - Check `.env` file has correct keys
   - Verify keys are not expired

3. **Qdrant Connection Error**
   - Ensure Qdrant is running on port 6333
   - Check firewall settings

4. **OpenRouter Rate Limit**
   - Add delays between requests
   - Check account limits

---

## ✅ Completion Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Environment Setup | ✅ | Python 3.13.3, all dependencies installed |
| Phase 2: Vector Database | ✅ | Qdrant Cloud connected, 27 points indexed |
| Phase 3: Document Ingestion | ✅ | 2 test docs → 27 chunks |
| Phase 4: Retrieval Testing | ✅ | Hybrid search working (dense + sparse) |
| Phase 5: LLM Generation | ✅ | GPT-4o-mini via OpenRouter |
| Phase 6: Research Workbench UI | ✅ | All components built + backend wired |
| Phase 7: Integration | ✅ | Full end-to-end working |
| Phase 8: Backend Wiring | ✅ | Frontend connected to FastAPI, citations working |

**Legend:** ⬜ Not Started | 🔄 In Progress | ✅ Complete | ⚠️ Partial | ❌ Blocked

---

## 🔧 Final Configuration Summary

### Working Setup (as of Dec 17, 2025)

**LLM Provider:** OpenRouter  
**Fast Model:** `openai/gpt-4o-mini`  
**Reasoning Model:** `openai/gpt-4o`  

**Embeddings:** Cohere `embed-v4.0` (dimension: **1536**)  

**Vector DB:** Qdrant Cloud (EU cluster)  
**Search Mode:** Dense-only (`HYBRID_ALPHA=1.0`)  

**Observability:** Langfuse Cloud ✅

### Known Issues (Minor)
1. **Hybrid search disabled** - Sparse vectors not working, using dense-only
2. **Reranker graceful fallback** - Minor API change, uses fallback
3. **Filter extraction disabled** - Was too aggressive (extracting topic as filter)

### Full Pipeline Test Result
```
Query: "What are the effects of cash transfers on food security?"
→ Retrieved: 27 chunks
→ Context: 15 chunks from 2 studies (2844 chars)  
→ Answer: Cited "Smith et al., 2023" with specific findings (35% increase)
→ Status: ✅ SUCCESS
```

---

## 🚧 Outstanding Work & Missing Features

### Priority 1: Critical Fixes

#### 1.1 Hybrid Search (Previously Disabled)
**Status:** ✅ FIXED  
**Files:** `src/ingestion/indexer.py`, `src/retrieval/hybrid_retriever.py`

**Problem:**  
Sparse search returned 0 results even though documents had sparse vectors indexed.

**Root Cause:**  
Python's built-in `hash()` function is **randomized between sessions** (security feature since Python 3.3). During ingestion, `hash('food')` might return `9592`, but during retrieval in a new Python session, it returns `82308`. This meant query tokens never matched indexed document tokens.

**Fix Applied:**
1. Replaced `hash(token) % 100000` with deterministic MD5 hashing:
   ```python
   hash_bytes = hashlib.md5(token.encode()).digest()
   idx = int.from_bytes(hash_bytes[:4], 'big') % 100000
   ```
2. Updated both `indexer.py` and `hybrid_retriever.py` to use identical hashing
3. Re-ingested documents with `--recreate` flag
4. Updated `.env`: `HYBRID_ALPHA=0.7` (70% dense, 30% sparse)

**Result:**  
- Sparse search now returns results with scores up to 8.3
- Hybrid search with RRF fusion working correctly
- Full pipeline tested successfully

---

#### 1.2 Filter Extraction Too Aggressive
**Status:** ✅ FIXED  
**Files:** `src/config/prompts.py`, `src/agents/devchat_agent.py`

**Problem:**  
Query processor extracted filters from topics, not just explicit mentions.
- Example: "food security" topic → `sectors=['food security']` filter
- But documents have `sector='Social Protection'`, so 0 results returned

**Root Cause:**  
Prompt said "extract explicit or implicit filters" - "implicit" was too loose.

**Fix Applied:**
1. Rewrote `METADATA_EXTRACTION_PROMPT` to be very conservative:
   - Only extract filters when EXPLICITLY stated
   - "cash transfers on food security" → NO sector filter (topic ≠ filter)
   - "RCTs in Kenya" → YES: study_type=RCT, country=Kenya
2. Added examples distinguishing topics from filters
3. Re-enabled filter application in agent

**Result:**
- Topic queries: `has_filters=False` ✅
- Explicit filter queries: `countries=['Kenya'], study_types=['RCT'], year_min=2018` ✅

---

#### 1.3 Reranker API Error
**Status:** ✅ FIXED  
**File:** `src/retrieval/reranker.py`

**Problem:**  
Cohere rerank API call failed with: `V2Client.rerank() got an unexpected keyword argument 'return_documents'`

**Root Cause:**  
Cohere V2 API removed the `return_documents` parameter. The valid parameters are:
- `model`, `query`, `documents`, `top_n`, `max_tokens_per_doc`, `request_options`

**Fix Applied:**  
Removed `return_documents=False` from the `client.rerank()` call.

**Result:**  
- Reranker now works: `Reranked 27 → 15 results (top score: 0.866)`
- No more fallback to original ranking

---

#### 1.4 Citation Metadata Missing (Unknown Author)
**Status:** ✅ FIXED  
**Files:** `src/ingestion/document_loader.py`, `src/retrieval/context_builder.py`

**Problem:**  
Citations displayed as "Unknown Author (n.d.). *Study 001*" instead of proper metadata.

**Root Causes:**  
1. Filename `test_study_001.md` → extracted study_id = `"001"`, but CSV has `"TEST001"` → lookup failed
2. `context_builder.py` wasn't including `authors` field in citation dictionaries

**Fixes Applied:**
1. Updated `_extract_study_id()` to try prefix patterns (`TEST001`, `STUDY001`, etc.)
2. Added `_extract_metadata_from_content()` to parse metadata from markdown body
3. Added `authors` field to citation generation in `context_builder.py`
4. Re-ingested documents with `--recreate` flag

**Result:**  
Citations now display correctly:
```
- Smith, J., Johnson, M., Williams, K. (2023). *Effects of unconditional cash transfers on household welfare in rural Kenya*.
- Patel, R., Kumar, S., Sharma, A. (2022). *Computer-Assisted Learning Programs and Student Achievement in Indian Schools*.
```

---

### Priority 2: Not Yet Tested


#### 2.3 Unit Tests
**Status:** 🔄 Not Run  
**Files:** `tests/test_*.py`

**To Test:**
```powershell
pytest tests/ -v
```

---

### Priority 3: Future Enhancements

#### 3.1 PDF Ingestion from SharePoint
**Status:** ✅ MinerU Working (Dec 18, 2025)
**Source:** https://3ie.sharepoint.com/:f:/s/DEPChatbot/IgCdLWmj1g8OR5L-m5ikM-dfAZN8J2CFCpv_B5EPwZKy28o?e=hB8isv

##### Chosen Solution: MinerU 2.6.8 (opendatalab/MinerU)

**Why MinerU:**
- ⭐ 50.6k GitHub stars, actively maintained
- 🏆 SOTA on OmniDocBench (academic PDF benchmark)
- 📊 Excellent table extraction (HTML output)
- 📐 LaTeX formula conversion for math-heavy papers
- 🌍 109-language OCR support
- 📄 Clean Markdown + JSON structured output
- 🔬 Designed for academic/research papers (perfect for 3ie)

**License Note:** AGPL-3.0  
⚠️ AGPL requires derivative works to be open source. However, this is **fine for internal use** because:
- PDF parsing is an internal processing step (not user-facing)
- Tokenization and vectorization are internal pipelines
- Users interact with the RAG API, not MinerU directly
- The web UI shows synthesized answers, not MinerU output

For SaaS deployment, MinerU runs as isolated processing service → outputs stored in Qdrant → no AGPL copyleft triggered on frontend/API.

**System Requirements:**
| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.10-3.13 | 3.11+ |
| RAM | 16 GB | 32 GB |
| Disk | 20 GB | 50 GB |
| GPU | Optional (CPU slower) | NVIDIA 6GB+ VRAM |

**⚠️ Windows Long Path REQUIRED:**
MinerU's `modelscope` dependency has very long file paths. You MUST enable Windows Long Path:
```powershell
# Run PowerShell as Administrator:
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```
Then restart terminal/VS Code before installing.

**Installation (Updated for v2.6.8):**
```powershell
# Package renamed from magic-pdf to mineru in v2.6+
pip install mineru[core]

# Or with GPU acceleration (vLLM/LMDeploy)
pip install mineru[full]
```

**Implementation Tasks:**

| Task | Status | Description |
|------|--------|-------------|
| 1. Download PDFs from SharePoint | ⬜ | Script to sync PDFs from 3ie SharePoint folder |
| 2. Install MinerU | ✅ | `mineru 2.6.8` installed |
| 3. Create PDF processor | ✅ | `src/ingestion/pdf_processor.py` (mineru 2.6.x API) |
| 4. Extract structured content | ✅ | Parse PDF → Markdown + tables + formulas |
| 5. Extract metadata | ✅ | Title, authors, year, DOI from first pages |
| 6. Integrate with chunking | ✅ | Feed MinerU output to existing chunker |
| 7. Batch processing script | ✅ | `scripts/process_pdfs.py` for bulk ingestion |
| 8. Test with sample papers | ✅ | ALCE paper (24 pages) processed successfully |

**✅ Test Results (Dec 18, 2025):**
```bash
# Processed 24-page academic paper successfully
mineru -p data/test_pdfs/alce_paper.pdf -o data/test_pdfs/mineru_output -m txt -d cpu

# Output:
# - alce_paper.md (631 lines of clean markdown)
# - alce_paper_content_list.json (structured elements)
# - alce_paper_layout.pdf (visual layout debug)
# - images/ (extracted figures)
```

**Models Auto-Downloaded from HuggingFace:**
- Layout detection: YOLO v8 (350MB)
- Table structure: SLANet-Plus (8MB)
- Formula recognition: UniMERNet (810MB)
- OCR: PaddleOCR v5 (det: 14MB, rec: 32MB)
- Document orientation: PP-LCNet (7MB)

**New Files Created:**
```
src/ingestion/pdf_processor.py     # MinerU 2.6.x wrapper ✅
scripts/process_pdfs.py             # Batch PDF → Qdrant pipeline ✅
scripts/mineru_worker.py            # Celery worker for queue-based processing ✅
Dockerfile.mineru                   # GPU Docker image for AWS/GCP ✅
data/test_pdfs/alce_paper.pdf       # Test paper ✅
data/test_pdfs/mineru_output/       # Test output ✅
scripts/download_sharepoint.py      # SharePoint sync (pending)
```

**⚠️ Performance Notes (Dec 18, 2025):**

| Mode | Speed | 24-page PDF | Notes |
|------|-------|-------------|-------|
| **CPU** | 1-3 pages/min | 10-20 min | Current local setup |
| **GPU (T4)** | 10-20 pages/min | 1-3 min | AWS g4dn.xlarge |
| **GPU (A10G)** | 20-30 pages/min | <1 min | AWS g5.xlarge |

**First run** is slower due to model loading (~30-60 sec). Subsequent runs faster if processor kept in memory.

**Model Cache Location:** `~/.cache/huggingface/` (~1.2 GB total)

**Production Deployment Options:**

| Approach | Cost | Best For |
|----------|------|----------|
| AWS g4dn.xlarge Spot | ~$0.16/hr | Cost-effective batch processing |
| AWS g5.xlarge Spot | ~$0.40/hr | Faster processing |
| GCP n1-standard-4 + T4 | ~$0.11/hr | Cheapest GPU option |
| AWS Batch | Variable | Scale to zero, auto-retry |

**Architecture:**
```
SharePoint PDFs → Local Download → MinerU Processing
                                        ↓
                              Markdown + Tables + Formulas
                                        ↓
                              Existing Pipeline (chunk → embed → Qdrant)
```

**Production Architecture (AWS):**
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   S3/GCS    │────▶│  SQS/Redis  │────▶│  GPU Worker │
│  (PDF in)   │     │   Queue     │     │  (MinerU)   │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌─────────────┐            │
                    │   S3/GCS    │◀───────────┘
                    │ (JSON out)  │
                    └─────────────┘
```

**Estimated Time:** ✅ Basic implementation complete. Pending: SharePoint integration (~1 day)

---

#### 3.2 Voyage AI Alternative Embeddings
**Status:** ⬜ Configured, Not Tested  
**File:** `src/ingestion/embeddings.py`

The code supports Voyage AI as alternative embedding provider. To switch:
```env
EMBEDDING_PROVIDER=voyage
VOYAGE_API_KEY=your-key
```

---

#### 3.3 Evaluation Pipeline
**Status:** ⬜ Not Run  
**Files:** `evaluation/test_cases.json`, `scripts/run_evaluation.py`

**To Test:**
```powershell
python scripts/run_evaluation.py
```

---

## 📊 Feature Completeness Matrix

### Current Features (v2.0) ✅

| Feature | Implemented | Tested | Working | Notes |
|---------|-------------|--------|---------|-------|
| Dense Search | ✅ | ✅ | ✅ | Core retrieval working |
| Sparse/BM25 Search | ✅ | ✅ | ✅ | **FIXED** - Uses MD5 hash |
| Hybrid Fusion | ✅ | ✅ | ✅ | **FIXED** - RRF fusion working |
| Query Expansion | ✅ | ✅ | ✅ | LLM expands queries |
| Query Classification | ✅ | ✅ | ✅ | Simple/Complex/Comparison |
| Filter Extraction | ✅ | ✅ | ✅ | **FIXED** - Conservative prompt |
| Reranking | ✅ | ✅ | ✅ | **FIXED** - Cohere V2 API working |
| Context Building | ✅ | ✅ | ✅ | Dedupes, sorts by score |
| Citation Generation | ✅ | ✅ | ✅ | **FIXED** - Authors, year, title working |
| Answer Synthesis | ✅ | ✅ | ✅ | GPT-4o-mini via OpenRouter |
| Langfuse Tracing | ✅ | ✅ | ✅ | Full observability |
| Research Workbench UI | ✅ | ✅ | ✅ | **COMPLETE** - Connected to backend, citations working |
| FastAPI Server | ✅ | ✅ | ✅ | /api/query and /api/filters endpoints working |
| PDF Ingestion | ✅ | ✅ | ✅ | **COMPLETE** - Modal GPU + MinerU + R2 + Qdrant |
| Smart Deduplication | ✅ | ✅ | ✅ | **NEW** - Checks R2 + Qdrant before processing |
| Evaluation Suite | ✅ | ❌ | ? | Not run |

### Quick Reference: Current Features Explained

| Feature | What It Does | How It Works |
|---------|--------------|--------------|
| **Dense Search** | Semantic similarity search using embeddings | Cohere embed-v4 creates 1536-dim vectors; Qdrant finds nearest neighbors |
| **Sparse/BM25 Search** | Exact keyword matching | Tokenizes text, builds term frequency vectors with MD5 hashing |
| **Hybrid Fusion** | Combines dense + sparse results | Reciprocal Rank Fusion (RRF) merges rankings; HYBRID_ALPHA=0.7 weights |
| **Query Expansion** | Adds synonyms and related terms | LLM expands "CCTs" → "conditional cash transfers, cash transfer programs" |
| **Query Classification** | Routes queries to appropriate pipeline | Classifies as Simple/Complex/Comparison; affects model choice |
| **Filter Extraction** | Parses explicit constraints from queries | "RCTs in Kenya since 2018" → `country=Kenya, study_type=RCT, year_min=2018` |
| **Reranking** | Re-scores top results with cross-encoder | Cohere Rerank v3.5 re-orders top 50 → top 15 by relevance |
| **Context Building** | Assembles chunks for LLM prompt | Deduplicates, groups by study, attaches citation metadata |
| **Citation Generation** | Creates proper academic citations | Extracts authors, year, title from metadata; formats as references |
| **Answer Synthesis** | Generates final response | Routes to fast (GPT-4o-mini) or reasoning (GPT-4o) model based on query type |
| **Langfuse Tracing** | Observability and debugging | Logs every step: query → retrieval → rerank → generation with latencies |
| **Research Workbench** | Professional research UI | Split screen, study cards, filters, compare mode, export (Next.js) |
| **FastAPI Server** | REST API for integrations | Endpoints at localhost:8000/docs |
| **PDF Ingestion** | Production GPU pipeline | Modal + MinerU + R2 storage + Qdrant indexing |
| **Smart Deduplication** | Skip already-processed PDFs | Checks R2 outputs + Qdrant indexed chunks |
| **Evaluation Suite** | Automated quality testing | RAGAS metrics on golden test set (not yet run) |

### Roadmap Features (v2.5 → v3.0) 🚀

| Priority | Feature | Effort | Impact | Status | Target |
|----------|---------|--------|--------|--------|--------|
| 🔴 **P1** | Multi-Query RAG-Fusion | Low | +10-15% recall | ⬜ TODO | v2.5 |
| 🔴 **P1** | CRAG Sanity Check | Low | ↓ Hallucinations | ⬜ TODO | v2.5 |
| 🔴 **P1** | RAGAS Eval in CI | Low | Quality assurance | ⬜ TODO | v2.5 |
| 🟡 **P2** | Contextual Retrieval | Medium | +49% recall | ⬜ TODO | v2.5 |
| 🟡 **P2** | HyDE (Hypothetical Docs) | Medium | Better zero-shot | ⬜ TODO | v2.5 |
| 🟡 **P2** | Parent-Child Chunks | Medium | Better context | ⬜ TODO | v2.5 |
| 🟢 **P3** | Self-RAG | High | Highest accuracy | ⬜ TODO | v3.0 |
| 🟢 **P3** | ColBERTv2 / Late Interaction | High | SOTA retrieval | ⬜ TODO | v3.0 |
| 🟢 **P3** | RAPTOR Hierarchical | High | Multi-hop reasoning | ⬜ TODO | v3.0 |
| 🔵 **P4** | GraphRAG | Very High | Complex relations | ⬜ TODO | v3.0+ |

**Legend:**
- 🔴 P0 = Critical for launch (2-3 weeks)
- 🔴 P1 = Quick wins, do first (1-2 days each)
- 🟡 P2 = Medium effort, high value (3-5 days each)
- 🟢 P3 = Advanced, requires planning (1-2 weeks each)
- 🔵 P4 = Research project (2-4 weeks)

### Quick Reference: What Each Feature Does

| Feature | One-Line Description |
|---------|---------------------|
| **Multi-Query RAG-Fusion** | Generate 3-5 query variants, fuse results for robust retrieval |
| **CRAG Sanity Check** | Verify retrieval quality, fallback if confidence low |
| **RAGAS Eval** | Automated metrics: Faithfulness, Relevancy, Precision |
| **Contextual Retrieval** | Prepend document context to chunks before embedding |
| **HyDE** | Embed hypothetical answer instead of query |
| **Parent-Child Chunks** | Small chunks for search, expand to parents for context |
| **Self-RAG** | LLM critiques its own retrieval and generation |
| **ColBERTv2** | Token-level embeddings with late interaction |
| **RAPTOR** | Build tree of summaries for multi-hop reasoning |
| **GraphRAG** | Entity extraction + knowledge graph retrieval |

---

## 🚀 Future Roadmap: SOTA RAG Enhancements (2024-2025)

Based on comprehensive analysis of state-of-the-art RAG research, here are prioritized next steps for DevChat.

### Phase 1: Quick Wins (Low Effort, High Impact) 🎯

#### 1.1 Multi-Query RAG-Fusion
**Complexity:** Low | **Impact:** +10-15% recall | **Time:** 1-2 days

**What:** Generate 3-5 query variants, retrieve for each, fuse results with RRF.

**Why:** Handles query ambiguity without re-indexing. Example:
- Original: "cash transfers education"  
- Variants: "CCT school enrollment", "unconditional transfers learning outcomes", "social protection academic performance"

**Implementation:**
```python
# src/retrieval/query_processor.py
async def generate_query_variants(self, query: str, n: int = 4) -> List[str]:
    prompt = f"Generate {n} semantically different search queries for: {query}"
    response = await self.llm.acomplete(prompt)
    return [query] + parse_variants(response.text)
```

**Reference:** [RAG-Fusion Paper](https://arxiv.org/abs/2402.03367)

---

#### 1.2 CRAG Retrieval Sanity Check
**Complexity:** Low | **Impact:** Reduces hallucinations | **Time:** 1 day

**What:** After retrieval, score relevance of top results. If all scores < threshold, trigger fallback (web search or "I don't know").

**Why:** Prevents confident but wrong answers when retrieval fails.

**Implementation:**
```python
# src/retrieval/hybrid_retriever.py
async def retrieve_with_sanity_check(self, query: str) -> Tuple[List[Chunk], bool]:
    results = await self.retrieve(query)
    
    # Check if top results are actually relevant
    if results and results[0].score < 0.3:  # Low confidence threshold
        logger.warning(f"Low retrieval confidence: {results[0].score}")
        return results, False  # Signal: results may not be reliable
    
    return results, True
```

**Reference:** [CRAG Paper](https://arxiv.org/abs/2401.15884)

---

#### 1.3 RAGAS Evaluation in CI
**Complexity:** Low | **Impact:** Quality assurance | **Time:** 1-2 days

**What:** Run automated evaluation on every PR using RAGAS metrics.

**Metrics:**
- **Faithfulness:** Does the answer use only retrieved context?
- **Answer Relevancy:** Does the answer address the question?
- **Context Precision:** Are retrieved chunks actually relevant?

**Implementation:**
```yaml
# .github/workflows/eval.yml
- name: Run RAGAS Evaluation
  run: |
    python scripts/run_evaluation.py --output results.json
    python scripts/check_thresholds.py --input results.json --fail-below 0.7
```

**Reference:** [RAGAS Documentation](https://docs.ragas.io/)

---

### Phase 2: Medium Effort Enhancements 🔧

#### 2.1 Contextual Retrieval (Anthropic Method)
**Complexity:** Medium | **Impact:** +49% recall | **Time:** 3-5 days

**What:** Before embedding each chunk, prepend a short context summary:
```
<document_context>
This chunk is from a 2023 RCT study of cash transfers in Kenya by Smith et al.
The study found 35% improvement in food security among beneficiary households.
</document_context>

[Original chunk content here...]
```

**Why:** Chunks lose context when split. Adding document-level context to each chunk dramatically improves retrieval.

**Implementation:**
1. During ingestion, use LLM to generate context for each chunk
2. Prepend context to chunk before embedding
3. Store both contextualized embedding and original text

**Reference:** [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)

---

#### 2.2 HyDE (Hypothetical Document Embeddings)
**Complexity:** Medium | **Impact:** Better zero-shot retrieval | **Time:** 2-3 days

**What:** Instead of embedding the query directly, generate a hypothetical answer and embed that.

**Why:** Queries are short and vague. Hypothetical answers match document style better.

**Example:**
- Query: "CCT education effects"
- HyDE: "Conditional cash transfer programs have shown positive effects on education outcomes. Studies in Latin America found 10-15% increases in school enrollment..."
- This hypothetical text embeds closer to actual study findings.

**Reference:** [HyDE Paper](https://arxiv.org/abs/2212.10496)

---

#### 2.3 Parent-Child Chunking
**Complexity:** Medium | **Impact:** Better context | **Time:** 2-3 days

**What:** Create small chunks for precise retrieval, but expand to parent chunks for context during synthesis.

**Current:** 512-token chunks  
**Proposed:** 128-token child chunks for search, expand to 2048-token parents for context

**Implementation:**
```python
# src/retrieval/context_builder.py
def expand_to_parent(self, child_chunk: Chunk) -> Chunk:
    parent_id = child_chunk.metadata.get("parent_id")
    if parent_id:
        return self.qdrant.retrieve(parent_id)
    return child_chunk
```

---

### Phase 3: Advanced Techniques (High Effort, High Reward) 🏆

#### 3.1 Self-RAG
**Complexity:** High | **Impact:** Highest accuracy | **Time:** 1-2 weeks

**What:** Train/prompt LLM to:
1. Decide if retrieval is needed
2. Critique retrieved passages for relevance
3. Generate answer with self-reflection tokens
4. Critique answer for faithfulness

**Implementation:** Requires special prompting or fine-tuned model with reflection tokens.

**Reference:** [Self-RAG Paper](https://arxiv.org/abs/2310.11511)

---

#### 3.2 ColBERTv2 / Late Interaction
**Complexity:** High | **Impact:** SOTA retrieval | **Time:** 1-2 weeks

**What:** Instead of single vector per chunk, store token-level embeddings. At query time, do late interaction (MaxSim) for more precise matching.

**Benefit:** Better than cross-encoder reranking, but applies to all documents (not just top-K).

**Challenge:** Requires ColBERT index infrastructure (not just Qdrant).

**Reference:** [ColBERTv2 Paper](https://arxiv.org/abs/2112.01488)

---

#### 3.3 RAPTOR Hierarchical Summarization
**Complexity:** High | **Impact:** Multi-hop reasoning | **Time:** 1-2 weeks

**What:** Build a tree of summaries:
```
Level 3: Corpus summary ("3ie evidence on social protection...")
    ↓
Level 2: Topic clusters ("Cash transfer studies show...")
    ↓
Level 1: Study summaries ("Smith 2023 found...")
    ↓
Level 0: Leaf chunks (original text)
```

**Benefit:** For broad questions, retrieve from higher levels. For specific questions, retrieve leaves.

**Reference:** [RAPTOR Paper](https://arxiv.org/abs/2401.18059)

---

#### 3.4 GraphRAG
**Complexity:** Very High | **Impact:** Complex relationships | **Time:** 2-4 weeks

**What:** Extract entities and relationships into a knowledge graph. Use graph algorithms during retrieval.

**Benefit:** Handles complex queries like "Which authors have published on both cash transfers AND nutrition?" 

**Challenge:** Requires entity extraction, graph database (Neo4j), graph-aware retrieval.

**Reference:** [Microsoft GraphRAG](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/)

---

### Implementation Priority Matrix

| Enhancement | Effort | Impact | Priority | Dependencies |
|-------------|--------|--------|----------|--------------|
| Multi-Query RAG-Fusion | Low | Medium | 🔴 **P1** | None |
| CRAG Sanity Check | Low | Medium | 🔴 **P1** | None |
| RAGAS in CI | Low | High | 🔴 **P1** | test_cases.json |
| Contextual Retrieval | Medium | High | 🟡 **P2** | Re-ingestion |
| HyDE | Medium | Medium | 🟡 **P2** | None |
| Parent-Child Chunks | Medium | Medium | 🟡 **P2** | Re-ingestion |
| Self-RAG | High | High | 🟢 **P3** | Prompting work |
| ColBERTv2 | High | High | 🟢 **P3** | New index |
| RAPTOR | High | High | 🟢 **P3** | Re-ingestion |
| GraphRAG | Very High | Medium | 🔵 **P4** | Neo4j, NER |

---

### Key Research References

**Retrieval Enhancements:**
- [Anthropic Contextual Retrieval (2024)](https://www.anthropic.com/news/contextual-retrieval) - +49% recall
- [ColBERTv2](https://arxiv.org/abs/2112.01488) - Late interaction retrieval
- [Late Chunking (JinaAI)](https://jina.ai/news/late-chunking-in-long-context-embedding-models/) - Context-preserving embeddings

**Query Enhancement:**
- [RAG-Fusion](https://arxiv.org/abs/2402.03367) - Multi-query generation
- [HyDE](https://arxiv.org/abs/2212.10496) - Hypothetical document embeddings

**Self-Correction:**
- [CRAG](https://arxiv.org/abs/2401.15884) - Corrective RAG with web fallback
- [Self-RAG](https://arxiv.org/abs/2310.11511) - Self-reflective retrieval

**Hierarchical & Graph:**
- [RAPTOR](https://arxiv.org/abs/2401.18059) - Tree-based recursive summarization
- [Microsoft GraphRAG](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/) - Knowledge graphs

**Evaluation:**
- [RAGAS](https://docs.ragas.io/) - RAG evaluation framework
- [TruLens](https://www.trulens.org/) - Production RAG monitoring

---

## 🏢 Phase 4: SaaS Platform Roadmap (v3.0+)

**Vision:** Transform DevChat from a research tool into a multi-tenant SaaS platform for evidence synthesis.

### 4.1 User & Team Management

| Feature | Description | Priority |
|---------|-------------|----------|
| **Authentication** | OAuth2 (Google, Microsoft, ORCID), Magic Links, SSO | 🔴 P1 |
| **User Accounts** | Profile, preferences, API keys, usage tracking | 🔴 P1 |
| **Teams/Organizations** | Create teams, invite members, role management | 🔴 P1 |
| **Role-Based Access** | Admin, Editor, Viewer roles per workspace | 🟡 P2 |
| **Team Workspaces** | Shared document collections, queries, exports | 🟡 P2 |

**Tech Stack:**
- Auth: NextAuth.js / Clerk / Auth0
- Database: PostgreSQL (users, teams, subscriptions)
- ORM: Prisma / Drizzle

---

### 4.2 Document & PDF Management

| Feature | Description | Priority |
|---------|-------------|----------|
| **PDF Upload** | Direct PDF upload with MinerU parsing | 🔴 P1 |
| **Document Library** | User/team document collections with metadata | 🔴 P1 |
| **PDF Processing Pipeline** | MinerU → Extract text, tables, formulas from PDFs | 🔴 P1 |
| **Storage** | S3-compatible storage (AWS S3, Cloudflare R2, MinIO) | 🔴 P1 |
| **Document Versioning** | Track document revisions | 🟡 P2 |
| **Citation Import** | Import from Zotero, Mendeley, BibTeX | 🟡 P2 |
| **OCR Support** | MinerU includes 109-language OCR (PaddleOCR) | ✅ Built-in |

**PDF Processing Stack:**
- **Parser:** MinerU (magic-pdf) - SOTA for academic papers
- **Output:** Markdown + HTML tables + LaTeX formulas
- **Why MinerU:** 50.6k stars, handles complex academic PDFs, table/formula extraction

**AGPL License Compliance:**
MinerU is AGPL-3.0 licensed, which is acceptable because:
1. PDF processing is an **internal backend service** (not distributed to users)
2. Users interact with our API/UI, not MinerU directly
3. Processed content (Markdown) stored in Qdrant, not MinerU output served
4. For maximum isolation, run MinerU in separate container/service

**Architecture:**
```
User uploads PDF → S3 Storage → Processing Queue (Celery/BullMQ)
                                      ↓
                              MinerU Parser → Markdown/Tables/Formulas
                                      ↓
                              Chunking → Embedding → Qdrant
                                      ↓
                              User's private collection (namespace/tenant isolation)
```

---

### 4.3 Multi-Tenancy & Data Isolation

| Feature | Description | Priority |
|---------|-------------|----------|
| **Tenant Isolation** | Separate vector namespaces per organization | 🔴 P1 |
| **Private Collections** | User-specific document sets | 🔴 P1 |
| **Shared Collections** | Team-accessible document pools | 🟡 P2 |
| **Public Corpus** | 3ie Evidence Portal as shared baseline | 🟡 P2 |
| **Cross-tenant Search** | Search own + public collections | 🟡 P2 |

**Qdrant Multi-tenancy Options:**
1. **Namespaces** - Logical separation within same collection
2. **Payload filtering** - `tenant_id` filter on every query
3. **Separate collections** - Physical isolation (for enterprise)

---

### 4.4 Subscription & Billing

| Tier | Queries/Month | Storage | Features | Price |
|------|---------------|---------|----------|-------|
| **Free** | 50 | 100 MB | Public corpus only, basic export | $0 |
| **Researcher** | 500 | 5 GB | PDF upload, private collections | $19/mo |
| **Team** | 2,000 | 25 GB | 5 users, shared workspaces | $79/mo |
| **Enterprise** | Unlimited | Unlimited | SSO, API access, dedicated support | Custom |

**Billing Stack:**
- Payment: Stripe / Paddle / LemonSqueezy
- Usage tracking: Custom metering middleware
- Quotas: Redis-based rate limiting

---

### 4.5 API Access (Developer Tier)

| Feature | Description |
|---------|-------------|
| **REST API** | `/api/v1/query`, `/api/v1/upload`, `/api/v1/collections` |
| **API Keys** | Per-user keys with rate limits |
| **Webhooks** | Notify on processing complete, usage alerts |
| **SDKs** | Python, JavaScript/TypeScript clients |
| **OpenAPI Docs** | Auto-generated Swagger/ReDoc |

**API Pricing:**
- Free: 100 API calls/month
- Pro: $0.01 per query, $0.05 per PDF processed
- Enterprise: Volume discounts

---

### 4.6 Infrastructure & Scaling

| Component | Development | Production |
|-----------|-------------|------------|
| **Backend** | FastAPI (single instance) | FastAPI + Gunicorn (multi-worker) |
| **Database** | SQLite/PostgreSQL local | Managed PostgreSQL (Supabase, Neon, RDS) |
| **Vector DB** | Qdrant Cloud (free tier) | Qdrant Cloud (dedicated) or self-hosted |
| **Object Storage** | Local filesystem | S3 / Cloudflare R2 |
| **Queue** | Sync processing | Redis + Celery / BullMQ |
| **Hosting** | Local | Railway / Render / AWS ECS / Fly.io |
| **CDN** | None | Cloudflare |
| **Monitoring** | Langfuse | Langfuse + Sentry + Prometheus |

---

### 4.7 Implementation Phases

#### Phase 4.1: Authentication & Basic Multi-tenancy (2-3 weeks)
- [ ] Add NextAuth.js with Google/email providers
- [ ] PostgreSQL for users, sessions
- [ ] Qdrant namespaces per user
- [ ] Basic user dashboard

#### Phase 4.2: PDF Upload & Processing (2-3 weeks)
- [ ] S3 storage integration
- [ ] PDF parsing pipeline (Unstructured.io or PyMuPDF)
- [ ] Background job queue (Celery)
- [ ] User document library UI

#### Phase 4.3: Teams & Subscriptions (2-3 weeks)
- [ ] Team/organization models
- [ ] Stripe subscription integration
- [ ] Usage metering & quotas
- [ ] Team workspace UI

#### Phase 4.4: API & Developer Experience (1-2 weeks)
- [ ] Public REST API with versioning
- [ ] API key management
- [ ] Rate limiting
- [ ] SDK generation from OpenAPI

---

### 4.8 Relevant Technologies & References

**Authentication:**
- [NextAuth.js](https://next-auth.js.org/) - Auth for Next.js
- [Clerk](https://clerk.com/) - Full-featured auth platform
- [Auth0](https://auth0.com/) - Enterprise auth

**PDF Processing:**
- [Unstructured.io](https://unstructured.io/) - Document parsing
- [PyMuPDF](https://pymupdf.readthedocs.io/) - Fast PDF extraction
- [LlamaParse](https://docs.llamaindex.ai/en/stable/llama_cloud/llama_parse/) - AI-powered parsing

**Background Jobs:**
- [Celery](https://docs.celeryq.dev/) - Python task queue
- [BullMQ](https://docs.bullmq.io/) - Node.js queue
- [Inngest](https://www.inngest.com/) - Serverless queues

**Billing:**
- [Stripe](https://stripe.com/) - Payments & subscriptions
- [LemonSqueezy](https://www.lemonsqueezy.com/) - SaaS billing (simpler)

**Multi-tenant SaaS Examples:**
- [Supabase Architecture](https://supabase.com/docs/guides/platform) - Multi-tenant patterns
- [Building SaaS with Next.js](https://shipfast.dev/) - SaaS boilerplate

---

## ✅ Backend Wiring (COMPLETED Dec 18, 2025)

**Goal:** Connect the complete Next.js frontend to the FastAPI backend

### Step 1: Add CORS to FastAPI ✅
```python
# api/server.py - Already had CORS configured
```

### Step 2: Update Backend Schemas (api/schemas.py) ✅
- Added `SearchSettings` model
- Added `FilterInput` model  
- Added `QueryRequest` with settings
- Added `QueryResponse` matching frontend types
- Added `StudyResponse`, `CitationResponse`, `EvidenceHealth`

### Step 3: Update /api/query Endpoint ✅
- Created new `api/routes.py` with `api_router`
- POST `/api/query` - Full RAG pipeline with filters/settings
- GET `/api/filters` - Returns available filter options from Qdrant

### Step 4: Wire Frontend ✅
- Updated `page.tsx` to call real API via `queryEvidence()`
- Removed mock data simulation
- Added error handling

### Step 5: Citation System ✅
- Backend numbers studies `[1]`, `[2]` in context
- LLM uses `[1]`, `[2]` in answers
- Frontend renders citations as clickable blue bubbles
- Invalid citations shown in orange (validation)
- References section appears right after answer

### Step 6: Test End-to-End ✅
- Backend: http://localhost:8000
- Frontend: http://localhost:3001
- Full query → answer → citations flow working

### Files to Modify

| File | Changes |
|------|---------|
| `api/server.py` | Add CORS middleware |
| `api/schemas.py` | Add SearchSettings, FilterInput, updated QueryRequest/Response |
| `api/routes.py` | Update /query to accept settings, apply filters |
| `frontend/src/lib/api.ts` | Replace mock with real fetch calls |
| `frontend/src/app/page.tsx` | Pass searchSettings to queryEvidence |
| `frontend/.env.local` | Set NEXT_PUBLIC_API_URL |

### Estimated Time: 2-3 hours

---

## ⚠️ Known Vulnerabilities & Future Research

### V1: Citation Reliability (LLM Hallucination Risk)

**Status:** 🟡 Partially Mitigated  
**Severity:** Medium  
**Date Identified:** December 18, 2025

#### Problem Description
The current citation system relies on the LLM correctly using `[1]`, `[2]`, etc. to reference studies in the order they appear in the context. However, LLMs can:

1. **Invent citations** - Reference `[5]` when only 2 studies exist
2. **Misattribute findings** - Cite `[1]` for content that actually came from `[2]`
3. **Hallucinate content** - Generate plausible-sounding findings not in any source

#### Current Mitigations
| Mitigation | Status | Description |
|------------|--------|-------------|
| Numbered context headers | ✅ | Studies labeled `[1] **Title** (Year)` in LLM context |
| Explicit prompt instructions | ✅ | LLM told to use `[1]`, `[2]` matching context order |
| Frontend validation | ✅ | Invalid citation IDs shown in orange (not clickable) |
| Visual differentiation | ✅ | Valid = blue bubble, Invalid = orange text |

#### SOTA Approaches to Explore

1. **Constrained Decoding / Structured Output**
   - Use JSON schema with OpenAI/Anthropic to force valid citation format
   - Example: `{"claim": "...", "citations": [1, 2]}`
   - Libraries: Instructor, Outlines, Guidance

2. **Post-hoc Citation Verification**
   - After LLM generates answer, verify each `[N]` claim against source text
   - Use embedding similarity or NLI (Natural Language Inference) models
   - Flag claims that don't match any source with high confidence

3. **Retrieval-Augmented Citing (RAC)**
   - For each sentence, re-retrieve and attach the most relevant source
   - Paper: "ALCE: Evaluating LLMs' Citation Generation" (2023)
   - More accurate but slower

4. **Attributed QA / Quote Extraction**
   - Force LLM to include direct quotes with citations
   - Easier to verify: quote either exists in source or doesn't
   - Paper: "Attributed Question Answering" (2023)

5. **Fine-tuned Citation Models**
   - Train smaller model specifically for citation generation
   - Given (claim, sources) → predict correct citation IDs
   - Could run as post-processor

#### Recommended Next Steps
1. **Short-term:** Implement JSON structured output for citations using Instructor library
2. **Medium-term:** Add post-hoc verification using sentence embeddings
3. **Long-term:** Evaluate ALCE-style attributed QA approach

#### References
- ALCE Benchmark: https://arxiv.org/abs/2305.14627
- Attributed QA: https://arxiv.org/abs/2212.08037
- Instructor library: https://github.com/jxnl/instructor
- Outlines (structured generation): https://github.com/outlines-dev/outlines

---

## 🚀 Phase 8: Production Roadmap & Feature Requests

**Created:** December 18, 2025  
**Status:** 📋 Planning

This section tracks future enhancements for scaling DevChat to production (external users, paid services).

---

### 8.1 MinerU Python API - COMPLETED ✅

**Date Completed:** December 18, 2025

| Task | Status | Notes |
|------|--------|-------|
| Install MinerU 2.6.8 | ✅ | Package renamed from `magic-pdf` to `mineru` |
| Enable Windows Long Path | ✅ | Required for modelscope dependency |
| CLI Test | ✅ | `mineru -p file.pdf -o output` working |
| Python API Integration | ✅ | `src/ingestion/pdf_processor.py` |
| Fix `formula_enabled` parameter | ✅ | Was `formula_enable` (missing 'd') |
| Fix table extraction | ✅ | Tables use `table_body` field, not `html` |
| Fix formula extraction | ✅ | Equations use `text` field with `type: "equation"` |
| End-to-end test | ✅ | 24-page paper → 21 tables, 1 formula, 110k chars |

**Output Location:** `C:\Users\LucasSempe\AppData\Local\Temp\mineru_output\`

**Files:**
- `alce_paper.md` - Full markdown text (110 KB)
- `alce_paper_content_list.json` - Structured JSON (171 KB)
- `images/` - Extracted figures and table screenshots

**Note:** `huggingface_hub[hf_xet]` warning during download is optional - only improves download speed, MinerU works fine without it.

---

### 8.2 Bulk File Upload & Folder Selection

**Status:** ⬜ Not Started  
**Priority:** HIGH

#### Requirements
| Feature | Description | Status |
|---------|-------------|--------|
| Multi-file upload | Drag & drop multiple PDFs at once | ⬜ |
| Folder selection | Select entire folder for batch processing | ⬜ |
| File type support | PDF, DOCX, TXT, MD, HTML | ⬜ |
| Cloud repository sync | SharePoint, Google Drive, S3 integration | ⬜ |
| Progress tracking | Show processing status for each file | ⬜ |
| Error handling | Continue batch on single file failure | ⬜ |

#### Implementation Notes
```
User uploads 50 PDFs → Queue system → MinerU processes each → 
Status updates via WebSocket → Store in Qdrant when complete
```

**Estimated Time:** 2-3 days

---

### 8.3 Admin UI - Document Ingestion Tab

**Status:** ✅ COMPLETE (Dec 18, 2025)  
**Priority:** HIGH

#### Requirements
| Feature | Description | Status |
|---------|-------------|--------|
| Separate admin route | `/admin` page | ✅ Complete |
| Role-based access | Only "owner" role can access | ⬜ TODO (auth) |
| Bulk upload interface | Drag & drop zone with progress | ✅ Complete |
| Processing queue | View pending/processing/completed files | ✅ Complete |
| Document management | View/delete indexed documents | ✅ Complete |
| Metadata editor | Edit title, authors, year post-ingestion | ⬜ TODO |
| Re-process button | Re-run MinerU on failed/updated PDFs | ✅ Complete |
| Settings panel | MinerU options, connections | ✅ Complete |

#### Files Created
```
frontend/src/app/admin/page.tsx              # Admin route
frontend/src/components/admin/
├── AdminLayout.tsx                          # Main layout with tabs
├── UploadTab.tsx                            # Drag & drop file upload
├── ProcessingTab.tsx                        # Job queue monitoring
├── DocumentsTab.tsx                         # Document management table
├── SettingsTab.tsx                          # Configuration panel
└── index.ts                                 # Exports
```

#### Backend API Endpoints
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/admin/status` | GET | Dashboard status | ✅ |
| `/admin/upload` | POST | Upload file to R2 | ✅ (stub) |
| `/admin/jobs` | GET | List processing jobs | ✅ (mock) |
| `/admin/jobs/trigger` | POST | Start batch processing | ✅ (stub) |
| `/admin/documents` | GET | List indexed documents | ✅ (mock) |
| `/admin/documents/{id}` | DELETE | Delete document | ✅ |
| `/admin/documents/{id}/reprocess` | POST | Reprocess document | ✅ |

**Note:** Endpoints return mock data. Connect to Modal/R2/Turso for production.

---

### 8.4 MinerU Parallelization

**Status:** ✅ COMPLETE (Modal-based)  
**Priority:** MEDIUM

#### Solution: Modal Serverless GPU

Instead of Celery + Redis, using **Modal** for simpler scaling:

```python
# infrastructure/modal_mineru.py

@app.function(gpu="T4", timeout=1800)
def process_pdf(pdf_key: str) -> dict:
    # Downloads from R2, runs MinerU, uploads results
    ...

# Orchestrator spawns parallel workers
for pdf_key in new_pdfs:
    process_pdf.spawn(pdf_key=pdf_key)  # Parallel execution
```

| Feature | Benefit |
|---------|---------|
| Auto-scaling | 0 → 10 workers automatically |
| GPU management | No CUDA setup needed |
| Cost efficiency | Pay per second of GPU use |
| Retry handling | Built-in with exponential backoff |

**Estimated Time:** ✅ Complete

---

### 8.5 MinerU User Settings

**Status:** ✅ UI Complete (Dec 18, 2025)  
**Priority:** LOW

#### Configurable Options (in Settings Tab)


| Setting | Default | Description |
|---------|---------|-------------|
| `enable_ocr` | `True` | OCR for scanned PDFs |
| `enable_table_extraction` | `True` | Extract tables as HTML |
| `enable_formula_extraction` | `True` | Extract math as LaTeX |
| `device` | `cpu` | `cpu` or `cuda` for GPU |
| `language` | `auto` | OCR language (109 supported) |
| `output_format` | `markdown` | `markdown`, `json`, or `both` |

#### UI Location
Settings Drawer → Advanced → PDF Processing Options

**Note:** Most users won't need to change these. Default settings work well for academic papers.

---

### 8.6 Docker for Production

**Status:** ⬜ Not Started  
**Priority:** HIGH (for deployment)

#### Do We Need Docker?

**YES** - Docker is strongly recommended for production because:

| Reason | Why It Matters |
|--------|----------------|
| **Consistency** | Same environment on dev/staging/production |
| **Isolation** | MinerU's heavy dependencies don't affect other services |
| **Scaling** | Easy horizontal scaling with Kubernetes/ECS |
| **Security** | Sandboxed execution, no host access |
| **Deployment** | One command to deploy anywhere |
| **GPU support** | NVIDIA Container Toolkit for GPU acceleration |

#### Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION DEPLOYMENT                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   NGINX     │  │  Frontend   │  │   Backend   │  │   MinerU    │    │
│  │   Proxy     │──│  (Next.js)  │──│  (FastAPI)  │──│   Worker    │    │
│  │   :443      │  │   :3000     │  │   :8000     │  │   (Celery)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│         │                                   │              │            │
│         │                                   ▼              ▼            │
│         │                          ┌─────────────┐  ┌─────────────┐    │
│         │                          │   Qdrant    │  │    Redis    │    │
│         │                          │   (Vector)  │  │   (Queue)   │    │
│         │                          │   :6333     │  │   :6379     │    │
│         │                          └─────────────┘  └─────────────┘    │
│         │                                   │                           │
│         │                                   ▼                           │
│         │                          ┌─────────────┐                      │
│         └─────────────────────────▶│  PostgreSQL │◀─── Document DB     │
│                                    │   :5432     │                      │
│                                    └─────────────┘                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Docker Compose (Production)

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
    
  backend:
    build: .
    ports: ["8000:8000"]
    environment:
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://user:pass@postgres:5432/devchat
    depends_on: [qdrant, redis, postgres]
    
  mineru-worker:
    build: 
      context: .
      dockerfile: Dockerfile.mineru
    command: celery -A tasks worker --loglevel=info
    volumes:
      - pdf_storage:/data/pdfs
    deploy:
      replicas: 2  # Scale workers
    depends_on: [redis]
    
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: [qdrant_storage:/qdrant/storage]
    
  redis:
    image: redis:alpine
    ports: ["6379:6379"]
    
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: devchat
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes: [postgres_data:/var/lib/postgresql/data]

volumes:
  qdrant_storage:
  postgres_data:
  pdf_storage:
```

**Estimated Time:** 2-3 days for full containerization

---

### 8.7 Document Storage for Production

**Status:** ⬜ Not Started  
**Priority:** HIGH

#### The Problem
Currently, parsed documents are stored in temp directory. For production we need:
1. **Persistent storage** - Survive restarts/deployments
2. **Queryable metadata** - Search by title, author, year, etc.
3. **Audit trail** - Who uploaded when, processing status
4. **Version control** - Re-process PDFs, track changes

#### Best Solution: PostgreSQL + S3/MinIO

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Metadata DB** | Document info, processing status | PostgreSQL |
| **Raw PDFs** | Original uploaded files | S3 / MinIO / Azure Blob |
| **Parsed Content** | Markdown, JSON from MinerU | S3 / MinIO / Azure Blob |
| **Vector Index** | Embeddings for search | Qdrant (already using) |

#### Database Schema

```sql
-- PostgreSQL Schema

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Source info
    original_filename VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,  -- SHA-256 for deduplication
    file_size_bytes BIGINT,
    
    -- Extracted metadata
    title VARCHAR(1000),
    authors TEXT[],
    year INTEGER,
    doi VARCHAR(100),
    abstract TEXT,
    
    -- Classification
    document_type VARCHAR(50),  -- 'systematic_review', 'rct', 'policy_brief'
    sectors TEXT[],
    countries TEXT[],
    
    -- Storage paths
    raw_pdf_path VARCHAR(500),      -- s3://bucket/pdfs/abc123.pdf
    parsed_md_path VARCHAR(500),    -- s3://bucket/parsed/abc123.md
    parsed_json_path VARCHAR(500),  -- s3://bucket/parsed/abc123.json
    
    -- Processing info
    processing_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    processing_error TEXT,
    mineru_version VARCHAR(20),
    
    -- Qdrant reference
    qdrant_collection VARCHAR(100),
    qdrant_point_ids UUID[],  -- IDs of all chunks in Qdrant
    
    -- Audit
    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    
    -- Search
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))
    ) STORED
);

CREATE INDEX idx_documents_status ON documents(processing_status);
CREATE INDEX idx_documents_search ON documents USING GIN(search_vector);
CREATE INDEX idx_documents_hash ON documents(file_hash);

CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    job_type VARCHAR(50),  -- 'initial', 'reprocess', 'update_metadata'
    status VARCHAR(20),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    worker_id VARCHAR(100),
    error_message TEXT
);
```

#### Why PostgreSQL + S3?

| Alternative | Pros | Cons | Verdict |
|-------------|------|------|---------|
| **MongoDB** | Flexible schema, JSON native | Less mature full-text search | ❌ Overkill for structured data |
| **Elasticsearch** | Great full-text search | Complex ops, high memory | ❌ Already have Qdrant |
| **SQLite** | Simple, embedded | No concurrent writes, no scale | ❌ Not for production |
| **PostgreSQL** | ACID, mature, full-text, JSON support | Needs separate file storage | ✅ Best for metadata |
| **Firestore** | Serverless, auto-scale | Vendor lock-in, limited queries | ❌ Less flexible |

**Recommendation:** PostgreSQL for metadata + S3/MinIO for files

**Estimated Time:** 3-4 days

---

### 8.8 PDF Retention Policy (Auto-Delete)

**Status:** ⬜ Not Started  
**Priority:** HIGH (for SaaS compliance)

#### Requirements
| Feature | Description | Status |
|---------|-------------|--------|
| Configurable retention | Default 30 days, user-adjustable | ⬜ |
| Auto-delete from R2 | Scheduled cleanup job | ⬜ |
| Delete parsed outputs | Remove MD/JSON when PDF deleted | ⬜ |
| Delete vectors | Remove from Qdrant when source deleted | ⬜ |
| Audit log | Track what was deleted and when | ⬜ |
| User notification | Email before deletion (optional) | ⬜ |

#### Implementation Options

| Approach | Pros | Cons |
|----------|------|------|
| **R2 Lifecycle Rules** | Native, zero code | Limited flexibility |
| **Modal scheduled job** | Full control, can clean Qdrant too | Requires code |
| **PostgreSQL + pg_cron** | Integrated with metadata | Needs pg_cron extension |

#### Recommended: Modal Scheduled Job + R2 Lifecycle

```python
# infrastructure/modal_mineru.py

@app.function(schedule=modal.Cron("0 3 * * *"))  # Daily at 3 AM
def cleanup_expired_documents():
    """Delete documents older than retention period."""
    retention_days = 30
    cutoff = datetime.now() - timedelta(days=retention_days)
    
    # Query expired documents from Turso
    expired = db.execute(
        "SELECT id, r2_key FROM documents WHERE uploaded_at < ? AND status = 'completed'",
        [cutoff.isoformat()]
    )
    
    for doc in expired:
        # Delete from R2
        s3.delete_object(Bucket=bucket, Key=doc.r2_key)
        s3.delete_object(Bucket=bucket, Key=f"outputs/md/{doc.id}.md")
        s3.delete_object(Bucket=bucket, Key=f"outputs/json/{doc.id}.json")
        
        # Delete vectors from Qdrant
        qdrant.delete(collection="devchat_v2", filter={"pdf_name": doc.id})
        
        # Mark as deleted in DB
        db.execute("UPDATE documents SET status = 'deleted' WHERE id = ?", [doc.id])
    
    return {"deleted": len(expired)}
```

**Estimated Time:** 1 day

---

## 🚀 Phase 8: Production PDF Pipeline (Cloud)

**Status:** ✅ COMPLETE  
**Completed:** December 18, 2025

### 8.1 Architecture Deployed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PRODUCTION PDF PIPELINE (Working!)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Upload                                                                │
│       │                                                                      │
│       ▼                                                                      │
│   ┌──────────────────┐                                                       │
│   │ FastAPI Backend  │  POST /admin/upload                                   │
│   │ (Local/Vercel)   │  POST /admin/jobs/trigger                            │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │  Cloudflare R2   │  input-pdfs/  ← uploaded PDFs                        │
│   │  (Storage)       │  outputs/md/  ← extracted markdown                   │
│   │  $0 egress       │  outputs/json/← structured JSON                      │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │  Modal (GPU)     │  T4 GPU, auto-scaling                                │
│   │  MinerU 2.6.8    │  Tables, formulas, OCR                               │
│   │                  │  ~2 min per 24-page paper                            │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │  Cohere          │  embed-v4.0 (1536 dims)                              │
│   │  (Embeddings)    │  search_document type                                │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │  Qdrant Cloud    │  Collection: devchat_v2                              │
│   │  (Vectors)       │  Named vector: dense                                 │
│   │  EU Region       │  Payload index: pdf_name                             │
│   └──────────────────┘                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Components Completed

| Component | Status | Details |
|-----------|--------|---------|
| **Modal App** | ✅ | `devchat-mineru` deployed |
| **R2 Bucket** | ✅ | `devchat-pdfs` with input/output folders |
| **Modal Secrets** | ✅ | r2-credentials, qdrant-credentials, cohere-credentials |
| **API Routes** | ✅ | `/admin/upload`, `/admin/r2/list`, `/admin/jobs/trigger` |
| **MinerU Integration** | ✅ | 2.6.x API with T4 GPU |
| **Qdrant Indexing** | ✅ | 1536-dim vectors with pdf_name index |
| **Smart Deduplication** | ✅ | Checks R2 + Qdrant before processing |

### 8.3 Smart Deduplication Logic

```
orchestrate() flow:
├── List PDFs in R2 input-pdfs/
├── Check R2 outputs/json/ for existing extractions
├── For each PDF:
│   ├── Has R2 output? 
│   │   ├── NO → Queue for full processing (GPU)
│   │   └── YES → Check Qdrant index
│   │       ├── Has chunks in Qdrant?
│   │       │   ├── YES → ✓ Skip (fully processed)
│   │       │   └── NO → Queue for re-indexing only (no GPU)
│   │       └── force_reprocess=True → Queue anyway
└── Return summary stats
```

**process_pdf() smart modes:**
- `skip_extraction=False` → Full MinerU + R2 upload + Qdrant index
- `skip_extraction=True` → Load from R2 JSON + Qdrant index only
- `force_reindex=True` → Delete old Qdrant chunks first

### 8.4 Test Results

**ALCE Paper (24 pages):**
```
✓ Extracted: 110,008 characters
✓ Tables: 21 HTML tables
✓ Processing time: ~2 min on T4 GPU
✓ Indexed: 31 chunks to Qdrant
✓ Semantic search working
✓ Smart dedup: Skips on re-run
```

### 8.5 Usage Commands

```powershell
# Process all new PDFs
modal run infrastructure/modal_mineru.py::orchestrate

# Force reprocess everything
modal run infrastructure/modal_mineru.py::orchestrate --force-reprocess

# Process single PDF
modal run infrastructure/modal_mineru.py::process_pdf --pdf-key "input-pdfs/paper.pdf"

# List PDFs in R2
modal run infrastructure/modal_mineru.py::list_pdfs

# Check Qdrant status
modal run infrastructure/modal_mineru.py::check_qdrant
```

### 8.6 Files Created/Modified

```
infrastructure/modal_mineru.py   # Main Modal app (840 lines)
api/routes.py                    # Added R2 upload, trigger endpoints
api/schemas.py                   # Added TriggerProcessingRequest
.env                             # Added R2 credentials
test_search.py                   # Quick semantic search test
```

### 8.7 Credentials Required (in Modal Secrets)

**r2-credentials:**
- R2_ACCOUNT_ID
- R2_ACCESS_KEY_ID
- R2_SECRET_ACCESS_KEY
- R2_BUCKET_NAME

**qdrant-credentials:**
- QDRANT_URL
- QDRANT_API_KEY

**cohere-credentials:**
- COHERE_API_KEY

---

## 🚀 Phase 9: PDF Parsing as a Service (SaaS)

**Status:** ⬜ PLANNING  
**Priority:** FUTURE OPPORTUNITY  
**Created:** December 18, 2025

### 9.1 Business Case

#### Market Analysis

| Competitor | Pricing | Target Market | Weakness |
|------------|---------|---------------|----------|
| Parsio | $41/1000 docs | General business | No academic optimization |
| Parseur | $0.01-0.05/page | Invoices, forms | No table/formula extraction |
| Adobe Acrobat | $15/mo + usage | Enterprise | Overkill, expensive |
| AWS Textract | $0.015/page | General | No academic structure |

#### Your Competitive Advantage

| Feature | MinerU-based Service | Competitors |
|---------|---------------------|-------------|
| **Table extraction** | ✅ HTML output, complex tables | ⚠️ Basic or none |
| **Math formulas** | ✅ LaTeX conversion | ❌ Rarely supported |
| **Multi-column layouts** | ✅ Academic paper aware | ⚠️ Often fails |
| **Figure captions** | ✅ Extracted with context | ⚠️ Usually ignored |
| **Cost** | ~$0.005/page | $0.01-0.05/page |

#### Positioning

> **"PDF parsing built for research"**  
> Systematic reviews, academic papers, scientific documents

Target customers:
- Evidence synthesis organizations (3ie network)
- Research NGOs
- Universities / libraries
- Think tanks
- Journals / publishers

### 9.2 Pricing Strategy

| Tier | Docs/month | Price | Per-doc cost | Margin |
|------|-----------|-------|--------------|--------|
| **Starter** | 100 | $5/mo | $0.05 | ~70% |
| **Pro** | 1,000 | $25/mo | $0.025 | ~75% |
| **Team** | 5,000 | $99/mo | $0.02 | ~80% |
| **Enterprise** | Unlimited | Custom | Negotiated | ~85% |

Alternative: **Pay-as-you-go**
- $0.005/page (~$0.15 for 30-page paper)
- No commitment, scales with usage

### 9.3 MVP Build Plan

| Component | Effort | Tools | Status |
|-----------|--------|-------|--------|
| **API endpoint** | 1 day | Modal `web_endpoint=True` | ⬜ |
| **Landing page** | 1-2 days | Framer / simple HTML | ⬜ |
| **Auth system** | 1-2 days | Clerk / Auth0 / Supabase | ⬜ |
| **Usage dashboard** | 3-4 days | Next.js (reuse Admin UI) | ⬜ |
| **Billing integration** | 2-3 days | Stripe (usage-based) | ⬜ |
| **Usage tracking/quotas** | 2-3 days | PostgreSQL / Turso | ⬜ |
| **API documentation** | 1 day | Swagger / Redoc | ⬜ |
| **Retention/cleanup** | 1 day | Modal scheduled job | ⬜ |

**Total MVP Time:** 3-4 weeks focused, 6-8 weeks part-time

### 9.4 Technical Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PDF PARSING SERVICE (SaaS)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────┐                          │
│  │   Landing Page   │         │   User Dashboard │                          │
│  │   (Marketing)    │         │   (Next.js)      │                          │
│  │   Framer/HTML    │         │   - Upload UI    │                          │
│  │                  │         │   - API Keys     │                          │
│  │   [Sign Up]      │────────▶│   - Usage Stats  │                          │
│  │                  │         │   - Billing      │                          │
│  └──────────────────┘         └────────┬─────────┘                          │
│                                        │                                     │
│  ┌─────────────────────────────────────┼─────────────────────────────────┐  │
│  │                           AUTH LAYER                                   │  │
│  │                     Clerk / Auth0 / Supabase                          │  │
│  │              API Keys + JWT + Usage Quotas                            │  │
│  └─────────────────────────────────────┼─────────────────────────────────┘  │
│                                        │                                     │
│  ┌─────────────────────────────────────▼─────────────────────────────────┐  │
│  │                           API LAYER (Modal)                            │  │
│  │                                                                        │  │
│  │   POST /v1/parse                                                       │  │
│  │   ├── Upload PDF (multipart or presigned URL)                         │  │
│  │   ├── Validate API key + check quota                                  │  │
│  │   ├── Queue processing job                                            │  │
│  │   └── Return job_id                                                   │  │
│  │                                                                        │  │
│  │   GET /v1/jobs/{job_id}                                               │  │
│  │   └── Return status + results when complete                           │  │
│  │                                                                        │  │
│  │   GET /v1/usage                                                       │  │
│  │   └── Return current period usage stats                               │  │
│  │                                                                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                        │                                     │
│  ┌─────────────────────────────────────▼─────────────────────────────────┐  │
│  │                      PROCESSING LAYER (Modal GPU)                      │  │
│  │                                                                        │  │
│  │   process_pdf()  [T4 GPU, auto-scaling]                               │  │
│  │   ├── Download from R2                                                │  │
│  │   ├── Run MinerU extraction                                           │  │
│  │   ├── Upload results to R2                                            │  │
│  │   ├── Increment usage counter                                         │  │
│  │   └── Return structured output                                        │  │
│  │                                                                        │  │
│  │   cleanup_expired()  [Daily cron]                                     │  │
│  │   └── Delete files older than retention period                        │  │
│  │                                                                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           STORAGE LAYER                                  ││
│  │                                                                          ││
│  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  ││
│  │   │ Cloudflare   │  │   Turso      │  │   Stripe     │                  ││
│  │   │ R2 (files)   │  │   (metadata) │  │   (billing)  │                  ││
│  │   │              │  │              │  │              │                  ││
│  │   │ /uploads/    │  │ users        │  │ subscriptions││
│  │   │ /outputs/    │  │ api_keys     │  │ usage_records││
│  │   │              │  │ jobs         │  │ invoices     │                  ││
│  │   │ 30-day TTL   │  │ usage        │  │              │                  ││
│  │   └──────────────┘  └──────────────┘  └──────────────┘                  ││
│  │                                                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.5 API Design

```bash
# Upload and parse a PDF
curl -X POST https://api.researchparser.io/v1/parse \
  -H "Authorization: Bearer sk_live_xxx" \
  -F "file=@paper.pdf" \
  -F "output_format=json"  # json, markdown, or both

# Response
{
  "job_id": "job_abc123",
  "status": "processing",
  "estimated_seconds": 45,
  "pages": 24
}

# Check status
curl https://api.researchparser.io/v1/jobs/job_abc123 \
  -H "Authorization: Bearer sk_live_xxx"

# Response (when complete)
{
  "job_id": "job_abc123",
  "status": "completed",
  "result": {
    "title": "Impact of Cash Transfers on Education",
    "authors": ["Smith, J.", "Jones, M."],
    "year": 2023,
    "abstract": "...",
    "content": "Full markdown text...",
    "tables": [
      {"page": 5, "html": "<table>...</table>", "caption": "Table 1: ..."}
    ],
    "formulas": [
      {"page": 12, "latex": "y = \\beta_0 + \\beta_1 x + \\epsilon"}
    ],
    "pages": 24
  },
  "download_urls": {
    "markdown": "https://r2.../outputs/abc123.md?token=...",
    "json": "https://r2.../outputs/abc123.json?token=..."
  },
  "expires_at": "2025-01-17T12:00:00Z"  # 30-day retention
}
```

### 9.6 Database Schema (SaaS additions)

```sql
-- Users and API keys
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    stripe_customer_id VARCHAR(100),
    plan VARCHAR(50) DEFAULT 'free'  -- free, starter, pro, team, enterprise
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    key_hash VARCHAR(64) NOT NULL,  -- SHA-256 of the key
    key_prefix VARCHAR(12) NOT NULL,  -- sk_live_abc... for display
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Usage tracking
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    job_id UUID,
    pages_processed INTEGER,
    processing_seconds FLOAT,
    cost_usd DECIMAL(10, 6),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE monthly_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    period VARCHAR(7),  -- '2025-01'
    docs_processed INTEGER DEFAULT 0,
    pages_processed INTEGER DEFAULT 0,
    quota_docs INTEGER,
    quota_pages INTEGER,
    UNIQUE(user_id, period)
);

-- Jobs for async processing
CREATE TABLE parsing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    filename VARCHAR(500),
    r2_input_key VARCHAR(500),
    r2_output_key VARCHAR(500),
    status VARCHAR(20) DEFAULT 'pending',
    pages INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    result JSONB,
    expires_at TIMESTAMP,  -- For retention policy
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_jobs_user ON parsing_jobs(user_id);
CREATE INDEX idx_jobs_status ON parsing_jobs(status);
CREATE INDEX idx_jobs_expires ON parsing_jobs(expires_at);
```

### 9.7 Revenue Projections

| Scenario | Users | Avg Revenue | MRR | Annual |
|----------|-------|-------------|-----|--------|
| **Conservative** | 50 | $30 | $1,500 | $18,000 |
| **Moderate** | 200 | $40 | $8,000 | $96,000 |
| **Optimistic** | 500 | $50 | $25,000 | $300,000 |

**Costs (at scale):**
- Modal GPU: ~$0.005/page × usage
- R2 storage: ~$0.015/GB (minimal)
- Turso: Free tier → $29/mo
- Clerk/Auth: Free → $25/mo
- Stripe: 2.9% + $0.30/transaction

**Estimated margin: 70-85%**

### 9.8 Go-to-Market Strategy

1. **Soft launch** (Week 1-2)
   - Invite 3ie network to beta test
   - Collect feedback, fix bugs

2. **Public beta** (Week 3-4)
   - Free tier (10 docs/month)
   - Landing page live
   - Post on Twitter/LinkedIn

3. **Paid launch** (Month 2)
   - Enable Stripe billing
   - Announce paid tiers
   - Reach out to research orgs

4. **Growth** (Month 3+)
   - SEO content (blog posts on PDF parsing)
   - Integration guides (Zotero, Mendeley, etc.)
   - API client libraries (Python, JS)

---

### 8.9 Updated Implementation Priority

| Priority | Task | Time | Dependencies | Status |
|----------|------|------|--------------|--------|
| 1 | ~~Modal + R2 infrastructure~~ | ~~2 days~~ | None | ✅ |
| 2 | ~~Admin UI~~ | ~~3 days~~ | None | ✅ |
| 3 | Wire upload to R2 | 1 day | Modal secrets | ⬜ |
| 4 | PDF retention/cleanup | 1 day | #3 | ⬜ |
| 5 | Authentication (Clerk) | 2 days | None | ⬜ |
| 6 | **SaaS: Public API endpoint** | 1 day | #1 | ⬜ |
| 7 | **SaaS: Landing page** | 2 days | None | ⬜ |
| 8 | **SaaS: Usage dashboard** | 3 days | #2, #5 | ⬜ |
| 9 | **SaaS: Stripe billing** | 3 days | #5, #8 | ⬜ |

**DevChat v2 completion:** ~3 days more  
**SaaS MVP additional:** ~2-3 weeks

---

### 8.9 Quick Wins (Can Do Now)

| Task | Time | Impact |
|------|------|--------|
| Install `huggingface_hub[hf_xet]` | 1 min | Faster model downloads |
| Configure MinerU output to project folder | 5 min | Persistent output |
| Add basic batch processing script | 1 hour | Process multiple PDFs |
| Update requirements.txt with mineru | 5 min | Document dependencies |

---

## 🔮 Phase 10: Hyperscience-Style Pipeline (Future)

**Reference:** [hyperscience.ai](https://hyperscience.ai)

### 10.1 Pipeline Architecture

```
┌─────────┐   ┌────────────────┐   ┌────────────┐   ┌─────────────────────┐
│  Input  │ → │ Classification │ → │ Extraction │ → │ Human-in-the-Loop   │
│ (PDFs)  │   │   (ML model)   │   │  (MinerU)  │   │ Exception Handling  │
└─────────┘   └────────────────┘   └────────────┘   └─────────────────────┘
                                                              │
                                                              ▼
┌─────────┐   ┌─────────────┐   ┌────────────┐   ┌────────────────────────┐
│ Output  │ ← │ Decisioning │ ← │ Validation │ ← │ Human Review Queue     │
│ (JSON)  │   │  (Rules)    │   │  (QA/LLM)  │   │                        │
└─────────┘   └─────────────┘   └────────────┘   └────────────────────────┘
```

### 10.2 Pipeline Stages

| Stage | Current | Future Enhancement |
|-------|---------|-------------------|
| **Input** | Manual upload | Batch intake, email parsing, API |
| **Classification** | None | Auto-detect: RCT, SR, Report, etc. |
| **Extraction** | MinerU | + Custom field extraction per doc type |
| **HITL Exception** | None | Flag low-confidence pages for review |
| **Validation** | None | LLM cross-check, schema validation |
| **Decisioning** | None | Auto-route: index, reject, escalate |
| **Output** | Qdrant only | + Structured JSON, API delivery |

### 10.3 Classification Model

Train lightweight classifier for research document types:

```python
# Future: Document classification
DOCUMENT_TYPES = [
    "randomized_controlled_trial",
    "systematic_review",
    "meta_analysis", 
    "impact_evaluation",
    "working_paper",
    "policy_brief",
    "technical_report",
    "other"
]

# Use first 2 pages + title for classification
# Fine-tune on 3ie document corpus
```

### 10.4 Human-in-the-Loop (HITL) Features

1. **Confidence Scoring**
   - MinerU extraction confidence per page
   - Flag pages with <80% confidence for human review

2. **Review Queue UI**
   - Show flagged pages with original PDF side-by-side
   - Allow corrections to extracted text
   - Feed corrections back for model improvement

3. **Exception Types**
   - Poor scan quality
   - Complex tables
   - Handwritten content
   - Multi-column layouts
   - Non-English text

### 10.5 Validation Layer

```python
# Future: Multi-stage validation
class DocumentValidator:
    def validate(self, extracted_data):
        checks = [
            self.check_completeness(),      # All expected fields?
            self.check_consistency(),       # Dates, authors match?
            self.check_quality(),           # Readability score
            self.llm_cross_reference(),     # LLM sanity check
        ]
        return ValidationResult(checks)
```

### 10.6 Implementation Priority

| Feature | Priority | Effort | Value |
|---------|----------|--------|-------|
| Confidence scoring | High | 1 week | Catches extraction errors |
| Document classification | Medium | 2 weeks | Auto-routing, better chunking |
| Review queue UI | Medium | 2 weeks | Quality assurance |
| Validation layer | Low | 1 week | Error prevention |
| Custom field extraction | Low | 3 weeks | Structured data output |

**Total estimated effort:** 9-10 weeks for full Hyperscience-style pipeline

---


