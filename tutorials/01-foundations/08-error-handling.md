# Post 8: Error Handling & Logging

**Part 8 of 50** | ⏱️ 45 minutes | [← Previous](07-environment-setup.md) | [Next: Testing Basics →](09-testing-basics.md)

---

## 🎯 What You'll Learn

- Python exception handling best practices
- Structured logging with loguru
- Error responses in FastAPI
- Frontend error handling patterns
- Observability with Langfuse

---

## 📖 Why Error Handling Matters

### The Silent Failure Scenario

Imagine a user uploads a PDF to DevChat:

```python
# ❌ NO ERROR HANDLING
def process_pdf(pdf_url: str):
    pdf_data = download_pdf(pdf_url)      # Could fail: Network error
    text = parse_pdf(pdf_data)            # Could fail: Corrupt PDF
    chunks = chunk_text(text)             # Could fail: Empty text
    embeddings = create_embeddings(chunks) # Could fail: OpenAI rate limit
    save_to_db(embeddings)                # Could fail: Database down
    return "Success!"

# User sees: "Success!"
# Reality: Failed at step 2, nothing was saved
# User thinks it worked, tries to search, finds nothing
# User: "This app is broken!" 😠
```

**The cascade of confusion:**
1. User uploads PDF
2. Something fails silently
3. User sees "Success" message
4. User tries to search the document
5. Nothing found
6. User wastes hours debugging
7. You have no idea what went wrong

### Proper Error Handling

```python
# ✅ WITH ERROR HANDLING
def process_pdf(pdf_url: str):
    try:
        # Step 1: Download
        logger.info(f"Downloading PDF from {pdf_url}")
        pdf_data = download_pdf(pdf_url)
        
        # Step 2: Parse
        logger.info("Parsing PDF to text")
        text = parse_pdf(pdf_data)
        if not text or len(text) < 100:
            raise ValueError("PDF appears to be empty or unreadable")
        
        # Step 3: Chunk
        logger.info(f"Chunking {len(text)} characters")
        chunks = chunk_text(text)
        
        # Step 4: Embed
        logger.info(f"Creating embeddings for {len(chunks)} chunks")
        embeddings = create_embeddings(chunks)
        
        # Step 5: Save
        logger.info("Saving to database")
        save_to_db(embeddings)
        
        logger.info("✅ PDF processing complete")
        return "Success!"
    
    except requests.RequestException as e:
        # Network problem downloading PDF
        logger.error(f"Failed to download PDF: {e}")
        raise ProcessingError(
            "Could not download PDF. Please check the URL."
        ) from e
    
    except PDFParseError as e:
        # PDF is corrupt or encrypted
        logger.error(f"Failed to parse PDF: {e}")
        raise ProcessingError(
            "PDF file appears to be corrupted or password-protected."
        ) from e
    
    except openai.RateLimitError as e:
        # Hit OpenAI rate limit
        logger.warning(f"OpenAI rate limit hit: {e}")
        raise ProcessingError(
            "Too many requests. Please try again in a few minutes."
        ) from e
    
    except Exception as e:
        # Something unexpected
        logger.exception("Unexpected error during PDF processing")
        raise ProcessingError(
            "An unexpected error occurred. Our team has been notified."
        ) from e

# Now when it fails:
# - User gets helpful message ("PDF appears corrupted")
# - You see detailed logs (where exactly it failed)
# - System remains stable (error doesn't crash other requests)
```

### The Three Audiences for Errors

**1. The User (Frontend)**
```python
raise ProcessingError("PDF file appears to be corrupted")
# User sees: Friendly message they can act on
```

**2. The Developer (Logs)**
```python
logger.error(f"Failed to parse PDF: {pdf_url}", extra={"user_id": user_id})
# You see: Exactly what failed and for whom
```

**3. The System (Monitoring)**
```python
sentry.capture_exception(e)  # Sent to error tracking
# Alert: "PDF processing failing for 10 users in last hour"
```

---

## 🐍 Python Exception Handling

### Custom Exceptions

```python
# src/exceptions.py

class DevChatError(Exception):
    """Base exception for all DevChat errors."""
    pass

class DocumentError(DevChatError):
    """Document-related errors."""
    pass

class DocumentNotFoundError(DocumentError):
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        super().__init__(f"Document {doc_id} not found")

class DocumentProcessingError(DocumentError):
    def __init__(self, doc_id: str, reason: str):
        self.doc_id = doc_id
        self.reason = reason
        super().__init__(f"Failed to process {doc_id}: {reason}")

class RetrievalError(DevChatError):
    """Search/retrieval errors."""
    pass

class LLMError(DevChatError):
    """LLM API errors."""
    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"{provider} error: {message}")
```

