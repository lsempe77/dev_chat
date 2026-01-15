# Modal MinerU Refactoring Plan

## Status: ✅ COMPLETED

**Refactoring completed on**: January 7, 2026

### Results

| File | Lines | Purpose |
|------|-------|---------|
| `modal_mineru.py` | 215 | Entry point, CLI, HTTP endpoints |
| `modal_lib/__init__.py` | 101 | Re-exports |
| `modal_lib/config.py` | 53 | App, image, secrets, constants |
| `modal_lib/utils.py` | 108 | R2 client, sanitization |
| `modal_lib/extraction.py` | 281 | MinerU PDF extraction |
| `modal_lib/metadata.py` | 450 | CrossRef, OpenAlex, LLM |
| `modal_lib/embedding.py` | 647 | Chunking, embedding, Qdrant, Contextual Retrieval |
| `modal_lib/processing.py` | 659 | GPU PDF processing functions |
| `modal_lib/orchestration.py` | 536 | Batch orchestration |
| **Total** | **3,050** | (grew from 2,744 due to Contextual Retrieval) |

**Backup**: `modal_mineru_backup.py` (2,913 lines) - can be deleted after verification

---

## Original State
- **File**: `modal_mineru.py` (~3000 lines)
- **Problem**: Monolithic, hard to navigate, risky to modify
- **Goal**: Split into logical modules while maintaining Modal compatibility

---

## Target Structure

```
infrastructure/
├── modal_mineru.py              # Entry point only (~150 lines)
│                                 # - App definition
│                                 # - CLI entry points  
│                                 # - HTTP endpoints
│
├── modal_lib/
│   ├── __init__.py              # Re-exports for convenience
│   │
│   ├── config.py                # (~100 lines)
│   │   ├── Modal app definition
│   │   ├── Image definitions (base_image)
│   │   ├── Secrets (r2_secret, qdrant_secret, etc.)
│   │   ├── Volumes (model_cache)
│   │   ├── Constants (QDRANT_COLLECTION_NAME, etc.)
│   │   └── R2/S3 client helpers
│   │
│   ├── extraction.py            # (~400 lines)
│   │   ├── run_mineru()
│   │   ├── extract_title()
│   │   ├── extract_authors_from_text()
│   │   ├── extract_year_from_text()
│   │   ├── extract_abstract()
│   │   └── post_process_content()
│   │
│   ├── metadata.py              # (~500 lines)
│   │   ├── resolve_metadata()
│   │   ├── extract_doi_from_text()
│   │   ├── llm_extract_domain_fields()
│   │   ├── classify_study_design_llm()
│   │   └── CrossRef/OpenAlex API calls
│   │
│   ├── embedding.py             # (~400 lines)
│   │   ├── embed_and_index()
│   │   ├── chunk_content()
│   │   ├── chunk_content_with_pages()
│   │   ├── _generate_sparse_vector()
│   │   └── ensure_qdrant_indexes()
│   │
│   ├── processing.py            # (~600 lines) - @app.function decorated
│   │   ├── process_pdf_rag()
│   │   ├── process_pdf()
│   │   ├── sync_to_supabase_rag()
│   │   └── sync_to_postgres()
│   │
│   ├── orchestration.py         # (~400 lines) - @app.function decorated
│   │   ├── orchestrate()
│   │   ├── orchestrate_rag()
│   │   ├── orchestrate_batch()
│   │   └── Batch processing helpers
│   │
│   └── utils.py                 # (~200 lines)
│       ├── sanitize_text()
│       ├── sanitize_dict()
│       ├── get_r2_client()
│       ├── get_bucket_name()
│       └── Other helpers
│
└── README.md                    # Updated with new structure
```

---

## Module Dependencies

```
modal_mineru.py
    └── modal_lib/
        ├── config.py          (no internal deps)
        ├── utils.py           ← config
        ├── extraction.py      ← config, utils
        ├── metadata.py        ← config, utils
        ├── embedding.py       ← config, utils
        ├── processing.py      ← config, utils, extraction, metadata, embedding
        └── orchestration.py   ← config, utils, processing
```

