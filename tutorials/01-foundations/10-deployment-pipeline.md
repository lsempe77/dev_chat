# Post 10: Deployment Pipeline

**Part 10 of 50** | ⏱️ 45 minutes | [← Previous](09-testing-basics.md) | [Next: PDF Processing →](../02-document-processing/11-pdf-parsing.md)

---

## 🎯 What You'll Learn

- CI/CD fundamentals
- GitHub Actions for automated testing
- Deploying to Vercel (frontend)
- Deploying to Railway (backend)
- Environment management

---

## 📖 What is CI/CD?

### The Old Way: Manual Deployment (Scary!)

**Every time you want to deploy:**

```bash
# Step 1: Remember to test
$ pytest tests/  # Did you test EVERYTHING?

# Step 2: Remember to lint
$ ruff check .   # Did you check style?

# Step 3: Build Docker image
$ docker build -t myapp .

# Step 4: SSH into server
$ ssh production-server

# Step 5: Pull new code
$ git pull origin main

# Step 6: Restart server
$ systemctl restart myapp

# Step 7: Check if it works
$ curl https://myapp.com/health

# 🤞 Hope nothing broke!
```

**Problems:**
- 😰 **Scary**: What if you forget a step?
- 🐌 **Slow**: Takes 30+ minutes
- 🎲 **Inconsistent**: Different every time
- 💥 **Error-prone**: Typos, wrong commands
- 😴 **Late night**: Deploy at 2am because users are asleep
- 🤔 **What broke?**: Hard to find which commit caused issues

### The New Way: CI/CD (Automated!)

**What you do:**

```bash
git add .
git commit -m "Add new feature"
git push origin main

# That's it! 🎉
```

**What happens automatically:**

```
┌──────────────────┐
│   You push code  │
└────────┬─────────┘
         │
         ▼
┌────────────────────────────┐
│  GitHub Actions (CI)       │
├────────────────────────────┤
│  1. ✅ Run tests           │  ← Catches bugs
│  2. ✅ Check code style    │  ← Enforces standards  
│  3. ✅ Type check          │  ← Finds type errors
│  4. ✅ Build Docker image  │  ← Packages app
└────────┬───────────────────┘
         │
         ▼ (Only if all pass!)
┌────────────────────────────┐
│  Deployment (CD)           │
├────────────────────────────┤
│  1. 🚀 Deploy to Railway   │  ← Backend live
│  2. 🚀 Deploy to Vercel    │  ← Frontend live
│  3. 📧 Notify team          │  ← "Deploy successful!"
└────────────────────────────┘

Time: 5 minutes, automatic! ⚡
```

### CI: Continuous Integration (Testing)

**What it does:** Tests every commit automatically.

**Why it matters:**

```python
# You write code:
def calculate_cost(tokens, model):
    return tokens * MODEL_COSTS[model] / 1_000_000

# You push
# GitHub Actions runs:
$ pytest tests/

test_calculate_cost_unknown_model FAILED ❌
KeyError: 'gpt-5'

# Deploy STOPS ✋
# You see the error immediately
# Fix it before users see it!
```

**Without CI:** Bug goes to production → Users complain → Emergency fix at midnight

**With CI:** Bug caught in 2 minutes → Fix before deploy → Users never see it

### CD: Continuous Deployment (Releasing)

**What it does:** Deploys passing code automatically.

**Why it matters:**

- **Deploy anytime:** Push at 3pm, auto-deploys in 5 minutes
- **Deploy often:** 10 small deploys safer than 1 big deploy
- **Rollback fast:** Bad deploy? One click to revert
- **No human error:** Same process every time

### Real-World Example

**Before CI/CD:**
```
Monday: Write feature
Tuesday: Write more code
Wednesday: Write more code  
Thursday: Write more code
Friday 5pm: Try to deploy
Friday 11pm: Still debugging deploy
Saturday 2am: Finally works

Deploys: Once per week, takes 6+ hours
```

