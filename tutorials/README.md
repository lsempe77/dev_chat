# DevChat Learning Path: From Zero to Production RAG

**A 50-Part Tutorial Series**

> Learn to build a production-grade RAG application by studying the DevChat codebase.  
> No prior experience required - we'll start from fundamentals and build up to advanced techniques.

---

## 🎯 What You'll Learn

By the end of this series, you'll understand:
- **Backend Development**: FastAPI, async Python, Pydantic validation
- **Frontend Development**: Next.js 15, React hooks, TypeScript
- **RAG Systems**: Embeddings, vector search, retrieval, synthesis
- **Production Deployment**: Docker, Railway, Vercel, Modal
- **Best Practices**: Testing, logging, observability, security

---

## 📚 Tutorial Structure

### Part 1: Foundations (Posts 1-10)
Learn the basics of Python, web development, and project setup.

| # | Title | Topics | Time |
|---|-------|--------|------|
| 01 | [Project Overview & Architecture](01-foundations/01-project-overview.md) | System design, tech stack | 30min |
| 02 | [Python Fundamentals for DevChat](01-foundations/02-python-fundamentals.md) | Type hints, async/await, Pydantic | 45min |
| 03 | [FastAPI Backend Basics](01-foundations/03-fastapi-basics.md) | Routes, schemas, validation | 60min |
| 04 | [Next.js Frontend Basics](01-foundations/04-nextjs-basics.md) | App router, components, hooks | 60min |
| 05 | [Database Setup with Supabase](01-foundations/05-database-setup.md) | PostgreSQL, RLS, migrations | 45min |
| 06 | [Authentication & Authorization](01-foundations/06-authentication.md) | Supabase Auth, JWT, RBAC | 45min |
| 07 | [Environment Setup & Configuration](01-foundations/07-environment-setup.md) | .env files, secrets management | 30min |
| 08 | [Error Handling & Logging](01-foundations/08-error-handling.md) | loguru, structured logging | 45min |
| 09 | [Testing Basics](01-foundations/09-testing-basics.md) | pytest, mocking, API tests | 45min |
| 10 | [Deployment Pipeline](01-foundations/10-deployment-pipeline.md) | CI/CD, Railway, Vercel | 45min |

### Part 2: Document Processing (Posts 11-20)
Learn how to process PDFs and extract structured data.

| # | Title | Topics | Time |
|---|-------|--------|------|
| 11 | [PDF Upload Flow](02-document-processing/11-pdf-upload.md) | File handling, validation | 45min |
| 12 | [MinerU GPU Parsing](02-document-processing/12-mineru-parsing.md) | GPU acceleration, tables | 60min |
| 13 | [Modal Serverless Functions](02-document-processing/13-modal-intro.md) | Containers, volumes | 60min |
| 14 | [Text Chunking Strategies](02-document-processing/14-chunking.md) | Parent-child, page-aware | 45min |
| 15 | [Metadata Enrichment](02-document-processing/15-metadata-enrichment.md) | CrossRef, OpenAlex APIs | 60min |
| 16 | [Study Design Classification](02-document-processing/16-study-design.md) | LLM classification | 45min |
| 17 | [Cloudflare R2 Storage](02-document-processing/17-r2-storage.md) | Object storage, CDN | 30min |
| 18 | [Document Deduplication](02-document-processing/18-deduplication.md) | Hashing, DOI matching | 30min |
| 19 | [Zotero Integration](02-document-processing/19-zotero.md) | API sync, collections | 45min |
| 20 | [Processing Pipeline](02-document-processing/20-pipeline.md) | Orchestration, error handling | 60min |

### Part 3: Vector Search & RAG (Posts 21-30)
Build the core retrieval system.

| # | Title | Topics | Time |
|---|-------|--------|------|
| 21 | [What is RAG?](03-rag-system/21-rag-intro.md) | Concepts, architecture | 30min |
| 22 | [Embeddings Explained](03-rag-system/22-embeddings.md) | Vector representations | 45min |
| 23 | [Qdrant Vector Database](03-rag-system/23-qdrant-setup.md) | Collections, indexing | 60min |
| 24 | [Dense Vector Search](03-rag-system/24-dense-search.md) | Cohere embed-v4 | 45min |
| 25 | [Sparse Vector Search (BM25)](03-rag-system/25-sparse-search.md) | Keyword matching | 45min |
| 26 | [Hybrid Search Implementation](03-rag-system/26-hybrid-search.md) | Combining signals | 60min |
| 27 | [Reranking with Cohere](03-rag-system/27-reranking.md) | Precision improvement | 45min |
| 28 | [Contextual Retrieval](03-rag-system/28-contextual-retrieval.md) | Anthropic's technique | 60min |
| 29 | [Query Understanding](03-rag-system/29-query-understanding.md) | HyDE, expansion | 45min |
| 30 | [Retrieval Evaluation](03-rag-system/30-retrieval-eval.md) | Metrics, testing | 60min |

