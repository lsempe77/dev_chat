# Copilot Instructions for DevChat

## ⚠️ IMPORTANT: Documentation Maintenance

**This project has 4 key documentation files that MUST be kept synchronized:**

1. **README.md** (Root) - Project overview, features, quick start, learning resources
   - Update when: Adding major features, changing architecture, new tutorials
   - Audience: New users, potential contributors, GitHub visitors

2. **SETUP_TRACKER.md** (Root) - Current implementation status, what's working NOW
   - Update when: Features complete, infrastructure changes, configuration updates
   - Format: Status tables (✅ Done, 🚧 In Progress, ❌ Not Started)

3. **docs/ROADMAP.md** - Future plans, upcoming features, priorities
   - Update when: Planning new features, changing priorities, completing roadmap items
   - Remove items once complete (move to SETUP_TRACKER)

4. **tutorials/** - Learning path for understanding the codebase
   - Update when: Code patterns change, new features need explanation
   - Keep examples synchronized with actual code

**After ANY significant code change, ask yourself: "Do the docs need updating?"**

---

## Project Overview

DevChat is a RAG-powered research workbench for academic literature. It uses:
- **Frontend**: Next.js 15, TypeScript, Tailwind CSS, shadcn/ui
- **Backend**: FastAPI, Python 3.12, Pydantic v2
- **Database**: Supabase PostgreSQL with RLS
- **Vectors**: Qdrant Cloud (hybrid search)
- **PDF Processing**: Modal (MinerU GPU parsing)

## Code Style

### Python
- Use type hints for all function signatures
- Use Pydantic models for data validation
- Prefer `async/await` for I/O operations
- Use `loguru` for logging, not `print()`
- Follow PEP 8, max line length 100 chars
- Prefer dictionary dispatch over long if-elif chains when switching on a single value



### TypeScript/React
- Use functional components with hooks
- Prefer `interface` over `type` for object shapes
- Use shadcn/ui components when available
- Handle loading/error states explicitly
- Use `fetch` with proper error handling

## File Structure

```
src/                  # Python libraries
├── agents/           # LLM agents (DevChatAgent)
├── generation/       # Synthesis (ClaimLedgerSynthesizer)
├── ingestion/        # Chunking, classification
├── retrieval/        # Hybrid search, reranking
└── config/           # Study designs, costs

api/                  # FastAPI endpoints
└── routes/           # Organized by feature

frontend/src/         # Next.js app
├── components/       # React components
├── lib/              # Utilities, API client
└── app/              # App router pages

infrastructure/       # Modal pipeline
└── modal_lib/        # 8 modular components
```

## Key Patterns

### RAG Flow
1. Query → Hybrid search (dense + sparse)
2. Rerank top results with Cohere
3. Extract claims with ClaimLedger
4. Verify with MiniCheck NLI
5. Return response with inline citations

### Database
- All tables use RLS with `user_id` column
- Use Supabase client for auth-aware queries
- Migrations in `scripts/migrations/`

### Error Handling
```python
# Python - use structured responses
from pydantic import BaseModel

class APIResponse(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
```

```typescript
// TypeScript - handle API errors
try {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
} catch (e) {
  console.error('API Error:', e);
  throw e;
}
```

## Common Tasks

### Adding a new API endpoint
1. Create route in `api/routes/`
2. Add Pydantic schemas in `api/schemas/`
3. Register in `api/server.py`

### Adding a new frontend component
1. Create in `frontend/src/components/`
2. Use shadcn/ui primitives
3. Handle loading/error states

### Updating Modal pipeline
1. Edit modules in `infrastructure/modal_lib/`
2. Test locally with `modal run`
3. Deploy with `modal deploy`

## Don't Do

- Don't use `print()` for logging
- Don't hardcode API keys
- Don't skip type hints
- Don't create files without using existing patterns
- Don't modify migrations after they're applied

## Testing

- Run Python tests: `pytest tests/`
- Run frontend: `cd frontend && npm run dev`
- Check linting: `ruff check .` / `npm run lint`