**With CI/CD:**
```
Monday: Write feature → Push → Auto-deployed in 5 min ✅
Tuesday: Fix bug → Push → Auto-deployed in 5 min ✅
Wednesday: Add docs → Push → Auto-deployed in 5 min ✅
Thursday: Refactor → Push → Auto-deployed in 5 min ✅
Friday 5pm: Go home, everything is deployed!

Deploys: 20+ times per week, 5 minutes each
```

---

## 🔧 GitHub Actions

### Workflow Structure

`.github/workflows/test.yml`:

```yaml
name: Test & Lint

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    
    steps:
      # 1. Checkout code
      - name: Checkout
        uses: actions/checkout@v4
      
      # 2. Setup Python
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      
      # 3. Install dependencies
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -e .
      
      # 4. Lint code
      - name: Lint with ruff
        run: ruff check .
      
      # 5. Type check
      - name: Type check with mypy
        run: mypy src/ api/
        continue-on-error: true  # Don't fail on type errors
      
      # 6. Run tests
      - name: Run tests
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pytest tests/ -v --cov=src --cov-report=xml
      
      # 7. Upload coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
  
  test-frontend:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      
      - name: Install dependencies
        working-directory: ./frontend
        run: npm ci
      
      - name: Lint
        working-directory: ./frontend
        run: npm run lint
      
      - name: Type check
        working-directory: ./frontend
        run: npm run type-check
      
      - name: Build
        working-directory: ./frontend
        run: npm run build
```

---

## 🚀 Backend Deployment (Railway)

### Setup Railway

1. Install Railway CLI:
```bash
npm install -g railway
```

2. Login:
```bash
railway login
```

3. Link project:
```bash
railway link
```

### railway.json

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "uvicorn api.server:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Production Dockerfile

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    g++ \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements-prod.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application
COPY . .

# Install package
RUN pip install -e .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run server
CMD uvicorn api.server:app --host 0.0.0.0 --port $PORT --workers 2
```

### Environment Variables in Railway

Add via Railway dashboard:
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=***
OPENAI_API_KEY=***
QDRANT_URL=***
QDRANT_API_KEY=***
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

### Deploy

```bash
# Manual deploy
railway up

# Auto-deploy on push (configure in Railway dashboard)
# Settings → Deploys → Trigger: Push to main
```

---

## 🌐 Frontend Deployment (Vercel)

### Setup Vercel

1. Install Vercel CLI:
```bash
npm install -g vercel
```

2. Login:
```bash
vercel login
```

3. Link project:
```bash
cd frontend
vercel link
```

### vercel.json

`frontend/vercel.json`:

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "framework": "nextjs",
  "regions": ["iad1"],
  "env": {
    "NEXT_PUBLIC_API_URL": "@api-url",
    "NEXT_PUBLIC_SUPABASE_URL": "@supabase-url",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY": "@supabase-anon-key"
  }
}
```

### Environment Variables in Vercel

Add via Vercel dashboard or CLI:

```bash
# Production
vercel env add NEXT_PUBLIC_API_URL production
# Enter: https://devchat-api.railway.app

vercel env add NEXT_PUBLIC_SUPABASE_URL production
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production

# Preview (for PR previews)
vercel env add NEXT_PUBLIC_API_URL preview
# Enter: https://devchat-api-staging.railway.app
```

### Deploy

```bash
# Manual deploy
cd frontend
vercel --prod

# Auto-deploy on push
# Connected automatically when linking GitHub repo
```

---

## 🐳 Modal Deployment (PDF Pipeline)

### Modal Setup

`infrastructure/modal_mineru.py`:

```python
import modal

# Create Modal app
app = modal.App("devchat-pdf-processing")

# Define image with dependencies
image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "magic-pdf[full]",
    "supabase",
    "qdrant-client"
)

# Add secrets
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("supabase"),
        modal.Secret.from_name("qdrant")
    ],
    gpu="A10G",  # GPU for faster processing
    timeout=600   # 10 minute timeout
)
def process_pdf(pdf_url: str, doc_id: str):
    """Process a PDF document."""
    from modal_lib.pdf_parser import parse_pdf
    from modal_lib.chunker import chunk_text
    from modal_lib.embedder import embed_chunks
    
    # Parse PDF
    text = parse_pdf(pdf_url)
    
    # Chunk text
    chunks = chunk_text(text)
    
    # Generate embeddings
    embedded = embed_chunks(chunks)
    
    # Store in Qdrant
    store_embeddings(doc_id, embedded)
    
    return {"status": "success", "chunks": len(chunks)}
```

