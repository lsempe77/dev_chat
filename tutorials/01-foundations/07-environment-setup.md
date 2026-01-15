# Post 7: Environment Setup & Configuration

**Part 7 of 50** | ⏱️ 30 minutes | [← Previous](06-authentication.md) | [Next: Error Handling →](08-error-handling.md)

---

## 🎯 What You'll Learn

- Environment variables and secrets management
- Development vs production configuration
- Docker setup for local development
- DevChat configuration patterns

---

## 📖 Environment Variables

### The Configuration Problem

Imagine you're building a house. You need:
- **Foundation** (the code) - same for all houses
- **Address** (database URL) - different for each house
- **Keys** (API keys) - unique to each owner

You can't hardcode the address and keys into the foundation! That's what environment variables solve.

### The Hardcoding Disaster

```python
# ❌ NEVER DO THIS
class Config:
    OPENAI_API_KEY = "sk-proj-abc123"  # Now in Git history forever!
    DATABASE_URL = "postgresql://prod_db"  # Testing on production?!
    ADMIN_PASSWORD = "admin123"  # Security nightmare!
```

**Problems:**
1. **Security breach**: Keys are in Git, anyone can see them
2. **Can't test safely**: How do you use a test database?
3. **Team conflicts**: Everyone needs different local settings
4. **Production accidents**: Easy to test on real data

### Environment Variables: Configuration Per Environment

```python
# ✅ GOOD: Read from environment
import os

class Config:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Different per environment
    DATABASE_URL = os.getenv("DATABASE_URL")      # Dev vs Prod
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")  # Never in code
```

**Now you can have:**

```bash
# Developer Alice's .env
OPENAI_API_KEY=sk-proj-alice-test-key
DATABASE_URL=postgresql://localhost:5432/dev_db

# Developer Bob's .env
OPENAI_API_KEY=sk-proj-bob-test-key
DATABASE_URL=postgresql://localhost:5432/bob_db

# Production server .env
OPENAI_API_KEY=sk-proj-real-production-key
DATABASE_URL=postgresql://prod-server:5432/prod_db
```

**Same code, different config!**

### What Goes in Environment Variables?

✅ **DO store:**
- **API keys**: OpenAI, Anthropic, Cohere (secrets)
- **Database credentials**: URLs, passwords (secrets)
- **Service URLs**: Different per environment
- **Feature flags**: Enable/disable features

❌ **DON'T store:**
- **Application logic**: Belongs in code
- **User data**: Belongs in database
- **Constants**: Just use Python variables

---

## 🔧 DevChat Configuration Files

### Frontend Environment

`frontend/.env.local`:

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# API Backend
NEXT_PUBLIC_API_URL=http://localhost:8000

# Feature Flags
NEXT_PUBLIC_ENABLE_EXPORT=true
NEXT_PUBLIC_MAX_FILE_SIZE_MB=10
```

**Key points:**
- `NEXT_PUBLIC_*` prefix = exposed to browser
- Never put secret keys in `NEXT_PUBLIC_*`
- Loaded automatically by Next.js

### Backend Environment

`.env`:

```bash
# Supabase (Backend)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
# ⚠️ Service key has admin access - never expose!

# LLM APIs
OPENAI_API_KEY=sk-proj-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
COHERE_API_KEY=xxx

# Qdrant Vector DB
QDRANT_URL=https://xxx.qdrant.io
QDRANT_API_KEY=xxx

# Modal (PDF Processing)
MODAL_TOKEN_ID=xxx
MODAL_TOKEN_SECRET=xxx

# Langfuse (Observability)
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_HOST=https://cloud.langfuse.com

# Application Config
ENVIRONMENT=development
LOG_LEVEL=INFO
CACHE_TTL_SECONDS=3600
```

---

## 🐍 Python Configuration

### Using Pydantic Settings

`src/config/settings.py`:

```python
from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Environment
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    
    # Supabase
    supabase_url: str
    supabase_service_key: str
    
    # LLM APIs
    openai_api_key: str
    anthropic_api_key: str | None = None
    cohere_api_key: str
    
    # Qdrant
    qdrant_url: str
    qdrant_api_key: str
    
    # Modal
    modal_token_id: str | None = None
    modal_token_secret: str | None = None
    
    # Langfuse
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    
    # Application
    cache_ttl_seconds: int = 3600
    max_file_size_mb: int = 10
    
    class Config:
        env_file = ".env"
        case_sensitive = False  # OPENAI_API_KEY = openai_api_key

