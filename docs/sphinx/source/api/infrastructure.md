# Infrastructure (Modal)

The `infrastructure/` package contains the Modal deployment for GPU-accelerated PDF processing.

## Entry Point

```{eval-rst}
.. automodule:: infrastructure.modal_mineru
   :members:
   :undoc-members:
   :show-inheritance:
```

## Modal Library Modules

### Config

```{eval-rst}
.. automodule:: infrastructure.modal_lib.config
   :members:
   :undoc-members:
   :show-inheritance:
```

### Processing

```{eval-rst}
.. automodule:: infrastructure.modal_lib.processing
   :members:
   :undoc-members:
   :show-inheritance:
```

### Extraction

```{eval-rst}
.. automodule:: infrastructure.modal_lib.extraction
   :members:
   :undoc-members:
   :show-inheritance:
```

### Embedding

```{eval-rst}
.. automodule:: infrastructure.modal_lib.embedding
   :members:
   :undoc-members:
   :show-inheritance:
```

### Metadata

```{eval-rst}
.. automodule:: infrastructure.modal_lib.metadata
   :members:
   :undoc-members:
   :show-inheritance:
```

### Orchestration

```{eval-rst}
.. automodule:: infrastructure.modal_lib.orchestration
   :members:
   :undoc-members:
   :show-inheritance:
```

### Utils

```{eval-rst}
.. automodule:: infrastructure.modal_lib.utils
   :members:
   :undoc-members:
   :show-inheritance:
```

## Deployment

```bash
# Test locally
modal run infrastructure/modal_mineru.py --help

# Deploy to Modal
modal deploy infrastructure/modal_mineru.py

# Process a document
modal run infrastructure/modal_mineru.py::process_document \
  --project-id "your-project-id" \
  --pdf-key "path/to/file.pdf"
```

## Pipeline Stages

1. **Download** - Fetch PDF from Cloudflare R2
2. **Parse** - MineRU extracts text, tables, formulas
3. **Chunk** - Split into overlapping chunks
4. **Contextualize** - Claude adds context to each chunk
5. **Embed** - Cohere generates dense + sparse vectors
6. **Index** - Store in Qdrant with metadata
7. **Update** - Mark document as processed in Supabase
