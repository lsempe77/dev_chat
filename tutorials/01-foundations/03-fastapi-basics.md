# Post 3: FastAPI Backend Basics

**Part 3 of 50** | ⏱️ 60 minutes | [← Previous](02-python-fundamentals.md) | [Next: Next.js Basics →](04-nextjs-basics.md)

---

## 🎯 What You'll Learn

- FastAPI basics and why it's perfect for AI apps
- Creating API endpoints (routes)
- Request/response validation with Pydantic
- Dependency injection in FastAPI
- Error handling and status codes
- Real examples from DevChat

---

## 📖 What is FastAPI?

### Understanding Web APIs

First, let's understand what we're building. A **web API** is like a waiter in a restaurant:

```
Frontend (Customer)          Backend (Kitchen)
    │                             │
    ├──"I want pasta"────────────▶│ Process request
    │                             │ Cook the food
    │◀──"Here's your pasta"───────┤ Send response
    │                             │
```

The frontend (React/Next.js) sends **requests**, the backend (FastAPI) processes them and sends **responses**.

### Why FastAPI?

You could build APIs with Flask, Django, or Node.js. But FastAPI has unique advantages:

**1. Automatic Validation**

```python
# Flask: You validate manually
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    if not data:  # Check 1
        return {'error': 'No data'}, 400
    if 'query' not in data:  # Check 2
        return {'error': 'Missing query'}, 400
    if not isinstance(data['query'], str):  # Check 3
        return {'error': 'Query must be string'}, 400
    if len(data['query']) < 1:  # Check 4
        return {'error': 'Query too short'}, 400
    # Finally process...
    return process(data['query'])

# FastAPI: Validation is automatic!
@app.post("/api/chat")
async def chat(request: ChatRequest):  # One line = all validation!
    return await process(request.query)
```

**2. Built for Async**

FastAPI was designed from day 1 for `async/await`. Flask and Django added it as an afterthought.

```python
# Natural async code
@app.post("/api/chat")
async def chat(request: ChatRequest):
    # Multiple I/O operations run concurrently
    docs = await search_db(request.query)
    response = await call_llm(docs)
    return response
```

**3. Free Documentation**

FastAPI automatically generates interactive API docs. Visit `http://localhost:8000/docs` and you get:
- List of all endpoints
- Try requests directly in browser
- See request/response schemas
- No extra work needed!

**Why FastAPI for DevChat?**

DevChat makes many I/O calls:
- Search Qdrant (vector database)
- Call OpenAI/Anthropic (LLMs)
- Query Supabase (PostgreSQL)
- Fetch metadata from APIs

All these need to run **concurrently** for good performance. FastAPI + async/await makes this natural.

```python
# Traditional Flask (synchronous)
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json  # No validation!
    if not data or 'query' not in data:
        return {'error': 'Missing query'}, 400
    
    # Blocking I/O
    results = search_database(data['query'])
    response = call_llm(results)
    return {'answer': response}

# FastAPI (async + validated)
@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    # Automatic validation
    results = await search_database(request.query)
    response = await call_llm(results)
    return ChatResponse(answer=response)
```

**Benefits:**
- Type hints = automatic validation
- Async = handle many concurrent requests
- Auto-docs = easy API testing
- Pydantic = clean error messages

---

## 🚀 Basic FastAPI App

### Minimal Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

Run with: `uvicorn main:app --reload`

Visit: <http://localhost:8000/docs> for interactive API docs!

### Path Parameters

```python
@app.get("/users/{user_id}")
async def get_user(user_id: str):
    return {"user_id": user_id}

# Call: GET /users/123
# Returns: {"user_id": "123"}
```

### Query Parameters

```python
@app.get("/search")
async def search(q: str, limit: int = 10):
    return {"query": q, "limit": limit}

# Call: GET /search?q=test&limit=5
# Returns: {"query": "test", "limit": 5}
```

---

## 🛡️ Request Validation with Pydantic

### Define Request Schema