### Error Handling Patterns

```python
# Pattern 1: Try-except with logging
from loguru import logger

def fetch_metadata(doi: str) -> dict:
    try:
        response = requests.get(f"https://api.crossref.org/works/{doi}")
        response.raise_for_status()
        return response.json()
    
    except requests.HTTPError as e:
        logger.error(f"HTTP error fetching {doi}: {e}")
        raise MetadataFetchError(doi) from e
    
    except requests.Timeout:
        logger.warning(f"Timeout fetching {doi}, retrying...")
        # Retry logic here
        raise
    
    except Exception as e:
        logger.exception(f"Unexpected error fetching {doi}")
        raise

# Pattern 2: Context manager for cleanup
from contextlib import contextmanager

@contextmanager
def processing_lock(doc_id: str):
    """Ensure document lock is released even if error occurs."""
    try:
        acquire_lock(doc_id)
        yield
    finally:
        release_lock(doc_id)

# Usage
with processing_lock(doc_id):
    process_document(doc_id)  # Lock always released
```

---

## 📝 Structured Logging with loguru

### Setup

```python
# src/utils/logging.py
from loguru import logger
import sys

def setup_logging(level: str = "INFO"):
    """Configure loguru logging."""
    
    # Remove default handler
    logger.remove()
    
    # Console output with colors
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
    )
    
    # File output (production)
    logger.add(
        "logs/devchat_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )
    
    return logger
```

### Logging Patterns

```python
from loguru import logger

# Different log levels
logger.debug("Detailed debug info")
logger.info("General information")
logger.warning("Something unexpected but handled")
logger.error("Error occurred but app continues")
logger.critical("Critical error, app may crash")

# Structured data
logger.info(
    "Document processed",
    extra={
        "doc_id": doc_id,
        "duration_ms": 1234,
        "status": "success"
    }
)

# Exception logging
try:
    risky_operation()
except Exception as e:
    logger.exception("Operation failed")  # Includes traceback
    # or
    logger.error(f"Operation failed: {e}")  # Just error message
```

### DevChat Logging Example

```python
from loguru import logger
from functools import wraps
import time

def log_execution_time(func):
    """Decorator to log function execution time."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = (time.time() - start) * 1000
            
            logger.info(
                f"{func.__name__} completed",
                extra={
                    "function": func.__name__,
                    "duration_ms": round(duration, 2),
                    "status": "success"
                }
            )
            return result
        
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(
                f"{func.__name__} failed",
                extra={
                    "function": func.__name__,
                    "duration_ms": round(duration, 2),
                    "status": "error",
                    "error": str(e)
                }
            )
            raise
    
    return wrapper

# Usage
@log_execution_time
async def search_documents(query: str):
    # Implementation...
    pass
```

---

## 🚀 FastAPI Error Handling

### Exception Handlers

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from src.exceptions import DocumentNotFoundError, LLMError

app = FastAPI()

@app.exception_handler(DocumentNotFoundError)
async def document_not_found_handler(request: Request, exc: DocumentNotFoundError):
    """Handle document not found errors."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "document_not_found",
            "message": str(exc),
            "doc_id": exc.doc_id
        }
    )

@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    """Handle LLM API errors."""
    logger.error(f"LLM error: {exc}")
    
    return JSONResponse(
        status_code=503,
        content={
            "error": "llm_unavailable",
            "message": f"LLM service temporarily unavailable",
            "provider": exc.provider
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unexpected errors."""
    logger.exception("Unhandled exception")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred"
        }
    )
```

### Error Response Models

```python
from pydantic import BaseModel
from typing import Optional

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    details: Optional[dict] = None

