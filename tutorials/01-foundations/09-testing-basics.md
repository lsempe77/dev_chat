# Post 9: Testing Basics

**Part 9 of 50** | ⏱️ 45 minutes | [← Previous](08-error-handling.md) | [Next: Deployment Pipeline →](10-deployment-pipeline.md)

---

## 🎯 What You'll Learn

- Python testing with pytest
- Mocking external dependencies
- Testing FastAPI endpoints
- Frontend testing patterns
- DevChat testing strategy

---

## 📖 Why Testing Matters

### The "It Works on My Machine" Problem

**Day 1:** You write a cost calculator

```python
def calculate_cost(tokens: int, model: str) -> float:
    """Calculate cost of LLM API call."""
    rate = MODEL_COSTS.get(model, 0.00001)  # Default rate
    return tokens * rate / 1_000_000

# You test manually:
cost = calculate_cost(1000, "gpt-4o")
print(cost)  # 0.0025 - looks right!
```

**Day 30:** Your teammate refactors

```python
def calculate_cost(tokens: int, model: str) -> float:
    """Calculate cost of LLM API call."""
    rate = MODEL_COSTS[model]  # Oops! Removed .get()
    return tokens * rate / 1_000_000

# New model comes out
calculate_cost(1000, "gpt-5")
# 💥 KeyError: 'gpt-5' - App crashes!
```

**Day 60:** You need to change the formula

```python
def calculate_cost(tokens: int, model: str) -> float:
    """Calculate cost with 20% markup."""
    rate = MODEL_COSTS.get(model, 0.00001)
    return tokens * rate * 1.2 / 1_000_000  # Added markup

# Did this break anything? No idea! 🤷
# Manually test every model? Takes hours!
```

### With Tests: Confidence and Speed

```python
# Your code
def calculate_cost(tokens: int, model: str) -> float:
    """Calculate cost of LLM API call."""
    rate = MODEL_COSTS.get(model, 0.00001)
    return tokens * rate / 1_000_000

# Your tests (written once)
def test_calculate_cost_gpt4o():
    """Test cost for GPT-4o."""
    cost = calculate_cost(1_000_000, "gpt-4o")
    assert cost == 2.50  # 1M tokens at $2.50/M

def test_calculate_cost_unknown_model():
    """Test fallback for unknown model."""
    cost = calculate_cost(1_000_000, "gpt-99")
    assert cost == 10.00  # Falls back to default

def test_calculate_cost_zero_tokens():
    """Test edge case: zero tokens."""
    cost = calculate_cost(0, "gpt-4o")
    assert cost == 0.0

def test_calculate_cost_negative_tokens():
    """Test invalid input."""
    with pytest.raises(ValueError):
        calculate_cost(-100, "gpt-4o")
```

**Now when changes happen:**

```bash
# Run tests
$ pytest tests/test_costs.py

# Day 30: Teammate removes .get()
test_calculate_cost_unknown_model FAILED ❌
# Caught before deploy!

# Day 60: You add markup
test_calculate_cost_gpt4o FAILED ❌
# Expected 2.50, got 3.00
# Update test to reflect new markup

# All tests pass ✅
# Deploy with confidence!
```

### Tests as Documentation

Tests show **how your code should be used**:

```python
# Reading this function signature:
def calculate_cost(tokens: int, model: str) -> float:
    ...

# Questions:
# - What happens with 0 tokens?
# - What if model doesn't exist?
# - What about negative tokens?
# - How is the cost calculated?

# Reading the tests:
def test_calculate_cost():
    # ✅ 0 tokens = $0
    assert calculate_cost(0, "gpt-4o") == 0.0
    
    # ✅ Unknown model = uses default
    assert calculate_cost(1000, "unknown") > 0
    
    # ✅ Negative tokens = error
    with pytest.raises(ValueError):
        calculate_cost(-100, "gpt-4o")
    
    # ✅ Formula: tokens * rate / 1M
    assert calculate_cost(1_000_000, "gpt-4o") == 2.50

# Now you know exactly how it works!
```

---

## 🐍 Python Testing with pytest

### Setup

```bash
pip install pytest pytest-asyncio pytest-cov
```

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
asyncio_mode = "auto"
```

### Basic Test Structure

```
tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── test_retrieval.py
├── test_generation.py
├── test_agents.py
└── integration/
    └── test_api.py
```

---

## ✅ Writing Tests

### Simple Function Test

```python
# tests/test_costs.py
from src.config.costs import calculate_cost, MODEL_COSTS

def test_calculate_cost_gpt4o():
    """Test cost calculation for GPT-4o."""
    cost = calculate_cost(
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=500
    )
    
    # 1000 tokens * $2.50/1M + 500 tokens * $10.00/1M
    expected = (1000 / 1_000_000 * 2.50) + (500 / 1_000_000 * 10.00)
    assert cost == expected

def test_calculate_cost_zero_tokens():
    """Test with zero tokens."""
    cost = calculate_cost("gpt-4o", 0, 0)
    assert cost == 0

