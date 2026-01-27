# Changelog

## [2.0.0] - 2026-01-27

### Added
- Binary quantization for 32x faster search
- Scalar quantization option (configurable)
- Multi-Query RAG-Fusion (+10-15% recall)
- Semantic cache for similar queries
- Query decomposition for complex questions
- Step-back prompting for specific questions
- HNSW tuning (m=16, ef_construct=200)
- MMR diversity (lambda=0.7)
- Lost-in-Middle reordering
- Embedding cache (MD5 hash)
- Retrieval metrics (Recall@K, NDCG, MRR)
- Sphinx documentation

### Changed
- Renamed `pipeline_v2_sota.py` to `pipeline.py`
- Renamed `analyze_effect_sizes.py` to `validate_extraction.py`
- Archived old extraction scripts (v3-v8) to `evaluation/archive/`

### Infrastructure
- Modal deployment with 8 modular components
- Cohere embed-v4 for embeddings
- Cohere rerank-v3.5 for reranking
- MineRU for PDF parsing

## [1.0.0] - 2025-12-01

### Added
- Initial release
- Multi-tenant RAG
- Hybrid search (dense + sparse)
- Claim Ledger synthesis
- MiniCheck verification
- PDF citation highlighting
- Contextual retrieval
- Parent-child chunking
- Study design classification
- Zotero integration
- Bibliography import