@app.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Chat endpoint with documented errors.
    
    Raises:
        404: Project not found
        429: Rate limit exceeded
        503: LLM service unavailable
    """
    try:
        return await process_chat(request)
    
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error="project_not_found",
                message=str(e),
                details={"project_id": e.project_id}
            ).dict()
        )
```

---

## 💻 Frontend Error Handling

### API Client with Error Handling

```typescript
// lib/api-client.ts

class APIError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public errorCode: string,
    public details?: any
  ) {
    super(message)
    this.name = 'APIError'
  }
}

async function apiRequest<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })
    
    if (!res.ok) {
      const error = await res.json()
      throw new APIError(
        error.message || 'Request failed',
        res.status,
        error.error || 'unknown_error',
        error.details
      )
    }
    
    return res.json()
  
  } catch (error) {
    if (error instanceof APIError) {
      throw error
    }
    
    // Network error
    throw new APIError(
      'Network error occurred',
      0,
      'network_error'
    )
  }
}
```

### React Error Boundaries

```typescript
// components/ErrorBoundary.tsx
'use client'

import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }
  
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }
  
  componentDidCatch(error: Error, errorInfo: any) {
    console.error('Error caught by boundary:', error, errorInfo)
    // Send to error tracking service
  }
  
  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="p-8 text-center">
          <h2 className="text-2xl font-bold mb-4">Something went wrong</h2>
          <p className="text-gray-600 mb-4">
            {this.state.error?.message}
          </p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="px-4 py-2 bg-blue-500 text-white rounded"
          >
            Try again
          </button>
        </div>
      )
    }
    
    return this.props.children
  }
}

// Usage
export default function Page() {
  return (
    <ErrorBoundary>
      <ChatInterface />
    </ErrorBoundary>
  )
}
```

### User-Friendly Error Messages

```typescript
// lib/error-messages.ts

export function getErrorMessage(error: APIError): string {
  const messages: Record<string, string> = {
    document_not_found: 'Document not found. It may have been deleted.',
    project_not_found: 'Project not found. Please check the URL.',
    rate_limit_exceeded: 'Too many requests. Please try again in a few minutes.',
    llm_unavailable: 'AI service temporarily unavailable. Please try again.',
    insufficient_credits: 'Insufficient credits. Please upgrade your plan.',
    invalid_file_type: 'Invalid file type. Please upload a PDF.',
    file_too_large: 'File too large. Maximum size is 10MB.',
  }
  
  return messages[error.errorCode] || 'An unexpected error occurred. Please try again.'
}

// Usage in component
try {
  await uploadDocument(file)
} catch (error) {
  if (error instanceof APIError) {
    toast.error(getErrorMessage(error))
  } else {
    toast.error('Network error. Please check your connection.')
  }
}
```

---

## 📊 Observability with Langfuse

### Setup Langfuse

```python
# src/utils/langfuse_client.py
from langfuse import Langfuse
from src.config.settings import settings

langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host
)

# Decorator for tracing
from functools import wraps

def trace_function(name: str = None):
    """Trace function execution in Langfuse."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            trace_name = name or func.__name__
            
            trace = langfuse.trace(name=trace_name)
            
            try:
                result = await func(*args, **kwargs)
                trace.update(status="success")
                return result
            
            except Exception as e:
                trace.update(
                    status="error",
                    metadata={"error": str(e)}
                )
                raise
        
        return wrapper
    return decorator
```

### Trace RAG Pipeline

```python
from src.utils.langfuse_client import langfuse, trace_function

@trace_function("rag_query")
async def process_query(query: str, project_id: str):
    """Process RAG query with full tracing."""
    
    # Create trace
    trace = langfuse.trace(
        name="rag_query",
        input={"query": query, "project_id": project_id}
    )
    
    # Step 1: Retrieval
    retrieval_span = trace.span(name="retrieval")
    docs = await retriever.search(query, limit=10)
    retrieval_span.end(output={"doc_count": len(docs)})
    
    # Step 2: Reranking
    rerank_span = trace.span(name="reranking")
    reranked = await reranker.rerank(query, docs, limit=5)
    rerank_span.end(output={"doc_count": len(reranked)})
    
    # Step 3: Generation
    generation = trace.generation(
        name="llm_generation",
        model="gpt-4o",
        input={"query": query, "context": reranked}
    )
    
    response = await llm.generate(query, reranked)
    
    generation.end(
        output=response.answer,
        usage={
            "input": response.tokens_input,
            "output": response.tokens_output,
            "total": response.tokens_total
        }
    )
    
    # Complete trace
    trace.update(
        output={"answer": response.answer},
        metadata={"latency_ms": response.latency}
    )
    
    return response
```

---

## ✅ Knowledge Check

1. When should you create custom exceptions?
2. What's the difference between `logger.error()` and `logger.exception()`?
3. How do you return structured errors in FastAPI?
4. What are React Error Boundaries for?
5. Why use observability tools like Langfuse?

<details>
<summary>Answers</summary>

1. For domain-specific errors that need special handling or have extra context
2. `exception()` includes full traceback, `error()` just logs the message
3. Create custom exception handlers that return `JSONResponse` with error details
4. To catch React component errors and show fallback UI instead of blank screen
5. To trace requests through the system, measure performance, and debug issues

</details>

---

**Next:** [Post 9: Testing Basics →](09-testing-basics.md)

Learn how to test Python and TypeScript code effectively.

---

[🏠 Back to Index](../README.md) | [← Previous](07-environment-setup.md) | [Next: Testing Basics →](09-testing-basics.md)