def test_calculate_cost_unknown_model():
    """Test with unknown model falls back to default."""
    cost = calculate_cost("gpt-99", 1000, 500)
    # Should use gpt-4o-mini costs
    assert cost > 0
```

### Async Function Test

```python
# tests/test_retrieval.py
import pytest
from src.retrieval.hybrid_retriever import HybridRetriever

@pytest.mark.asyncio
async def test_search_returns_results():
    """Test that search returns documents."""
    retriever = HybridRetriever()
    
    results = await retriever.search(
        query="What are the effects of cash transfers?",
        limit=5
    )
    
    assert len(results) > 0
    assert len(results) <= 5
    assert all(hasattr(r, 'content') for r in results)
    assert all(hasattr(r, 'score') for r in results)
```

---

## 🎭 Mocking External Services

### Mock API Calls

```python
# tests/test_metadata_enrichment.py
from unittest.mock import patch, Mock
from src.ingestion.metadata_enricher import enrich_from_doi

@patch('requests.get')
def test_enrich_from_doi(mock_get):
    """Test metadata enrichment from DOI."""
    
    # Mock API response
    mock_response = Mock()
    mock_response.json.return_value = {
        "message": {
            "title": ["Test Paper"],
            "author": [{"given": "Alice", "family": "Smith"}],
            "published": {"date-parts": [[2024, 1, 15]]}
        }
    }
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    
    # Test function
    metadata = enrich_from_doi("10.1234/test")
    
    assert metadata["title"] == "Test Paper"
    assert len(metadata["authors"]) == 1
    assert metadata["year"] == 2024
    
    # Verify API was called
    mock_get.assert_called_once_with(
        "https://api.crossref.org/works/10.1234/test"
    )
```

### Mock LLM Calls

```python
# tests/test_chat_agent.py
import pytest
from unittest.mock import AsyncMock, patch
from src.agents.devchat_agent import DevChatAgent

@pytest.mark.asyncio
@patch('src.agents.devchat_agent.OpenAI')
async def test_query_with_mock_llm(mock_openai_class):
    """Test agent with mocked LLM."""
    
    # Mock LLM response
    mock_client = AsyncMock()
    mock_openai_class.return_value = mock_client
    
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(
            choices=[Mock(
                message=Mock(content="Cash transfers increase consumption.")
            )],
            usage=Mock(
                prompt_tokens=100,
                completion_tokens=50
            )
        )
    )
    
    # Test agent
    agent = DevChatAgent()
    response = await agent.query(
        query="What are the effects?",
        project_id="test_123",
        user_id="user_456"
    )
    
    assert "consumption" in response["answer"].lower()
    assert response["tokens"]["input"] == 100
    assert response["tokens"]["output"] == 50
```

---

## 🏭 Fixtures

Reusable test setup with pytest fixtures.

### conftest.py

```python
# tests/conftest.py
import pytest
from supabase import create_client
from src.config.settings import settings

@pytest.fixture
def supabase_client():
    """Supabase client fixture."""
    return create_client(
        settings.supabase_url,
        settings.supabase_service_key
    )

@pytest.fixture
async def test_user(supabase_client):
    """Create a test user."""
    user = supabase_client.auth.admin.create_user({
        "email": "test@example.com",
        "password": "testpass123"
    })
    
    yield user
    
    # Cleanup
    supabase_client.auth.admin.delete_user(user.id)

@pytest.fixture
async def test_project(supabase_client, test_user):
    """Create a test project."""
    project = supabase_client.table("rag_projects").insert({
        "user_id": test_user.id,
        "name": "Test Project",
        "model": "gpt-4o"
    }).execute()
    
    yield project.data[0]
    
    # Cleanup
    supabase_client.table("rag_projects")\\
        .delete()\\
        .eq("id", project.data[0]["id"])\\
        .execute()
```

### Using Fixtures

```python
# tests/test_projects.py
def test_create_project(supabase_client, test_user):
    """Test project creation."""
    project = supabase_client.table("rag_projects").insert({
        "user_id": test_user.id,
        "name": "My Project"
    }).execute()
    
    assert len(project.data) == 1
    assert project.data[0]["name"] == "My Project"

async def test_query_project(test_project):
    """Test querying with existing project."""
    # test_project fixture automatically created
    assert test_project["name"] == "Test Project"
```

---

## 🚀 Testing FastAPI

### Test Client

```python
# tests/integration/test_api.py
from fastapi.testclient import TestClient
from api.server import app

client = TestClient(app)