### Part 4: Synthesis & Citations (Posts 31-40)
Generate grounded responses with citations.

| # | Title | Topics | Time |
|---|-------|--------|------|
| 31 | [LLM Integration](04-synthesis/31-llm-integration.md) | OpenRouter, streaming | 60min |
| 32 | [Prompt Engineering](04-synthesis/32-prompt-engineering.md) | System prompts, few-shot | 45min |
| 33 | [Claim Ledger Pattern](04-synthesis/33-claim-ledger.md) | Two-pass extraction | 60min |
| 34 | [Citation Extraction](04-synthesis/34-citation-extraction.md) | Regex, validation | 45min |
| 35 | [Source Attribution](04-synthesis/35-source-attribution.md) | Matching claims to docs | 60min |
| 36 | [MiniCheck Verification](04-synthesis/36-minicheck.md) | NLI grounding | 60min |
| 37 | [PDF Highlighting](04-synthesis/37-pdf-highlighting.md) | PyMuPDF, annotations | 45min |
| 38 | [Response Streaming](04-synthesis/38-streaming.md) | SSE, chunked transfer | 45min |
| 39 | [Caching Strategies](04-synthesis/39-caching.md) | Redis, response cache | 45min |
| 40 | [Quality Metrics](04-synthesis/40-quality-metrics.md) | Faithfulness, precision | 60min |

### Part 5: Admin & Advanced Features (Posts 41-50)
Add production features and deploy.

| # | Title | Topics | Time |
|---|-------|--------|------|
| 41 | [Multi-tenancy](05-production/41-multi-tenancy.md) | RLS, user isolation | 60min |
| 42 | [Admin Dashboard](05-production/42-admin-dashboard.md) | Stats, monitoring | 60min |
| 43 | [Cost Tracking](05-production/43-cost-tracking.md) | Usage logs, billing | 45min |
| 44 | [Langfuse Observability](05-production/44-langfuse.md) | Tracing, debugging | 60min |
| 45 | [Per-RAG Configuration](05-production/45-per-rag-config.md) | Model selection, prompts | 45min |
| 46 | [Extraction Pipeline](05-production/46-extraction-pipeline.md) | Structured data extraction | 60min |
| 47 | [Docker & Deployment](05-production/47-docker-deployment.md) | Railway, Vercel | 60min |
| 48 | [CI/CD Pipeline](05-production/48-cicd.md) | GitHub Actions | 45min |
| 49 | [Security Best Practices](05-production/49-security.md) | Auth, rate limiting | 45min |
| 50 | [Scaling & Performance](05-production/50-scaling.md) | Optimization, monitoring | 60min |

---

## 🎓 How to Use This Tutorial

### Prerequisites
- Basic programming knowledge (any language)
- Familiarity with terminal/command line
- A text editor (VS Code recommended)
- Accounts: GitHub, Supabase, Qdrant Cloud

### Recommended Path
1. **Start at Post 1** - Don't skip ahead, concepts build on each other
2. **Code Along** - Type out examples, don't just copy-paste
3. **Read the Source** - Reference actual DevChat files mentioned
4. **Experiment** - Break things, fix them, learn by doing
5. **Build Projects** - Apply learnings to your own ideas

### Time Commitment
- **Full series**: ~42 hours total
- **Per post**: 30-60 minutes
- **Suggested pace**: 2-3 posts per week = 4-6 months

---

## 🎯 Learning Outcomes by Part

### After Part 1 (Foundations)
✅ Understand Python async programming  
✅ Build basic FastAPI endpoints  
✅ Create React components with Next.js  
✅ Set up dev environment  

### After Part 2 (Document Processing)
✅ Process PDFs with GPU acceleration  
✅ Extract and enrich metadata  
✅ Build serverless functions with Modal  
✅ Implement document pipelines  

### After Part 3 (Vector Search & RAG)
✅ Understand embeddings and vector search  
✅ Build hybrid search systems  
✅ Implement reranking  
✅ Evaluate retrieval quality  

### After Part 4 (Synthesis & Citations)
✅ Integrate LLMs effectively  
✅ Generate citation-grounded responses  
✅ Verify factual accuracy  
✅ Build interactive PDF viewers  

### After Part 5 (Production)
✅ Deploy to production  
✅ Monitor and debug at scale  
✅ Implement security best practices  
✅ Build admin interfaces  

---

## 📝 Contributing

Found an error or have a suggestion? Open an issue or PR:
- **Typos/errors**: Fix directly and submit PR
- **Missing topics**: Open issue with suggestion
- **Code improvements**: Reference specific tutorial post

---

## 🙏 Acknowledgments

This tutorial series is based on the real-world DevChat project built for **3ie** (International Initiative for Impact Evaluation). All code examples are production-tested.

---

**Ready to start?** 👉 [Begin with Post 1: Project Overview](01-foundations/01-project-overview.md)