```python
from pydantic import BaseModel, Field
from typing import Optional

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    project_id: str
    stream: bool = False
    model: Optional[str] = None

@app.post("/api/chat")
async def chat(request: ChatRequest):
    # request.query is guaranteed to be 1-5000 chars
    # request.project_id exists
    # request.stream defaults to False
    return {"query": request.query}
```

### Automatic Validation

```python
# Valid request
{
    "query": "What are the findings?",
    "project_id": "proj_123"
}
# ✅ Works

# Invalid request
{
    "query": "",  # Too short!
    "project_id": "proj_123"
}
# ❌ Returns 422 with error: "String should have at least 1 character"
```

---

## 🎯 DevChat API Structure

From `api/server.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import chat, api, admin

app = FastAPI(
    title="DevChat API",
    description="RAG-powered research assistant",
    version="2.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dev-chat-frontend.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(api.router, prefix="/api", tags=["rag"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "2.0.0"}
```

### Chat Route

From `api/routes/chat.py`:

```python
from fastapi import APIRouter, HTTPException, Depends
from api.schemas.chat import ChatRequest, ChatResponse
from src.agents.devchat_agent import DevChatAgent

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    agent: DevChatAgent = Depends(get_agent)
):
    """
    Process a chat query with RAG.
    
    - **query**: User's natural language question
    - **project_id**: RAG project to search within
    - **stream**: Whether to stream response
    """
    try:
        result = await agent.query(
            query=request.query,
            project_id=request.project_id,
            user_id=request.user_id,
        )
        
        return ChatResponse(
            answer=result["answer"],
            citations=result["citations"],
            tokens_used=result["tokens"],
            latency_ms=result["latency"]
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Query failed: {str(e)}"
        )
```

**Key features:**
- `response_model`: Validates response matches schema
- `Depends()`: Dependency injection (explained next)
- `HTTPException`: Proper error handling
- Docstring appears in auto-generated docs

---

## 💉 Dependency Injection

FastAPI's dependency system is powerful for managing shared resources.

### Basic Dependency

```python
from fastapi import Depends

def get_current_user(token: str) -> User:
    """Validate token and return user."""
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

@app.get("/me")
async def read_users_me(user: User = Depends(get_current_user)):
    return user
```

### DevChat Example: Database Connection

From `api/dependencies.py`:

```python
from typing import AsyncGenerator
from supabase import create_client, AsyncClient

async def get_supabase() -> AsyncGenerator[AsyncClient, None]:
    """Get Supabase client as dependency."""
    client = create_client(
        supabase_url=settings.SUPABASE_URL,
        supabase_key=settings.SUPABASE_SERVICE_KEY
    )
    try:
        yield client
    finally:
        await client.close()

@router.get("/projects")
async def list_projects(
    user_id: str,
    db: AsyncClient = Depends(get_supabase)
):
    # db is automatically injected
    projects = await db.table("rag_projects")\\
        .select("*")\\
        .eq("user_id", user_id)\\
        .execute()
    
    return projects.data
```

### Nested Dependencies

```python
def get_db():
    return DatabaseConnection()

def get_user(db = Depends(get_db)):
    return db.get_current_user()

def get_project(user = Depends(get_user), db = Depends(get_db)):
    return db.get_user_projects(user.id)

@app.get("/data")
async def endpoint(project = Depends(get_project)):
    # All dependencies resolved automatically!
    return project
```

---

## ⚠️ Error Handling

### HTTP Status Codes

```python
from fastapi import HTTPException, status

@app.post("/documents")
async def create_document(doc: Document):
    # 400: Bad Request (client error)
    if doc.file_size > 10_000_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 10MB)"
        )
    
    # 404: Not Found
    project = get_project(doc.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {doc.project_id} not found"
        )
    
    # 500: Internal Server Error
    try:
        result = await process_document(doc)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}"
        )
    
    # 201: Created (success)
    return result
```