def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_project():
    """Test project creation endpoint."""
    response = client.post(
        "/api/projects",
        json={
            "name": "Test Project",
            "description": "A test project"
        },
        headers={"Authorization": "Bearer test_token"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Project"
    assert "id" in data

def test_create_project_invalid_data():
    """Test validation errors."""
    response = client.post(
        "/api/projects",
        json={"name": ""},  # Empty name
        headers={"Authorization": "Bearer test_token"}
    )
    
    assert response.status_code == 422  # Validation error
```

### Authenticated Requests

```python
import pytest
from unittest.mock import patch

@pytest.fixture
def auth_headers():
    """Generate auth headers for testing."""
    return {"Authorization": "Bearer test_token"}

@patch('api.dependencies.get_current_user')
def test_protected_endpoint(mock_auth, auth_headers):
    """Test endpoint that requires authentication."""
    
    # Mock authentication
    mock_auth.return_value = {
        "id": "user_123",
        "email": "test@example.com"
    }
    
    response = client.get(
        "/api/projects",
        headers=auth_headers
    )
    
    assert response.status_code == 200

def test_protected_endpoint_no_auth():
    """Test endpoint without authentication."""
    response = client.get("/api/projects")
    assert response.status_code == 403  # Forbidden
```

---

## 💻 Frontend Testing (Brief Overview)

### Jest + React Testing Library

```typescript
// __tests__/ChatInput.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import ChatInput from '@/components/ChatInput'

describe('ChatInput', () => {
  it('renders input field', () => {
    render(<ChatInput onSend={jest.fn()} />)
    
    const input = screen.getByPlaceholderText(/type your message/i)
    expect(input).toBeInTheDocument()
  })
  
  it('calls onSend when submitted', () => {
    const mockSend = jest.fn()
    render(<ChatInput onSend={mockSend} />)
    
    const input = screen.getByRole('textbox')
    const button = screen.getByRole('button', { name: /send/i })
    
    fireEvent.change(input, { target: { value: 'Hello' } })
    fireEvent.click(button)
    
    expect(mockSend).toHaveBeenCalledWith('Hello')
  })
  
  it('disables input when loading', () => {
    render(<ChatInput onSend={jest.fn()} disabled />)
    
    const input = screen.getByRole('textbox')
    expect(input).toBeDisabled()
  })
})
```

---

## 📊 Test Coverage

```bash
# Run with coverage report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

`pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src", "api"]
omit = [
    "*/tests/*",
    "*/conftest.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

---

## 🎯 DevChat Testing Strategy

### Test Pyramid

```
        /\\
       /  \\    E2E Tests (5%)
      /----\\   - Full user flows
     /      \\  - Slow, expensive
    /--------\\
   / Integration \\ (15%)
  /  Tests       \\ - API endpoints
 /-----------------\\ - Database queries
/                   \\
/    Unit Tests     \\ (80%)
/   (Fast, Focused) \\ - Pure functions
---------------------- - Business logic
```

### What to Test

✅ **DO test:**
- Core business logic
- API endpoints
- Data transformations
- Edge cases and errors
- Critical user flows

❌ **DON'T test:**
- Third-party libraries
- Simple getters/setters
- Configuration files
- Generated code

### Example Test Suite

```python
# tests/test_claim_ledger.py
import pytest
from src.generation.claim_ledger import ClaimLedgerSynthesizer

class TestClaimLedgerSynthesizer:
    """Test suite for claim extraction and synthesis."""
    
    @pytest.fixture
    def synthesizer(self):
        return ClaimLedgerSynthesizer()
    
    async def test_extract_claims(self, synthesizer):
        """Test claim extraction from text."""
        text = "Cash transfers increase consumption by 10%."
        
        claims = await synthesizer.extract_claims(text)
        
        assert len(claims) > 0
        assert any("consumption" in c.text.lower() for c in claims)
    
    async def test_verify_claims(self, synthesizer):
        """Test claim verification."""
        claim = "Cash transfers increase consumption."
        context = "Cash transfers lead to higher spending."
        
        is_supported = await synthesizer.verify_claim(claim, context)
        
        assert is_supported is True
    
    async def test_synthesize_response(self, synthesizer):
        """Test full synthesis pipeline."""
        query = "What are the effects of cash transfers?"
        documents = [...]  # Mock documents
        
        response = await synthesizer.synthesize(query, documents)
        
        assert len(response.answer) > 0
        assert len(response.citations) > 0
        assert all(c.score > 0 for c in response.citations)
```

---

## ✅ Knowledge Check

1. What's the difference between unit tests and integration tests?
2. When should you use mocks?
3. What are pytest fixtures?
4. How do you test async functions?
5. What's a good test coverage target?

<details>
<summary>Answers</summary>

1. Unit tests test individual functions, integration tests test multiple components together
2. When testing code that depends on external services (APIs, databases)
3. Reusable test setup/teardown code that can be injected into tests
4. Use `@pytest.mark.asyncio` decorator and `await` in the test function
5. 70-80% is a good target, but 100% isn't necessary (focus on critical paths)

</details>

---

**Next:** [Post 10: Deployment Pipeline →](10-deployment-pipeline.md)

Learn how to deploy DevChat to production with CI/CD.

---

[🏠 Back to Index](../README.md) | [← Previous](08-error-handling.md) | [Next: Deployment Pipeline →](10-deployment-pipeline.md)
