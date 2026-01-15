# Post 2: Python Fundamentals for DevChat

**Part 2 of 50** | ⏱️ 45 minutes | [← Previous](01-project-overview.md) | [Next: FastAPI Basics →](03-fastapi-basics.md)

---

## 🎯 What You'll Learn

- Type hints and why they matter
- Pydantic models for data validation
- Async/await for concurrent operations
- Python imports and project structure
- Common patterns in the DevChat codebase

---

## 📖 Type Hints

### Understanding the Problem

Python is **dynamically typed**, meaning you don't have to declare variable types:

```python
x = 5        # x is an integer
x = "hello"  # Now x is a string - Python doesn't care!
```

This flexibility is great for quick scripts, but causes problems in large projects:

1. **You can't tell what a function expects** just by looking at it
2. **Bugs hide until runtime** - no warnings until the code actually runs
3. **IDEs can't help you** - no autocomplete or warnings

Think of it like building with unlabeled boxes - you don't know what goes in each box until you try.

### Type Hints: Labels for Your Code

Type hints add **labels** to your code without changing how it runs:

```python
# Without type hints (mystery box)
def process_document(doc, user):
    # What is doc? A dictionary? An object? A string?
    # What is user? Their name? Their ID? A user object?
    return doc.title + user.name  # Will this even work?

# With type hints (labeled boxes)
def process_document(doc: dict, user: str) -> str:
    # Clear: doc is a dictionary, user is a string
    # Returns: a string
    return doc["title"] + user
```

**What changes?** Actually, nothing at runtime! Python still ignores the types. But:
- Your IDE shows errors **before you run the code**
- Other developers know exactly what to pass in
- You catch bugs while typing, not in production

### Why Type Hints?

1. **Catch bugs early**: IDEs warn you about type errors
2. **Better autocomplete**: Your editor knows what's available
3. **Self-documenting**: Code explains itself
4. **Refactoring safety**: Change types confidently

### DevChat Example

From `src/agents/devchat_agent.py`:

```python
from typing import List, Dict, Optional

async def search_documents(
    query: str,
    user_id: str,
    project_id: str,
    limit: int = 10
) -> List[Dict[str, any]]:
    """
    Search for relevant documents.
    
    Args:
        query: User's search query
        user_id: ID of the user making the request
        project_id: RAG project to search within
        limit: Maximum number of results (default 10)
        
    Returns:
        List of document dictionaries with metadata
    """
    # Implementation...
```

**Key points:**
- `query`, `user_id`, `project_id` are strings
- `limit` is an int with default value
- Returns a list of dictionaries
- Docstring explains parameters

---

## 🛡️ Pydantic Models

### The Manual Validation Problem

Imagine you're building an API that accepts user data. Without Pydantic:

```python
def create_user(data: dict):
    # You have to check EVERYTHING manually
    if "id" not in data:
        raise ValueError("Missing id")
    if "email" not in data:
        raise ValueError("Missing email")
    if "@" not in data["email"]:
        raise ValueError("Invalid email")
    if "age" not in data:
        raise ValueError("Missing age")
    if not isinstance(data["age"], int):
        raise ValueError("Age must be integer")
    if data["age"] < 0 or data["age"] > 150:
        raise ValueError("Invalid age")
    # ... and on and on ...
    
    return create_user_in_db(data)
```

**Problems:**
- 20+ lines of validation code
- Easy to forget checks
- Hard to maintain
- Repetitive across endpoints

### Pydantic: Automatic Validation

Pydantic does all this validation automatically:

```python
from pydantic import BaseModel, Field, EmailStr

class User(BaseModel):
    id: str
    email: EmailStr  # Automatically validates email format!
    name: str
    age: int = Field(gt=0, lt=150)  # Must be between 0 and 150

# This ONE line does all the validation:
user = User(id="123", email="user@example.com", name="Alice", age=30)
# ✅ Works!

# Invalid data?
user = User(id="123", email="invalid", name="Bob", age=200)
# ❌ Raises ValidationError with clear message:
# "value is not a valid email address"
# "ensure this value is less than 150"
```