### Custom Exception Handler

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class DocumentProcessingError(Exception):
    def __init__(self, doc_id: str, message: str):
        self.doc_id = doc_id
        self.message = message

@app.exception_handler(DocumentProcessingError)
async def document_error_handler(request: Request, exc: DocumentProcessingError):
    return JSONResponse(
        status_code=500,
        content={
            "error": "document_processing_failed",
            "doc_id": exc.doc_id,
            "detail": exc.message
        }
    )
```

---

## 📡 Response Models

### Multiple Response Types

```python
from typing import Union

class SuccessResponse(BaseModel):
    status: str = "success"
    data: dict

class ErrorResponse(BaseModel):
    status: str = "error"
    message: str

@app.post("/process", response_model=Union[SuccessResponse, ErrorResponse])
async def process(data: dict):
    if validate(data):
        return SuccessResponse(data={"result": "processed"})
    return ErrorResponse(message="Validation failed")
```

### Exclude Fields from Response

```python
class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    password: str  # Don't want to return this!
    
    class Config:
        exclude = {"password"}

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    user = db.get_user(user_id)
    return user  # password automatically excluded
```

---

## 🧪 Testing FastAPI

```python
from fastapi.testclient import TestClient

def test_chat_endpoint():
    client = TestClient(app)
    
    response = client.post(
        "/api/chat",
        json={
            "query": "What are the findings?",
            "project_id": "test_123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["citations"]) > 0
```

---

## 💡 Real DevChat Example: RAG Project Creation

From `api/routes/api.py`:

```python
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from supabase import AsyncClient

from api.dependencies import get_supabase, get_current_user
from src.config.costs import estimate_project_cost

router = APIRouter()

class CreateProjectRequest(BaseModel):
    name: str = Field(max_length=100)
    description: Optional[str] = None
    model: str = "gpt-4o"  # Default model

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: str
    document_count: int
    estimated_monthly_cost: float

@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    request: CreateProjectRequest,
    user = Depends(get_current_user),
    db: AsyncClient = Depends(get_supabase)
):
    """
    Create a new RAG project.
    
    A project is an isolated collection of documents with its own:
    - Vector embeddings
    - Configuration (model, prompts)
    - Usage tracking
    """
    # Validate user hasn't exceeded project limit
    existing = await db.table("rag_projects")\\
        .select("id")\\
        .eq("user_id", user.id)\\
        .execute()
    
    if len(existing.data) >= 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 projects per user"
        )
    
    # Create project
    project = await db.table("rag_projects").insert({
        "user_id": user.id,
        "name": request.name,
        "description": request.description,
        "model": request.model,
    }).execute()
    
    project_data = project.data[0]
    
    # Estimate costs
    cost = estimate_project_cost(
        model=request.model,
        expected_queries=100
    )
    
    return ProjectResponse(
        id=project_data["id"],
        name=project_data["name"],
        description=project_data["description"],
        created_at=project_data["created_at"],
        document_count=0,
        estimated_monthly_cost=cost
    )
```

**What's happening:**
1. Request validated by Pydantic
2. Dependencies injected (user, database)
3. Business logic (check limits)
4. Database operation
5. Response formatted and validated

---

## ✅ Knowledge Check

1. What's the difference between `@app.get()` and `@app.post()`?
2. How does FastAPI validate requests?
3. What does `Depends()` do?
4. When should you raise `HTTPException`?
5. What's the benefit of `response_model`?

<details>
<summary>Answers</summary>

1. `get()` for reading data, `post()` for creating/submitting data
2. Uses Pydantic models with type hints
3. Injects dependencies (like database connections) into endpoint functions
4. When you need to return an error response (400, 404, 500, etc.)
5. Validates response data and auto-generates documentation

</details>

---

**Next:** [Post 4: Next.js Basics →](04-nextjs-basics.md)

Learn the frontend framework that powers DevChat's user interface.

---

[🏠 Back to Index](../README.md) | [← Previous](02-python-fundamentals.md) | [Next: Next.js Basics →](04-nextjs-basics.md)