### Deploy to Modal

```bash
# Deploy function
modal deploy infrastructure/modal_mineru.py

# Test
modal run infrastructure/modal_mineru.py::process_pdf --pdf-url "https://..."
```

### Call from Backend

```python
# api/routes/documents.py
import modal

@router.post("/documents/{doc_id}/process")
async def trigger_processing(doc_id: str):
    """Trigger Modal processing for document."""
    
    # Get document URL
    doc = supabase.table("documents")\\
        .select("file_path")\\
        .eq("id", doc_id)\\
        .single()\\
        .execute()
    
    # Call Modal function
    f = modal.Function.lookup("devchat-pdf-processing", "process_pdf")
    result = f.remote(
        pdf_url=doc.data["file_path"],
        doc_id=doc_id
    )
    
    return {"status": "processing", "job_id": result}
```

---

## 🔄 Complete CI/CD Workflow

### Multi-Environment Setup

```
main branch
    ↓
┌───────────────┐
│ GitHub Action │
│ - Test        │
│ - Lint        │
│ - Build       │
└───────┬───────┘
        ↓ (on success)
        ├─────────────────┐
        ↓                 ↓
┌──────────────┐  ┌──────────────┐
│   Railway    │  │   Vercel     │
│  (Backend)   │  │  (Frontend)  │
│  Production  │  │  Production  │
└──────────────┘  └──────────────┘
```

### Full Deployment Workflow

`.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run tests
        run: |
          pip install -r requirements.txt
          pytest tests/
  
  deploy-backend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to Railway
        uses: railwayapp/cli-action@v1
        with:
          railway_token: ${{ secrets.RAILWAY_TOKEN }}
        run: railway up --service backend
  
  deploy-frontend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to Vercel
        uses: amondnet/vercel-action@v20
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          vercel-args: '--prod'
          working-directory: ./frontend
```

---

## 📊 Monitoring & Rollback

### Health Checks

```python
# api/server.py

@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "services": {}
    }
    
    # Check Supabase
    try:
        supabase.table("rag_projects").select("id").limit(1).execute()
        checks["services"]["supabase"] = "healthy"
    except Exception as e:
        checks["services"]["supabase"] = "unhealthy"
        checks["status"] = "degraded"
    
    # Check Qdrant
    try:
        qdrant.get_collections()
        checks["services"]["qdrant"] = "healthy"
    except Exception as e:
        checks["services"]["qdrant"] = "unhealthy"
        checks["status"] = "degraded"
    
    return checks
```

### Rollback

```bash
# Railway rollback
railway rollback

# Vercel rollback
vercel rollback
```

---

## ✅ Knowledge Check

1. What's the difference between CI and CD?
2. When do GitHub Actions run?
3. How do you add environment variables to Railway/Vercel?
4. What's a health check endpoint?
5. How do you rollback a bad deployment?

<details>
<summary>Answers</summary>

1. CI = test automatically, CD = deploy automatically
2. On push, pull request, or scheduled (defined in workflow YAML)
3. Via dashboard (Settings → Variables) or CLI
4. An endpoint that returns service status (used by load balancers to check if app is running)
5. Use platform CLI (`railway rollback` or `vercel rollback`)

</details>

---

## 🎉 Foundations Complete!

You've completed Part 1 (Posts 1-10) covering:
- ✅ Project architecture
- ✅ Python and FastAPI fundamentals
- ✅ Next.js frontend basics
- ✅ Database and authentication
- ✅ Configuration and error handling
- ✅ Testing and deployment

**Next:** [Part 2: Document Processing →](../02-document-processing/11-pdf-parsing.md)

Dive into PDF parsing, chunking, and metadata enrichment.

---

[🏠 Back to Index](../README.md) | [← Previous](09-testing-basics.md) | [Next: PDF Processing →](../02-document-processing/11-pdf-parsing.md)