**What just happened?**

1. Pydantic checked all fields exist
2. Validated email format
3. Verified age is an integer
4. Ensured age is in valid range
5. Gave helpful error messages

All without a single `if` statement!

### DevChat Example

From `api/schemas/chat.py`:

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class ChatRequest(BaseModel):
    """Request schema for chat endpoint."""
    query: str = Field(..., min_length=1, max_length=5000)
    project_id: str
    stream: bool = False
    model: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the effects of cash transfers?",
                "project_id": "proj_123",
                "stream": True
            }
        }

class Citation(BaseModel):
    """Citation extracted from response."""
    text: str
    doc_id: str
    page: int
    score: float = Field(ge=0.0, le=1.0)

class ChatResponse(BaseModel):
    """Response schema for chat endpoint."""
    answer: str
    citations: List[Citation]
    tokens_used: int
    latency_ms: int
```

**Why Pydantic?**
- ✅ Automatic validation
- ✅ Type coercion (converts "123" → 123)
- ✅ Clear error messages
- ✅ JSON serialization built-in
- ✅ Great with FastAPI

---

## ⚡ Async/Await

### The Waiting Problem

Imagine you're making breakfast:

**Synchronous (Blocking) Approach:**
```
1. Put bread in toaster → Stand and wait 2 minutes
2. Boil water → Stand and wait 3 minutes  
3. Make coffee → Stand and wait 1 minute
Total time: 6 minutes (lots of waiting!)
```

**Asynchronous (Non-blocking) Approach:**
```
1. Put bread in toaster (start 2-min timer)
2. Start boiling water (start 3-min timer)
3. Prep coffee while waiting
4. Everything done in ~3 minutes!
```

This is exactly what async/await does with code.

### Sync: One Thing at a Time

```python
import requests
import time

def fetch_metadata(doi: str) -> dict:
    # Make API call - your program STOPS and WAITS
    response = requests.get(f"https://api.crossref.org/works/{doi}")
    return response.json()  # Takes ~200ms

start = time.time()
result1 = fetch_metadata(doi1)  # Wait 200ms
result2 = fetch_metadata(doi2)  # Wait 200ms
result3 = fetch_metadata(doi3)  # Wait 200ms
print(f"Took {time.time() - start:.2f}s")  # ~600ms
```

**Problem:** Your program is **frozen** while waiting for the network. It can't do anything else!

### Async: Do Multiple Things While Waiting

```python
import httpx
import asyncio
import time

async def fetch_metadata(doi: str) -> dict:
    async with httpx.AsyncClient() as client:
        # "await" means "I'll wait, but others can run"
        response = await client.get(f"https://api.crossref.org/works/{doi}")
        return response.json()

start = time.time()
# Run all 3 at the same time!
results = await asyncio.gather(
    fetch_metadata(doi1),
    fetch_metadata(doi2),
    fetch_metadata(doi3)
)
print(f"Took {time.time() - start:.2f}s")  # ~200ms (3x faster!)
```

**Magic:** While waiting for API #1, Python starts API #2 and #3. All three run **concurrently**.

### Key Concepts

**`async def`** = "This function can pause and let others run"

**`await`** = "Pause here, but let other async functions run while I wait"

**Why this matters for DevChat:**
- Searching 10 documents? Do it in parallel!
- Calling OpenAI + Cohere + Qdrant? Run simultaneously!
- Serving 100 users? Handle all their requests at once!

### Running Multiple Requests

```python
import asyncio

# Sequential (slow) - takes 3 seconds
async def get_all_sync():
    result1 = await fetch_metadata(doi1)  # 1 second
    result2 = await fetch_metadata(doi2)  # 1 second
    result3 = await fetch_metadata(doi3)  # 1 second
    return [result1, result2, result3]

# Concurrent (fast) - takes 1 second
async def get_all_concurrent():
    results = await asyncio.gather(
        fetch_metadata(doi1),
        fetch_metadata(doi2),
        fetch_metadata(doi3)
    )
    return results  # All run at once!
