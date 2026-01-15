# Changelog

All notable changes to DevChat v2.0 are documented in this file.

## [2.0.10] - 2026-01-15

### Changed
- Complete documentation overhaul: SETUP_TRACKER.md and ROADMAP.md rewritten with clear status dashboards
- Removed verbose aspirational code examples from ROADMAP.md (434→143 lines)

---

## [2.0.9] - 2026-01-14

### Added
- **Extraction Pipeline V2 SOTA** - Production table extraction using BeautifulSoup
  - 100% match on Bossuroy Table 1 (18/18 rows)
  - Rules-based + LLM classification for results vs descriptive tables
  - Output: CSV + JSON to `extraction_pipeline/outputs/{study_id}/`

### Changed
- Project reorganization: renamed docs, archived old extractors (v10-v17)
- Moved FURTHER_IMPROVEMENTS.md → docs/ROADMAP.md
- Moved EVALUATION_FRAMEWORK.md → docs/EVALUATION.md

---

## [2.0.8] - 2026-01-08

### Added
- **Contextual Retrieval** - Anthropic's 49% improvement technique
  - LLM-generated context prefixes for each chunk
  - New Qdrant fields: `contextual_prefix`, `text_with_context`
  - 97 PDFs reprocessed, 6,769 chunks with prefixes

---

## [2.0.7] - 2026-01-07

### Added
- **Modal Pipeline Refactoring** - Modular architecture
  - Split 1700-line modal_mineru.py into 8 modules in modal_lib/
  - Entry point now 230 lines (87% reduction)
- **Study Design Classification** - 22 types with LLM classifier
  - StudyDesignBadge frontend component
  - 96 documents classified (34 RCT, 10 DiD, etc.)
- **Parent-Child Chunking** - Small chunks for search, parent for context
  - ParentChildChunker in src/ingestion/chunking.py

### Fixed
- Webhook timeout via `.spawn()` background processing
- Stale job auto-cleanup (>30 min marked as failed)

---

## [2.0.6] - 2026-01-06

### Added
- **PDF Citation Highlighting** - PyMuPDF with inline viewer
  - Endpoint: `/rags/{id}/documents/{doc_id}/pdf-highlighted`
  - Toggle button to switch Evidence panel ↔ PDF viewer
  - Evidence snippet card with copy button
- **Prompt Customization** - Per-RAG extraction/synthesis prompts
  - Prompt history with restore (max 10 versions)
  - Safety: acknowledge_risk checkbox
- **Chat History Caching** - Citations robustly cached to Supabase

---

## [2.0.5] - 2026-01-03

### Added
- Sparse vector support in Modal indexing for hybrid search
- "Mark as reviewed" checkbox in metadata editor (save doesn't auto-mark)
- BM25-style sparse vectors for keyword matching

### Fixed
- Qdrant collection name mismatch (dashes vs no-dashes)
- Fallback to dense-only search when collection lacks sparse vectors
- Metadata panel scroll staying within card bounds
- Compact header when panel is narrow (1/3 width)

### Changed
- Modal now looks up collection name from database instead of guessing
- Reorganized repository (archived old files, moved eval scripts)

---

## [2.0.4] - 2026-01-02

### Added
- Backend pagination for document/metadata lists
- Hallucination prevention (0.8 similarity threshold for metadata enrichment)

### Fixed
- Layout regression where document list disappeared when editing
- Flexbox scroll issues in metadata panel

---

## [2.0.3] - 2025-12-31

### Added
- Multi-tenant RAG platform with Supabase auth
- Per-user RAG projects with isolated Qdrant collections
- Public RAG sharing via slugs (/r/{slug})
- Full Documents/Metadata/Processing/Settings tabs
- Drag-drop and batch PDF upload
- Content-hash deduplication

### Changed
- Migrated from single collection to per-project collections
- Added Row Level Security to all tables

---

## [2.0.2] - 2025-12-28

### Added
- Claim Ledger synthesis for grounded responses
- Hybrid BM25+Dense search (Qdrant native)
- Contextual retrieval with document prefixes
- Post-hoc verification (NLI-based)
- Citation coverage validator

### Achieved
- **Faithfulness: 0.699** (target: 0.70+) ✅
- **Citation Recall: 1.000** ✅
- **Citation Precision: 1.000** ✅

---

## [2.0.1] - 2025-12-22

### Added
- Side-by-side metadata editor with PDF viewer
- Item types (article, book, report, thesis, etc.)
- Volume, issue, pages extraction
- 256-word chunks for better RAG precision

### Fixed
- False positive bug in has_useful_content detection

---

## [2.0.0] - 2025-12-17

### Initial Release
- FastAPI backend with modular routes
- Next.js 15 frontend
- MinerU PDF processing on Modal
- Cohere embed-v4 embeddings
- CrossRef/OpenAlex metadata enrichment
- Qdrant vector storage
- PostgreSQL metadata store
- Langfuse observability

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 2.0.10 | 2026-01-15 | Documentation overhaul |
| 2.0.9 | 2026-01-14 | Extraction Pipeline V2 SOTA |
| 2.0.8 | 2026-01-08 | Contextual Retrieval |
| 2.0.7 | 2026-01-07 | Modal refactoring, Study Design, Parent-Child |
| 2.0.6 | 2026-01-06 | PDF highlighting, Prompt customization |
| 2.0.5 | 2026-01-03 | Sparse vectors, repo cleanup |
| 2.0.4 | 2026-01-02 | Pagination, hallucination fix |
| 2.0.3 | 2025-12-31 | Multi-tenant RAG platform |
| 2.0.2 | 2025-12-28 | Citation quality at target |
| 2.0.1 | 2025-12-22 | Metadata editor, item types |
| 2.0.0 | 2025-12-17 | Initial SOTA release |
