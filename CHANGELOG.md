# Changelog

All notable changes to DevChat v2.0 are documented in this file.

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
| 2.0.5 | 2026-01-03 | Sparse vectors, repo cleanup |
| 2.0.4 | 2026-01-02 | Pagination, hallucination fix |
| 2.0.3 | 2025-12-31 | Multi-tenant RAG platform |
| 2.0.2 | 2025-12-28 | Citation quality at target |
| 2.0.1 | 2025-12-22 | Metadata editor, item types |
| 2.0.0 | 2025-12-17 | Initial SOTA release |