```

### DevChat Example

From `src/retrieval/hybrid_retriever.py`:

```python
async def search(
    self,
    query: str,
    limit: int = 10
) -> List[SearchResult]:
    """Hybrid search: dense + sparse in parallel."""
    
    # Run dense and sparse search concurrently
    dense_task = self._dense_search(query, limit=50)
    sparse_task = self._sparse_search(query, limit=50)
    
    # Wait for both to complete
    dense_results, sparse_results = await asyncio.gather(
        dense_task,
        sparse_task
    )
    
    # Merge and rerank
    merged = self._merge_results(dense_results, sparse_results)
    reranked = await self._rerank(query, merged, limit=limit)
    
    return reranked
```

**When to use async:**
- ✅ Database queries
- ✅ API calls (OpenAI, Cohere, etc.)
- ✅ File I/O
- ✅ Network requests
- ❌ CPU-intensive work (use threads/processes instead)

---

## 📦 Project Structure & Imports

### DevChat Structure

```
src/
├── agents/
│   └── devchat_agent.py          # Main RAG orchestrator
├── retrieval/
│   ├── hybrid_retriever.py       # Search implementation
│   └── reranker.py               # Cohere reranking
├── generation/
│   └── claim_ledger.py           # Citation synthesis
├── ingestion/
│   ├── chunking.py               # Text chunking
│   └── study_design_classifier.py
├── config/
│   ├── study_designs.py          # Study design taxonomy
│   └── costs.py                  # Cost tracking
└── utils/
    ├── langfuse_client.py        # Observability
    └── cache.py                  # Response caching
```

### Import Patterns

```python
# Absolute imports (preferred)
from src.retrieval.hybrid_retriever import HybridRetriever
from src.generation.claim_ledger import ClaimLedgerSynthesizer
from src.config.study_designs import STUDY_DESIGNS

# Relative imports (for internal module imports)
from .reranker import CohereReranker
from ..utils.cache import get_cached_response

# Type-only imports (don't import at runtime)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.agents.devchat_agent import DevChatAgent
```

---

## 🎨 Common Patterns

### 1. Dependency Injection

```python
# BAD: Hardcoded dependencies
class ChatService:
    def __init__(self):
        self.retriever = HybridRetriever()  # Tightly coupled
        self.llm = OpenAIClient()

# GOOD: Inject dependencies
class ChatService:
    def __init__(
        self,
        retriever: HybridRetriever,
        llm: LLMClient
    ):
        self.retriever = retriever
        self.llm = llm

# Easy to test with mocks
service = ChatService(
    retriever=MockRetriever(),
    llm=MockLLM()
)
```

### 2. Context Managers

```python
# Automatic cleanup with 'with'
async with httpx.AsyncClient() as client:
    response = await client.get(url)
    # Client automatically closes
```

### 3. Dictionary Dispatch

```python
# BAD: Long if-elif chain
if action == "create":
    return create_project()
elif action == "update":
    return update_project()
elif action == "delete":
    return delete_project()

# GOOD: Dictionary dispatch
handlers = {
    "create": create_project,
    "update": update_project,
    "delete": delete_project,
}
return handlers[action]()
```

### 4. Optional Values

```python
from typing import Optional

# May return None
def find_user(user_id: str) -> Optional[User]:
    user = db.query(User).filter_by(id=user_id).first()
    return user  # Could be None

# Handle None safely
user = find_user("123")
if user is not None:
    print(user.name)
```

---

## 💡 Real DevChat Example

Let's trace through `src/agents/devchat_agent.py`:

```python
from typing import List, Dict, Optional
from pydantic import BaseModel
import asyncio

from src.retrieval.hybrid_retriever import HybridRetriever
from src.generation.claim_ledger import ClaimLedgerSynthesizer
from src.utils.langfuse_client import langfuse

class SearchResult(BaseModel):
    """Pydantic model for search results."""
    content: str
    doc_id: str
    score: float
    metadata: Dict[str, any]