# Singleton instance
settings = Settings()
```

### Using Settings

```python
from src.config.settings import settings

# Access settings anywhere
client = OpenAI(api_key=settings.openai_api_key)

if settings.environment == "production":
    # Production-only logic
    enable_rate_limiting()
```

---

## 🎯 Configuration by Feature

### LLM Configuration

`src/config/llm_config.py`:

```python
from pydantic import BaseModel
from typing import Literal

class LLMConfig(BaseModel):
    """Configuration for LLM calls."""
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 1000
    
    def to_openai_params(self) -> dict:
        """Convert to OpenAI API parameters."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

# Default configs
DEFAULT_CHAT_CONFIG = LLMConfig(
    model="gpt-4o",
    temperature=0.7,
    max_tokens=2000
)

DEFAULT_SYNTHESIS_CONFIG = LLMConfig(
    model="gpt-4o-mini",
    temperature=0.3,  # More deterministic
    max_tokens=1500
)
```

### Cost Configuration

`src/config/costs.py`:

```python
# Token costs per million (as of Jan 2026)
MODEL_COSTS = {
    "gpt-4o": {
        "input": 2.50,   # $2.50 per 1M input tokens
        "output": 10.00  # $10.00 per 1M output tokens
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00
    },
}

def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int
) -> float:
    """Calculate cost in USD."""
    costs = MODEL_COSTS.get(model, MODEL_COSTS["gpt-4o-mini"])
    
    input_cost = (input_tokens / 1_000_000) * costs["input"]
    output_cost = (output_tokens / 1_000_000) * costs["output"]
    
    return input_cost + output_cost
```

---

## 🐳 Docker Setup

### Development Docker Compose

`docker-compose.yml`:

```yaml
version: '3.8'

services:
  # FastAPI backend
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=development
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - QDRANT_URL=${QDRANT_URL}
      - QDRANT_API_KEY=${QDRANT_API_KEY}
    volumes:
      - ./src:/app/src
      - ./api:/app/api
    command: uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
  
  # Next.js frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
      - NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}
      - NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY}
    volumes:
      - ./frontend/src:/app/src
    command: npm run dev
  
  # Redis cache (optional)
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### Backend Dockerfile

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Install package
RUN pip install -e .

# Run server
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Run with Docker

```bash
# Start all services
docker-compose up

# Backend available at http://localhost:8000
# Frontend available at http://localhost:3000

# Stop services
docker-compose down
```

---

## 🚀 Development vs Production

### Understanding the Two Worlds

Your application lives in **two completely different environments**:

**Development (Your Laptop):**
- You're writing and testing code
- Bugs are expected and helpful
- You want detailed error messages
- Speed doesn't matter much
- Fake data is fine

**Production (Real Server):**
- Real users are using your app
- Bugs cost money and trust
- Error messages could expose secrets
- Speed is critical
- Real data only

### Development Mode: Developer-Friendly

```python
from src.config.settings import settings

if settings.environment == "development":
    # 1. VERBOSE LOGGING
    # Show everything so you can debug
    import logging
    logging.basicConfig(level=logging.DEBUG)
    # Output: "Query took 234ms", "Cache miss for key_123", etc.
    
    # 2. DISABLE CACHING
    # So you see changes immediately
    CACHE_ENABLED = False
    # Change code → refresh → see results (no stale cache)
    
    # 3. MOCK EXPENSIVE SERVICES
    # Don't waste API credits while developing
    USE_MOCK_LLM = True
    # OpenAI call → Returns fake data instantly
    # Saves: Time + Money + API rate limits
    
    # 4. DETAILED ERRORS
    # Show full stack traces
    SHOW_STACK_TRACES = True
```

**What this feels like:** Fast iteration, lots of helpful info, forgiving.

### Production Mode: User-Friendly and Secure

```python
if settings.environment == "production":
    # 1. MINIMAL LOGGING
    # Only log errors, not every request
    import logging
    logging.basicConfig(level=logging.WARNING)
    # Reduces: Disk space, performance overhead
    
    # 2. ENABLE CACHING
    # Serve cached responses for speed
    CACHE_ENABLED = True
    # User requests projects → Cache hit → Instant response
    
    # 3. REAL SERVICES ONLY
    # Use actual APIs
    USE_MOCK_LLM = False
    # OpenAI call → Real AI response
    
    # 4. ERROR TRACKING
    # Send errors to Sentry for monitoring
    import sentry_sdk
    sentry_sdk.init(dsn=settings.sentry_dsn)
    # Error occurs → You get notified → Fix before users complain
    
    # 5. HIDE INTERNAL DETAILS
    # Don't expose stack traces to users
    SHOW_STACK_TRACES = False
    # User sees: "Something went wrong" (friendly)
    # You see: Full error in Sentry (detailed)
```

**What this feels like:** Fast, secure, professional.

### How Your Code Knows Which Environment

```bash
# On your laptop
ENVIRONMENT=development

# On Railway production server
ENVIRONMENT=production
```

One variable changes everything!

---

## 🔒 Secrets Management

### Development (Local)

```bash
# .env file (gitignored)
OPENAI_API_KEY=sk-proj-xxx
```

### Production

Use your platform's secrets manager:

#### Vercel (Frontend)

```bash
# Add secrets via CLI
vercel env add NEXT_PUBLIC_SUPABASE_URL
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY
```

#### Railway (Backend)

```bash
# Add via Railway dashboard
# Settings → Variables → Add Variable
OPENAI_API_KEY=sk-proj-xxx
SUPABASE_SERVICE_KEY=xxx
```

#### Modal (Pipeline)

```bash
# Create Modal secrets
modal secret create openai OPENAI_API_KEY=sk-proj-xxx
modal secret create qdrant QDRANT_URL=xxx QDRANT_API_KEY=xxx
```

---

## ⚙️ Configuration Validation

### Validate on Startup

```python
from src.config.settings import settings
from loguru import logger

def validate_config():
    """Validate required configuration on startup."""
    
    # Check required API keys
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required")
    
    if not settings.qdrant_url or not settings.qdrant_api_key:
        raise ValueError("Qdrant configuration is required")
    
    # Validate URLs
    if not settings.supabase_url.startswith("https://"):
        raise ValueError("SUPABASE_URL must be HTTPS")
    
    logger.info(f"✅ Configuration validated for {settings.environment}")

# Run on app startup
if __name__ == "__main__":
    validate_config()
```

---

## 💡 Real DevChat Example

From `api/server.py`:

```python
from fastapi import FastAPI
from src.config.settings import settings
from loguru import logger
import sys

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)

# Create FastAPI app
app = FastAPI(
    title="DevChat API",
    version="2.0.0",
    debug=(settings.environment == "development")
)

@app.on_event("startup")
async def startup():
    """Run on application startup."""
    logger.info(f"🚀 Starting DevChat API in {settings.environment} mode")
    
    # Validate config
    try:
        validate_config()
    except Exception as e:
        logger.error(f"❌ Configuration error: {e}")
        sys.exit(1)
    
    # Initialize services
    await init_qdrant_client()
    await init_langfuse()
    
    logger.info("✅ All services initialized")

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "2.0.0"
    }
```

---

## ✅ Knowledge Check

1. What's the difference between `.env` and `.env.local`?
2. When should you use `NEXT_PUBLIC_*` prefix?
3. Why use Pydantic Settings?
4. How do you validate configuration on startup?
5. Where should you store production secrets?

<details>
<summary>Answers</summary>

1. `.env` is for backend secrets, `.env.local` is for frontend (Next.js convention)
2. When the variable needs to be accessible in browser JavaScript
3. Automatic validation, type hints, and environment variable loading
4. Use a `validate_config()` function that runs on app startup
5. In your platform's secrets manager (Vercel, Railway, Modal, etc.)

</details>

---

**Next:** [Post 8: Error Handling & Logging →](08-error-handling.md)

Learn how to implement robust error handling and observability.

---

[🏠 Back to Index](../README.md) | [← Previous](06-authentication.md) | [Next: Error Handling →](08-error-handling.md)
