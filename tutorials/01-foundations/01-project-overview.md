# Post 1: Project Overview & Architecture

**Part 1 of 50** | ⏱️ 30 minutes | [Next: Python Fundamentals →](02-python-fundamentals.md)

---

## 🎯 What You'll Learn

- What DevChat is and what problem it solves
- The high-level architecture of a RAG application
- How the different components fit together
- The tech stack and why each piece was chosen

---

## 📖 What is DevChat?

DevChat is a **production-grade RAG (Retrieval-Augmented Generation) application** for academic research. It helps researchers:

1. **Upload PDFs** from their research library
2. **Ask questions** in natural language
3. **Get answers** with inline citations that link to specific pages
4. **Verify sources** by jumping directly to referenced text

### The Problem It Solves

Researchers often need to:
- Review 50-100 papers for a literature review
- Find specific evidence across many studies
- Ensure claims are properly cited
- Synthesize findings from multiple sources

Manually doing this takes **weeks**. DevChat does it in **seconds**.

---

## 🏗️ High-Level Architecture

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │
       ├─── Upload PDF ─────┐
       │                    │
       │                    ▼
       │            ┌──────────────┐
       │            │   Modal      │  GPU Processing
       │            │  (MinerU)    │  - Parse tables
       │            └───────┬──────┘  - Extract text
       │                    │
       │                    ▼
       │            ┌──────────────┐
       │            │  Embeddings  │  Create vectors
       │            │  (Cohere)    │  - Dense: embed-v4
       │            └───────┬──────┘  - Sparse: BM25
       │                    │
       │                    ▼
       │            ┌──────────────┐
       │            │   Qdrant     │  Store vectors
       │            │ (Vector DB)  │  - 6,769 chunks
       │            └──────────────┘  - Hybrid search
       │
       └─── Ask Question ───┐
                           │
                           ▼
                   ┌──────────────┐
                   │   Backend    │  FastAPI
                   │  (Railway)   │  - Search Qdrant
                   └───────┬──────┘  - Rerank results
                           │
                           ▼
                   ┌──────────────┐
                   │   LLM        │  Generate answer
                   │ (OpenRouter) │  - Extract claims
                   └───────┬──────┘  - Match citations
                           │
                           ▼
                   ┌──────────────┐
                   │  Frontend    │  Next.js
                   │  (Vercel)    │  - Display answer
                   └──────────────┘  - Highlight PDF
```

---

## 🔧 Tech Stack Breakdown

### Frontend
- **Next.js 15**: React framework with App Router
- **TypeScript**: Type safety for JavaScript
- **Tailwind CSS**: Utility-first CSS framework
- **shadcn/ui**: Pre-built accessible components

**Why?** Modern, fast, great DX, excellent for data-heavy apps.

### Backend
- **FastAPI**: Python async web framework
- **Pydantic v2**: Data validation
- **Python 3.12**: Latest stable Python

**Why?** Fast, async-native, great for AI/ML integration.

### Database
- **Supabase PostgreSQL**: Relational database
- **Row Level Security (RLS)**: Multi-tenant isolation

**Why?** Managed PostgreSQL with built-in auth and security.

### Vector Database
- **Qdrant Cloud**: Vector search engine
- **Hybrid search**: Dense + Sparse vectors

**Why?** Best-in-class vector search with hybrid capabilities.

### PDF Processing
- **Modal**: Serverless GPU compute
- **MinerU**: GPU-accelerated PDF parsing

**Why?** Handle compute-heavy PDF parsing without managing servers.

### Storage
- **Cloudflare R2**: Object storage (S3-compatible)

**Why?** Cheaper than S3, no egress fees.

### AI/ML
- **Cohere**: Embeddings (embed-v4) + Reranking (rerank-v3.5)
- **OpenRouter**: LLM gateway (GPT-4o, Claude, Gemini)
- **MiniCheck**: Fact verification with NLI

**Why?** Best-in-class models, easy integration, competitive pricing.

### Observability
- **Langfuse**: LLM tracing and debugging

**Why?** Purpose-built for LLM observability, great UI.

---

## 📊 Data Flow Example

Let's trace what happens when you ask: *"What are the main findings from RCTs on cash transfers?"*

### Step 1: Query Processing
```python
# User query comes in via Next.js frontend
query = "What are the main findings from RCTs on cash transfers?"
```

### Step 2: Vector Search
```python
# Backend converts query to vectors
dense_vector = cohere.embed([query])  # 1536 dimensions
sparse_vector = bm25_vectorize(query)  # Keyword matching