class DevChatAgent:
    """Main RAG agent orchestrator."""
    
    def __init__(
        self,
        retriever: HybridRetriever,
        synthesizer: ClaimLedgerSynthesizer,
    ):
        """Dependency injection."""
        self.retriever = retriever
        self.synthesizer = synthesizer
    
    @langfuse.observe()  # Decorator for tracing
    async def query(
        self,
        query: str,
        project_id: str,
        user_id: str,
    ) -> Dict[str, any]:
        """
        Process a user query end-to-end.
        
        Args:
            query: User's natural language question
            project_id: RAG project ID
            user_id: ID of requesting user
            
        Returns:
            Dict with answer, citations, and metadata
        """
        # Step 1: Retrieve relevant documents
        docs = await self.retriever.search(
            query=query,
            project_id=project_id,
            limit=10
        )
        
        # Step 2: Generate response with citations
        response = await self.synthesizer.synthesize(
            query=query,
            documents=docs
        )
        
        return {
            "answer": response.answer,
            "citations": [c.dict() for c in response.citations],
            "tokens": response.tokens_used,
        }
```

**Key Python features used:**
- ✅ Type hints on all parameters and return values
- ✅ Pydantic `BaseModel` for data validation
- ✅ `async/await` for non-blocking I/O
- ✅ Dependency injection in `__init__`
- ✅ Decorator for observability
- ✅ Docstrings explaining parameters

---

## 🧪 Try It Yourself

### Exercise 1: Type Hints

Add type hints to this function:

```python
def calculate_cost(tokens, model):
    if model == "gpt-4o":
        return tokens * 0.00001
    return tokens * 0.000001
```

<details>
<summary>Solution</summary>

```python
def calculate_cost(tokens: int, model: str) -> float:
    if model == "gpt-4o":
        return tokens * 0.00001
    return tokens * 0.000001
```

</details>

### Exercise 2: Pydantic Model

Create a Pydantic model for a document:

```python
# Requirements:
# - id: string (required)
# - title: string (required, max 500 chars)
# - authors: list of strings (optional)
# - year: integer (between 1900-2100)
```

<details>
<summary>Solution</summary>

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class Document(BaseModel):
    id: str
    title: str = Field(max_length=500)
    authors: Optional[List[str]] = None
    year: int = Field(ge=1900, le=2100)
```

</details>

### Exercise 3: Async

Convert this to async:

```python
def fetch_all_metadata(dois):
    results = []
    for doi in dois:
        result = requests.get(f"https://api.crossref.org/works/{doi}")
        results.append(result.json())
    return results
```

<details>
<summary>Solution</summary>

```python
import asyncio
import httpx

async def fetch_all_metadata(dois):
    async with httpx.AsyncClient() as client:
        tasks = [
            client.get(f"https://api.crossref.org/works/{doi}")
            for doi in dois
        ]
        responses = await asyncio.gather(*tasks)
        return [r.json() for r in responses]
```

</details>

---

## 📚 Additional Resources

- [Python Type Hints](https://docs.python.org/3/library/typing.html) - Official docs
- [Pydantic Documentation](https://docs.pydantic.dev/) - Data validation
- [Real Python: Async IO](https://realpython.com/async-io-python/) - Async guide
- [Python Project Structure](https://docs.python-guide.org/writing/structure/) - Best practices

---

## ✅ Knowledge Check

1. What's the difference between `str` and `Optional[str]`?
2. Why does DevChat use Pydantic models?
3. When should you use `async/await`?
4. How do you run multiple async functions concurrently?
5. What's the benefit of dependency injection?

<details>
<summary>Answers</summary>

1. `Optional[str]` means the value can be `str` or `None`
2. For automatic data validation and type coercion
3. For I/O operations (API calls, database queries, file operations)
4. Use `asyncio.gather()` to run them in parallel
5. Makes code more testable and flexible by decoupling components

</details>

---

**Next:** [Post 3: FastAPI Basics →](03-fastapi-basics.md)

Learn how to build REST APIs with FastAPI, the framework powering DevChat's backend.

---

[🏠 Back to Index](../README.md) | [← Previous](01-project-overview.md) | [Next: FastAPI Basics →](03-fastapi-basics.md)