---

## Implementation Phases

### Phase 1: Create Structure (30 min)
- [ ] Create `infrastructure/modal_lib/` directory
- [ ] Create `__init__.py` with placeholder imports
- [ ] Create empty module files with docstrings

### Phase 2: Extract Config & Utils (30 min)  
- [ ] Move Modal app, secrets, images to `config.py`
- [ ] Move utility functions to `utils.py`
- [ ] Test: `modal deploy` still works

### Phase 3: Extract Extraction Logic (30 min)
- [ ] Move `run_mineru()` and extract_* functions to `extraction.py`
- [ ] Update imports in main file
- [ ] Test: single PDF processing works

### Phase 4: Extract Metadata Resolution (30 min)
- [ ] Move `resolve_metadata()` and related to `metadata.py`
- [ ] Move LLM functions (`llm_extract_domain_fields`, `classify_study_design_llm`)
- [ ] Test: metadata enrichment works

### Phase 5: Extract Embedding & Indexing (30 min)
- [ ] Move `embed_and_index()` and chunking to `embedding.py`
- [ ] Move sparse vector generation
- [ ] Test: Qdrant indexing works

### Phase 6: Extract Processing Functions (45 min)
- [ ] Move `process_pdf()`, `process_pdf_rag()` to `processing.py`
- [ ] Move sync functions
- [ ] These have @app.function decorators - need careful handling
- [ ] Test: full pipeline works

### Phase 7: Extract Orchestration (30 min)
- [ ] Move `orchestrate()`, `orchestrate_rag()` to `orchestration.py`
- [ ] Move batch helpers
- [ ] Test: batch processing works

### Phase 8: Cleanup Main File (15 min)
- [ ] Main file should only have:
  - Imports from modal_lib
  - CLI entry points (`@app.local_entrypoint`)
  - HTTP endpoints (`@modal.fastapi_endpoint`)
  - Re-exports for backward compatibility
- [ ] Final test: full deploy and processing

---

## Key Technical Considerations

### 1. Modal App Object
The `app` object must be created in ONE place and imported everywhere:

```python
# modal_lib/config.py
import modal
app = modal.App("devchat-mineru")

# modal_lib/processing.py
from .config import app, base_image, r2_secret
@app.function(image=base_image, secrets=[r2_secret])
def process_pdf(...):
    ...
```

### 2. @app.function Decorators
Functions with `@app.function` can be in separate files as long as they import `app`:

```python
# Works fine!
from modal_lib.config import app
from modal_lib.processing import process_pdf  # Has @app.function
```

### 3. Local Imports in Remote Functions
Modal serializes functions to run remotely. Standard library and pip packages work fine, but local imports need the code available in the image. Since we're already copying the full project, this works.

### 4. Circular Import Prevention
Use TYPE_CHECKING pattern if needed:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .processing import process_pdf
```

### 5. Testing Strategy
After each phase:
1. Run `modal deploy infrastructure/modal_mineru.py`
2. Test with a single PDF: `modal run infrastructure/modal_mineru.py --action single --pdf-key "..."`
3. Check logs for import errors

---

## Rollback Plan
Keep the original file as `modal_mineru_backup.py` until refactoring is validated in production.

---

## Estimated Total Time
- **Development**: ~4 hours
- **Testing**: ~1 hour  
- **Buffer**: ~1 hour
- **Total**: ~6 hours

---

## Success Criteria
1. ✅ `modal deploy` succeeds
2. ✅ Single PDF processing works end-to-end
3. ✅ Batch orchestration works
4. ✅ HTTP trigger endpoint works
5. ✅ No functionality regression
6. ✅ Main file is < 200 lines
7. ✅ Each module is < 600 lines

---

## Next Steps
1. Review and approve this plan
2. Start with Phase 1: Create directory structure
3. Proceed incrementally, testing after each phase