# Search Qdrant with hybrid search
results = qdrant.search(
    collection="documents",
    query_vector=dense_vector,
    sparse_vector=sparse_vector,
    limit=50
)
```

### Step 3: Reranking
```python
# Rerank top 50 results to get best 10
reranked = cohere.rerank(
    query=query,
    documents=[r.content for r in results],
    top_n=10
)
```

### Step 4: Synthesis
```python
# Pass context to LLM with structured prompt
context = "\n\n".join([doc.content for doc in reranked])

prompt = f"""Based on these research documents:
{context}

Answer: {query}

Extract specific claims and cite sources."""

response = openrouter.chat(prompt)
```

### Step 5: Citation Extraction
```python
# Extract claims and match to sources
claims = extract_claims(response)  # "Cash transfers increased income by 25%"
for claim in claims:
    sources = match_to_documents(claim, reranked)
    claim.citations = sources  # [Author2020, p.42]
```

### Step 6: Verification
```python
# Verify each claim with MiniCheck
for claim in claims:
    is_supported = minicheck.verify(
        claim=claim.text,
        context=claim.source_text
    )
    claim.verified = is_supported
```

### Step 7: Display
```typescript
// Frontend renders answer with inline citations
<Answer>
  Cash transfers increased income by 25%{' '}
  <Citation onClick={() => jumpToPDF('Author2020', 42)}>
    [Author2020, p.42]
  </Citation>
</Answer>
```

---

## 🧩 Key Concepts

### What is RAG?

**Retrieval-Augmented Generation** = Search + LLM

Traditional LLM:
```
User: "What does the research say?"
LLM: *hallucinates* "Studies show..." (no sources!)
```

RAG:
```
User: "What does the research say?"
System: 
  1. Search vector DB for relevant docs
  2. Pass docs to LLM as context
  3. LLM answers based on actual sources
  4. Display answer with citations
```

### Why RAG?

- **Grounded**: Answers cite real sources
- **Up-to-date**: Add new docs anytime
- **Transparent**: Users can verify claims
- **Domain-specific**: Your data, not generic web training

---

## 🎯 System Requirements

To run DevChat locally, you'll need:

### Accounts (Free Tiers Available)
- GitHub (code hosting)
- Supabase (database + auth)
- Qdrant Cloud (vector search)
- Modal (GPU processing)
- Cohere (embeddings + reranking)
- OpenRouter (LLM access)
- Cloudflare (R2 storage)

### Local Development
- **OS**: Windows, macOS, or Linux
- **Python**: 3.12+
- **Node.js**: 18+
- **RAM**: 8GB+ recommended
- **Storage**: 5GB for dependencies

---

## 🚀 Next Steps

Now that you understand the **what** and **why**, let's learn **how** to build it!

**Next:** [Post 2: Python Fundamentals →](02-python-fundamentals.md)

In the next post, we'll cover the Python concepts you need to understand the DevChat codebase:
- Type hints and Pydantic models
- Async/await for concurrent operations
- Python project structure
- Common patterns in the codebase

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Learn Course](https://nextjs.org/learn)
- [What is RAG?](https://www.anthropic.com/news/contextual-retrieval) - Anthropic blog
- [Vector Databases Explained](https://qdrant.tech/articles/what-is-a-vector-database/)

---

## ✅ Knowledge Check

Before moving on, make sure you can answer:

1. What problem does DevChat solve?
2. What are the main components of the architecture?
3. What is RAG and why is it better than a plain LLM?
4. What database stores the vectors?
5. What service processes the PDFs?

<details>
<summary>Click to reveal answers</summary>

1. Helps researchers quickly find evidence across many papers with citations
2. Frontend (Next.js), Backend (FastAPI), Vector DB (Qdrant), PDF Processing (Modal), LLM (OpenRouter)
3. RAG combines search with LLM generation, providing grounded answers with citations
4. Qdrant Cloud
5. Modal (using MinerU for GPU-accelerated parsing)

</details>

---

[🏠 Back to Index](../README.md) | [Next: Python Fundamentals →](02-python-fundamentals.md)
