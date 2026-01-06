"""
RAG Project Management API Routes

Allows authenticated users to create, list, update, and delete their RAG projects.
Each RAG project corresponds to a separate Qdrant collection.
"""

import hashlib
import os
import difflib
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field
from botocore.exceptions import ClientError

from src.auth import AuthenticatedUser, get_current_user, get_supabase_client, is_multi_tenant_enabled
from src.utils.logging import get_logger
from src.ingestion.indexer import QdrantIndexer
from src.config.settings import settings
from .dependencies import get_r2_client

logger = get_logger(__name__)

router = APIRouter(prefix="/rags", tags=["RAG Projects"])


# =============================================================================
# Pydantic Models
# =============================================================================

# Available LLM providers and models (via OpenRouter)
AVAILABLE_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": {
            "gpt-4o-mini": {"name": "GPT-4o Mini", "type": "fast", "cost_per_1k": 0.00015},
            "gpt-4o": {"name": "GPT-4o", "type": "reasoning", "cost_per_1k": 0.0025},
            "gpt-4-turbo": {"name": "GPT-4 Turbo", "type": "reasoning", "cost_per_1k": 0.01},
        }
    },
    "anthropic": {
        "name": "Anthropic",
        "models": {
            "claude-3-5-haiku-20241022": {"name": "Claude 3.5 Haiku", "type": "fast", "cost_per_1k": 0.0008},
            "claude-sonnet-4-20250514": {"name": "Claude Sonnet 4", "type": "reasoning", "cost_per_1k": 0.003},
            "claude-3-5-sonnet-20241022": {"name": "Claude 3.5 Sonnet", "type": "reasoning", "cost_per_1k": 0.003},
        }
    },
    "google": {
        "name": "Google",
        "models": {
            "gemini-2.0-flash-exp": {"name": "Gemini 2.0 Flash", "type": "fast", "cost_per_1k": 0.0},
            "gemini-exp-1206": {"name": "Gemini Exp", "type": "reasoning", "cost_per_1k": 0.0},
        }
    },
}

# Default model configuration
DEFAULT_MODEL_CONFIG = {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "reasoning_model": "gpt-4o",
    "temperature": 0.1,
}


class ModelConfig(BaseModel):
    """LLM configuration for a RAG project."""
    provider: str = Field(default="openai", description="LLM provider: openai, anthropic, google")
    model: str = Field(default="gpt-4o-mini", description="Fast model for simple tasks")
    reasoning_model: str = Field(default="gpt-4o", description="Strong model for synthesis")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0, description="LLM temperature")


class PromptHistoryEntry(BaseModel):
    """A historical version of custom prompts."""
    extraction: Optional[str] = None
    synthesis: Optional[str] = None
    saved_at: str


class CustomPrompts(BaseModel):
    """Custom prompts for extraction and synthesis (advanced feature)."""
    extraction: Optional[str] = Field(None, max_length=10000, description="Custom extraction prompt")
    synthesis: Optional[str] = Field(None, max_length=10000, description="Custom synthesis prompt")
    modified_at: Optional[str] = Field(None, description="When prompts were last modified")
    history: Optional[List[PromptHistoryEntry]] = Field(default=None, description="Previous prompt versions (max 10)")


class PromptConfig(BaseModel):
    """Prompt configuration for a RAG project."""
    context_prompt: Optional[str] = Field(
        None, 
        max_length=2000, 
        description="Domain-specific instructions (e.g., 'You are a health economics expert')"
    )
    custom_prompts: Optional[CustomPrompts] = Field(
        None, 
        description="Advanced: Custom extraction/synthesis prompts. May break citation quality!"
    )


class RAGProjectCreate(BaseModel):
    """Request to create a new RAG project."""
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    description: Optional[str] = Field(None, max_length=500, description="Project description")
    slug: Optional[str] = Field(None, max_length=50, description="URL-friendly identifier")
    is_public: bool = Field(default=False, description="Whether the RAG is publicly accessible")
    model_config_data: Optional[ModelConfig] = Field(None, description="LLM configuration")


class RAGProjectUpdate(BaseModel):
    """Request to update a RAG project."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    slug: Optional[str] = Field(None, max_length=50)
    is_public: Optional[bool] = None
    model_config_data: Optional[ModelConfig] = Field(None, description="LLM configuration")


class RAGProjectResponse(BaseModel):
    """Response for a RAG project."""
    id: str
    name: str
    description: Optional[str]
    slug: Optional[str]
    qdrant_collection: str
    is_public: bool
    status: str
    document_count: int
    chunk_count: int
    model_config_data: Optional[ModelConfig] = None
    context_prompt: Optional[str] = None
    custom_prompts: Optional[CustomPrompts] = None
    created_at: datetime
    updated_at: datetime


class RAGProjectListResponse(BaseModel):
    """Response for listing RAG projects."""
    projects: List[RAGProjectResponse]
    total: int


class RAGProjectDetailResponse(RAGProjectResponse):
    """Detailed response for a single RAG project."""
    # Additional stats can be added here
    pass


# =============================================================================
# Helper Functions
# =============================================================================

async def get_user_project(user: AuthenticatedUser, project_id: str) -> dict:
    """
    Get a RAG project owned by the user.
    
    Raises HTTPException if not found or not owned by user.
    """
    client = get_supabase_client()
    
    result = client.table("rag_projects").select("*").eq("id", project_id).eq("user_id", user.id).single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG project not found"
        )
    
    return result.data


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=RAGProjectListResponse)
async def list_rag_projects(
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectListResponse:
    """
    List all RAG projects owned by the current user.
    """
    client = get_supabase_client()
    
    result = client.table("rag_projects").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
    
    projects = [
        RAGProjectResponse(
            id=str(p["id"]),
            name=p["name"],
            description=p.get("description"),
            slug=p.get("slug"),
            qdrant_collection=p["qdrant_collection"],
            is_public=p.get("is_public", False),
            status=p["status"],
            document_count=p.get("document_count", 0),
            chunk_count=p.get("chunk_count", 0),
            model_config_data=ModelConfig(**p["model_config"]) if p.get("model_config") else None,
            context_prompt=p.get("context_prompt"),
            custom_prompts=CustomPrompts(**p["custom_prompts"]) if p.get("custom_prompts") else None,
            created_at=p["created_at"],
            updated_at=p["updated_at"],
        )
        for p in result.data or []
    ]
    
    return RAGProjectListResponse(projects=projects, total=len(projects))


@router.post("", response_model=RAGProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_rag_project(
    request: RAGProjectCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectResponse:
    """
    Create a new RAG project.
    
    This will:
    1. Create a database record
    2. Create a new Qdrant collection for the project
    """
    client = get_supabase_client()
    
    # Check for duplicate name
    existing = client.table("rag_projects").select("id").eq("user_id", user.id).eq("name", request.name).execute()
    
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A RAG project named '{request.name}' already exists"
        )
    
    try:
        # Prepare model config for database
        model_config = request.model_config_data.model_dump() if request.model_config_data else DEFAULT_MODEL_CONFIG
        
        # Create the project record (qdrant_collection is auto-generated by trigger)
        result = client.table("rag_projects").insert({
            "user_id": user.id,
            "name": request.name,
            "description": request.description,
            "slug": request.slug,
            "is_public": request.is_public,
            "model_config": model_config,
        }).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create RAG project"
            )
        
        project = result.data[0]
        collection_name = project["qdrant_collection"]
        
        # Create the Qdrant collection
        try:
            indexer = QdrantIndexer(
                collection_name=collection_name,
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
            )
            # This will create the collection if it doesn't exist
            await indexer.ensure_collection_exists()
            logger.info(f"Created Qdrant collection: {collection_name}")
        except Exception as e:
            # Rollback the database record
            client.table("rag_projects").delete().eq("id", project["id"]).execute()
            logger.error(f"Failed to create Qdrant collection: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create vector store collection"
            )
        
        return RAGProjectResponse(
            id=str(project["id"]),
            name=project["name"],
            description=project.get("description"),
            slug=project.get("slug"),
            qdrant_collection=project["qdrant_collection"],
            is_public=project.get("is_public", False),
            status=project["status"],
            document_count=0,
            chunk_count=0,
            model_config_data=ModelConfig(**project["model_config"]) if project.get("model_config") else None,
            context_prompt=project.get("context_prompt"),
            custom_prompts=CustomPrompts(**project["custom_prompts"]) if project.get("custom_prompts") else None,
            created_at=project["created_at"],
            updated_at=project["updated_at"],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating RAG project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create RAG project"
        )


@router.get("/{project_id}", response_model=RAGProjectDetailResponse)
async def get_rag_project(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectDetailResponse:
    """
    Get details of a specific RAG project.
    """
    project = await get_user_project(user, project_id)
    
    return RAGProjectDetailResponse(
        id=str(project["id"]),
        name=project["name"],
        description=project.get("description"),
        slug=project.get("slug"),
        qdrant_collection=project["qdrant_collection"],
        is_public=project.get("is_public", False),
        status=project["status"],
        document_count=project.get("document_count", 0),
        chunk_count=project.get("chunk_count", 0),
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


@router.patch("/{project_id}", response_model=RAGProjectResponse)
async def update_rag_project(
    project_id: str,
    request: RAGProjectUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectResponse:
    """
    Update a RAG project's name or description.
    """
    # Verify ownership
    await get_user_project(user, project_id)
    
    client = get_supabase_client()
    
    update_data = {}
    if request.name is not None:
        # Check for duplicate name
        existing = client.table("rag_projects").select("id").eq("user_id", user.id).eq("name", request.name).neq("id", project_id).execute()
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A RAG project named '{request.name}' already exists"
            )
        update_data["name"] = request.name
    
    if request.description is not None:
        update_data["description"] = request.description
    
    if request.slug is not None:
        # Check for duplicate slug
        if request.slug:
            existing = client.table("rag_projects").select("id").eq("slug", request.slug).neq("id", project_id).execute()
            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A RAG project with slug '{request.slug}' already exists"
                )
        update_data["slug"] = request.slug if request.slug else None
    
    if request.is_public is not None:
        update_data["is_public"] = request.is_public
    
    if request.model_config_data is not None:
        update_data["model_config"] = request.model_config_data.model_dump()
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    result = client.table("rag_projects").update(update_data).eq("id", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update project"
        )
    
    project = result.data[0]
    
    return RAGProjectResponse(
        id=str(project["id"]),
        name=project["name"],
        description=project.get("description"),
        slug=project.get("slug"),
        qdrant_collection=project["qdrant_collection"],
        is_public=project.get("is_public", False),
        status=project["status"],
        document_count=project.get("document_count", 0),
        chunk_count=project.get("chunk_count", 0),
        model_config_data=ModelConfig(**project["model_config"]) if project.get("model_config") else None,
        context_prompt=project.get("context_prompt"),
        custom_prompts=CustomPrompts(**project["custom_prompts"]) if project.get("custom_prompts") else None,
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


# =============================================================================
# Model Configuration Endpoints
# =============================================================================

class AvailableModelsResponse(BaseModel):
    """Response containing available LLM providers and models."""
    providers: dict


@router.get("/models/available", response_model=AvailableModelsResponse)
async def get_available_models() -> AvailableModelsResponse:
    """
    Get available LLM providers and models.
    
    Returns a dictionary of providers with their available models,
    model types (fast vs reasoning), and cost per 1k tokens.
    """
    return AvailableModelsResponse(providers=AVAILABLE_PROVIDERS)


class ModelConfigResponse(BaseModel):
    """Response for model configuration."""
    model_config_data: ModelConfig


@router.get("/{project_id}/model-config", response_model=ModelConfigResponse)
async def get_project_model_config(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ModelConfigResponse:
    """
    Get the LLM model configuration for a project.
    """
    project = await get_user_project(user, project_id)
    
    if project.get("model_config"):
        config = ModelConfig(**project["model_config"])
    else:
        config = ModelConfig()  # Use defaults
    
    return ModelConfigResponse(model_config_data=config)


@router.patch("/{project_id}/model-config", response_model=ModelConfigResponse)
async def update_project_model_config(
    project_id: str,
    config: ModelConfig,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ModelConfigResponse:
    """
    Update the LLM model configuration for a project.
    
    Validates that the provider and models are valid before updating.
    """
    # Verify ownership
    await get_user_project(user, project_id)
    
    # Validate provider
    if config.provider not in AVAILABLE_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider: {config.provider}. Available: {list(AVAILABLE_PROVIDERS.keys())}"
        )
    
    provider_models = AVAILABLE_PROVIDERS[config.provider]["models"]
    
    # Validate fast model
    if config.model not in provider_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid model: {config.model}. Available for {config.provider}: {list(provider_models.keys())}"
        )
    
    # Validate reasoning model
    if config.reasoning_model not in provider_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid reasoning model: {config.reasoning_model}. Available for {config.provider}: {list(provider_models.keys())}"
        )
    
    client = get_supabase_client()
    
    result = client.table("rag_projects").update({
        "model_config": config.model_dump()
    }).eq("id", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update model configuration"
        )
    
    return ModelConfigResponse(model_config_data=config)


# =============================================================================
# Prompt Configuration Endpoints
# =============================================================================

class PromptConfigResponse(BaseModel):
    """Response for prompt configuration."""
    context_prompt: Optional[str] = None
    custom_prompts: Optional[CustomPrompts] = None
    has_custom_prompts: bool = False
    history: Optional[List[PromptHistoryEntry]] = None
    warning: Optional[str] = None


class ContextPromptUpdate(BaseModel):
    """Update just the context prompt (safe operation)."""
    context_prompt: Optional[str] = Field(None, max_length=2000)


class CustomPromptsUpdate(BaseModel):
    """Update custom prompts (dangerous - requires acknowledgment)."""
    extraction: Optional[str] = Field(None, max_length=10000)
    synthesis: Optional[str] = Field(None, max_length=10000)
    acknowledge_risk: bool = Field(
        ..., 
        description="Must be true to confirm understanding that custom prompts may break citation quality"
    )


# Default prompts for reference - these MUST match the actual prompts in src/generation/claim_ledger.py
DEFAULT_EXTRACTION_PROMPT = """You are extracting verifiable claims from a research study.

USER QUESTION: {query}

STUDY TEXT (Source [{source_id}]):
{source_text}

Extract ALL claims from this text that are relevant to answering the user's question.

For EACH claim, you MUST provide:
1. A clear, atomic factual statement
2. The EXACT quote from the text that supports it (word for word)
3. The type of claim
4. Your confidence based on how directly the quote supports the claim

Return JSON array:
[
    {{
        "claim_text": "Clear statement of the finding or fact",
        "supporting_quote": "Exact words from the text that prove this claim",
        "claim_type": "finding|methodology|context|limitation",
        "confidence": "high|medium|low"
    }}
]

CLAIM TYPES:
- finding: Results, effects, outcomes, conclusions
- methodology: Study design, sample size, methods used  
- context: Location, population, time period, intervention details
- limitation: Caveats, weaknesses, generalizability concerns

CONFIDENCE LEVELS:
- high: Quote directly states the claim
- medium: Quote strongly implies the claim
- low: Claim is inferred from context

RULES:
- Extract 3-8 claims per source (focus on most relevant)
- Supporting quotes must be EXACT text from the source (copy-paste)
- Each claim should be one clear fact (atomic)
- Focus on claims that help answer the user's question
- Include at least one finding-type claim if any findings exist

Return ONLY the JSON array, no other text."""

DEFAULT_SYNTHESIS_PROMPT = """You are writing a research synthesis answer.

USER QUESTION: {query}

I found {num_sources} studies and extracted verified claims from them.

{ledger_context}

WRITING INSTRUCTIONS:

1. **Opening**: "I found {num_sources} studies relevant to your question."

2. **Answer**: Write a comprehensive answer using ONLY claims from the ledger above.
   - Every fact you state MUST come from a verified claim in the ledger
   - Cite using the SOURCE NUMBER in brackets: [1], [2], [3], etc.
   - Do NOT use claim IDs like [1a] or [1b] - just use [1], [2], etc.
   - Include specific effect sizes and numbers from the claims
   - Be substantive (300-500 words)
   - USE THE EXACT WORDING from claims whenever possible - do not paraphrase
   - Do NOT add inferences like "this suggests" or "this indicates"

3. **Structure** (use markdown headers):
   - Key Findings (cite the finding-type claims)
   - Study Contexts (where/when/whom from context-type claims)
   - Limitations (any limitation-type claims)

4. **Citation Rules** (CRITICAL):
   - Use ONLY source numbers: [1], [2], [3] - NOT claim IDs like [1a], [1b]
   - Every statement MUST have a [N] citation
   - You may combine claims: "Studies found positive effects [1, 3]..."
   - Do NOT make claims that aren't in the ledger
   - Do NOT add a References section at the end
   - Do NOT list author names or study titles at the end
   - Do NOT add any "Note:" or "Additional evidence" sections

REMEMBER: 
- You can ONLY state facts that appear in the verified claims ledger above.
- Use [1], [2], [3] format - NOT [1a], [1b], [1c] format.
- Any uncited claim or claim not in the ledger is a failure.
- END your answer after the Limitations section - NO references or notes after that.

Write your answer:"""

# Placeholder documentation for custom prompts
EXTRACTION_PLACEHOLDERS = {
    "query": "The user's question (required)",
    "source_id": "The source number, e.g. 1, 2, 3 (required)", 
    "source_text": "The text content from the study, truncated to ~6000 chars (required)",
}

SYNTHESIS_PLACEHOLDERS = {
    "query": "The user's question (required)",
    "num_sources": "Total number of retrieved sources (required)",
    "ledger_context": "The formatted claim ledger with all extracted claims (required)",
}


@router.get("/{project_id}/prompts", response_model=PromptConfigResponse)
async def get_project_prompts(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PromptConfigResponse:
    """
    Get prompt configuration for a project, including history.
    """
    project = await get_user_project(user, project_id)
    
    custom_prompts = None
    history = None
    if project.get("custom_prompts"):
        prompts_data = project["custom_prompts"]
        # Extract history before creating CustomPrompts
        if prompts_data.get("history"):
            history = [PromptHistoryEntry(**h) for h in prompts_data["history"]]
        custom_prompts = CustomPrompts(**prompts_data)
    
    return PromptConfigResponse(
        context_prompt=project.get("context_prompt"),
        custom_prompts=custom_prompts,
        has_custom_prompts=bool(custom_prompts and (custom_prompts.extraction or custom_prompts.synthesis)),
        history=history,
        warning="Custom prompts are enabled. Citation quality may differ from defaults." if custom_prompts and (custom_prompts.extraction or custom_prompts.synthesis) else None,
    )


@router.patch("/{project_id}/prompts/context", response_model=PromptConfigResponse)
async def update_context_prompt(
    project_id: str,
    update: ContextPromptUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PromptConfigResponse:
    """
    Update the context prompt for a project.
    
    Context prompts are safe to modify - they add domain-specific instructions
    without replacing the core extraction/synthesis logic.
    
    Example: "You are a health economics expert. Focus on cost-effectiveness studies."
    """
    await get_user_project(user, project_id)
    
    client = get_supabase_client()
    
    result = client.table("rag_projects").update({
        "context_prompt": update.context_prompt
    }).eq("id", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update context prompt"
        )
    
    project = result.data[0]
    custom_prompts = CustomPrompts(**project["custom_prompts"]) if project.get("custom_prompts") else None
    
    return PromptConfigResponse(
        context_prompt=project.get("context_prompt"),
        custom_prompts=custom_prompts,
        has_custom_prompts=custom_prompts is not None,
    )


@router.patch("/{project_id}/prompts/custom", response_model=PromptConfigResponse)
async def update_custom_prompts(
    project_id: str,
    update: CustomPromptsUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PromptConfigResponse:
    """
    Update custom extraction/synthesis prompts.
    
    ⚠️ WARNING: This is an advanced feature!
    
    Modifying these prompts can significantly impact citation quality.
    The default prompts have been carefully tuned for:
    - High faithfulness (claims match sources)
    - Accurate citations (inline [N] references)
    - Proper claim extraction with supporting quotes
    
    Only modify if you understand the ALCE claim ledger pipeline.
    
    History is preserved - previous prompts are saved and can be restored.
    """
    if not update.acknowledge_risk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must acknowledge the risk by setting acknowledge_risk=true. "
                   "Custom prompts may break citation quality."
        )
    
    project = await get_user_project(user, project_id)
    
    from datetime import datetime
    
    # Get existing custom_prompts to preserve history
    existing_prompts = project.get("custom_prompts") or {}
    history = existing_prompts.get("history", [])
    
    # If there are current prompts, save them to history before overwriting
    if existing_prompts.get("extraction") or existing_prompts.get("synthesis"):
        history_entry = {
            "extraction": existing_prompts.get("extraction"),
            "synthesis": existing_prompts.get("synthesis"),
            "saved_at": existing_prompts.get("modified_at", datetime.utcnow().isoformat()),
        }
        history.insert(0, history_entry)  # Most recent first
        # Keep only last 10 versions
        history = history[:10]
    
    custom_prompts_data = {
        "extraction": update.extraction,
        "synthesis": update.synthesis,
        "modified_at": datetime.utcnow().isoformat(),
        "history": history,
    }
    
    # Remove None values (but keep history)
    custom_prompts_data = {k: v for k, v in custom_prompts_data.items() if v is not None or k == "history"}
    
    # If both are None/empty, clear custom prompts entirely (but keep history for restore)
    if not update.extraction and not update.synthesis:
        if history:
            # Keep history even when clearing current prompts
            custom_prompts_data = {"history": history, "modified_at": datetime.utcnow().isoformat()}
        else:
            custom_prompts_data = None
    
    client = get_supabase_client()
    
    result = client.table("rag_projects").update({
        "custom_prompts": custom_prompts_data
    }).eq("id", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update custom prompts"
        )
    
    project = result.data[0]
    custom_prompts = CustomPrompts(**project["custom_prompts"]) if project.get("custom_prompts") else None
    
    return PromptConfigResponse(
        context_prompt=project.get("context_prompt"),
        custom_prompts=custom_prompts,
        has_custom_prompts=custom_prompts is not None,
        warning="Custom prompts are now enabled. Monitor your citation quality closely." if custom_prompts else None,
    )


@router.delete("/{project_id}/prompts/custom", response_model=PromptConfigResponse)
async def reset_custom_prompts(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PromptConfigResponse:
    """
    Reset custom prompts to defaults.
    
    This removes any custom extraction/synthesis prompts and restores
    the default behavior optimized for citation quality.
    """
    await get_user_project(user, project_id)
    
    client = get_supabase_client()
    
    result = client.table("rag_projects").update({
        "custom_prompts": None
    }).eq("id", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset custom prompts"
        )
    
    project = result.data[0]
    
    return PromptConfigResponse(
        context_prompt=project.get("context_prompt"),
        custom_prompts=None,
        has_custom_prompts=False,
        warning=None,
    )


@router.get("/prompts/defaults")
async def get_default_prompts():
    """
    Get the default extraction and synthesis prompts for reference.
    
    Use these as a starting point if you want to create custom prompts.
    IMPORTANT: Your custom prompts MUST include ALL the required placeholders
    or the system will fail when processing queries.
    """
    return {
        "extraction": {
            "prompt": DEFAULT_EXTRACTION_PROMPT,
            "placeholders": EXTRACTION_PLACEHOLDERS,
            "instructions": (
                "Your custom extraction prompt MUST include these placeholders: "
                "{query}, {source_id}, {source_text}. "
                "The prompt should instruct the LLM to return a JSON array of claims."
            ),
        },
        "synthesis": {
            "prompt": DEFAULT_SYNTHESIS_PROMPT,
            "placeholders": SYNTHESIS_PLACEHOLDERS,
            "instructions": (
                "Your custom synthesis prompt MUST include these placeholders: "
                "{query}, {num_sources}, {ledger_context}. "
                "The prompt should instruct the LLM to cite sources using [1], [2], etc."
            ),
        },
        "warning": (
            "⚠️ Modifying these prompts may significantly impact citation quality. "
            "The defaults have been tuned for high faithfulness and accurate citations. "
            "Missing placeholders will cause errors."
        ),
    }


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rag_project(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete a RAG project.
    
    This will:
    1. Delete the Qdrant collection
    2. Delete all associated documents from R2
    3. Delete the database record
    """
    project = await get_user_project(user, project_id)
    collection_name = project["qdrant_collection"]
    
    client = get_supabase_client()
    
    # Delete Qdrant collection
    try:
        indexer = QdrantIndexer(
            collection_name=collection_name,
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        await indexer.delete_collection()
        logger.info(f"Deleted Qdrant collection: {collection_name}")
    except Exception as e:
        logger.warning(f"Failed to delete Qdrant collection {collection_name}: {e}")
        # Continue anyway - collection might not exist
    
    # Delete R2 files for this project
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        prefix = f"rags/{project_id}/"
        paginator = r2_client.get_paginator("list_objects_v2")
        
        deleted_count = 0
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                try:
                    r2_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                    deleted_count += 1
                except Exception:
                    pass
        logger.info(f"Deleted {deleted_count} R2 files for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to delete R2 files for {project_id}: {e}")
        # Continue anyway
    
    # Delete database record (cascade will delete documents and jobs)
    client.table("rag_projects").delete().eq("id", project_id).execute()
    
    logger.info(f"Deleted RAG project: {project_id}")


# =============================================================================
# Public Endpoints (No Auth Required)
# =============================================================================

class PublicRAGResponse(BaseModel):
    """Public-facing RAG info (limited fields)."""
    id: str
    name: str
    description: Optional[str]
    qdrant_collection: str
    is_public: bool


@router.get("/{project_id}/public", response_model=PublicRAGResponse)
async def get_public_rag_project(project_id: str) -> PublicRAGResponse:
    """
    Get public info for a RAG project.
    
    No authentication required, but only works for public projects.
    Accepts either project ID or slug.
    """
    if not is_multi_tenant_enabled():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Multi-tenant mode not enabled"
        )
    
    client = get_supabase_client()
    
    # Check if project_id looks like a UUID
    import re
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    is_uuid = bool(uuid_pattern.match(project_id))
    
    result = None
    if is_uuid:
        # Try to find by ID first
        result = client.table("rag_projects").select("*").eq("id", project_id).execute()
    
    if not result or not result.data:
        # Try by slug
        result = client.table("rag_projects").select("*").eq("slug", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG not found"
        )
    
    project = result.data[0]
    
    if not project.get("is_public", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This RAG is private"
        )
    
    return PublicRAGResponse(
        id=str(project["id"]),
        name=project["name"],
        description=project.get("description"),
        qdrant_collection=project["qdrant_collection"],
        is_public=True,
    )


# =============================================================================
# Per-RAG Document Endpoints
# =============================================================================

class DocumentResponse(BaseModel):
    """Response for a document."""
    id: str
    filename: str
    original_filename: str
    title: Optional[str] = None
    authors: List[str] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    status: str
    error_message: Optional[str]
    chunk_count: int
    created_at: datetime
    processed_at: Optional[datetime]


class DocumentStats(BaseModel):
    """Summary stats for documents (unfiltered totals)."""
    total_documents: int
    completed: int
    pending: int
    processing: int
    failed: int
    total_chunks: int


class DocumentListResponse(BaseModel):
    """Response for listing documents."""
    documents: List[DocumentResponse]
    total_count: int
    page: int
    limit: int
    pages: int
    stats: Optional[DocumentStats] = None


@router.get("/{project_id}/documents", response_model=DocumentListResponse)
async def list_project_documents(
    project_id: str,
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    needs_review: Optional[bool] = None,
    search: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentListResponse:
    """List all documents in a RAG project with pagination and filtering."""
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Build query
    query = client.table("documents").select("*", count="exact").eq("rag_project_id", project_id)
    
    if status:
        query = query.eq("status", status)
    
    if needs_review is not None:
        # needs_review is stored in metadata jsonb column
        # Supabase/PostgREST syntax for JSON filtering: metadata->>needs_review
        # But the python client might need a specific filter syntax
        # For now, let's filter in python if we can't do it easily in SQL, 
        # OR use the .contains() filter for JSONB
        if needs_review:
            query = query.contains("metadata", {"needs_review": True})
        else:
            # This is harder because it could be False or missing
            # For "not needs review", we might just fetch all and filter in memory if the dataset is small
            # But for pagination we need SQL filtering.
            # Let's try to use the arrow operator if supported, or just filter by status for now
            pass

    if search:
        # Simple search on filename or original_filename
        query = query.or_(f"filename.ilike.%{search}%,original_filename.ilike.%{search}%")

    # Apply pagination
    start = (page - 1) * limit
    end = start + limit - 1
    
    result = query.order("created_at", desc=True).range(start, end).execute()
    
    documents = []
    for d in result.data or []:
        # Extract metadata from JSONB field
        metadata = d.get("metadata", {}) or {}
        
        # Handle authors - ensure it's always a list
        authors = metadata.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        elif not isinstance(authors, list):
            authors = []
        
        # Filter by needs_review if requested (and not handled by SQL)
        if needs_review is not None:
            doc_needs_review = metadata.get("needs_review", False)
            if needs_review != doc_needs_review:
                continue

        documents.append(DocumentResponse(
            id=str(d["id"]),
            filename=d["filename"],
            original_filename=d["original_filename"],
            title=metadata.get("title"),
            authors=authors,
            year=metadata.get("year"),
            doi=metadata.get("doi"),
            status=d["status"],
            error_message=d.get("error_message"),
            chunk_count=d.get("chunk_count", 0),
            created_at=d["created_at"],
            processed_at=d.get("processed_at"),
        ))
    
    # Get summary stats (unfiltered totals for this project)
    stats_query = client.table("documents").select(
        "status, chunk_count"
    ).eq("rag_project_id", project_id).execute()
    
    stats_data = stats_query.data or []
    stats = DocumentStats(
        total_documents=len(stats_data),
        completed=sum(1 for d in stats_data if d.get("status") == "completed"),
        pending=sum(1 for d in stats_data if d.get("status") == "pending"),
        processing=sum(1 for d in stats_data if d.get("status") == "processing"),
        failed=sum(1 for d in stats_data if d.get("status") == "failed"),
        total_chunks=sum(d.get("chunk_count", 0) or 0 for d in stats_data),
    )
    
    return DocumentListResponse(
        documents=documents, 
        total_count=result.count or 0,
        page=page,
        limit=limit,
        pages=(result.count + limit - 1) // limit if result.count else 0,
        stats=stats,
    )


class SyncResponse(BaseModel):
    """Response for syncing R2 with Supabase."""
    synced: int
    already_exists: int
    errors: int
    message: str


@router.post("/{project_id}/documents/sync", response_model=SyncResponse)
async def sync_project_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> SyncResponse:
    """
    Sync R2 files with Supabase documents table.
    
    Finds files in R2 that don't have corresponding Supabase records and creates them.
    This handles orphaned uploads where R2 succeeded but Supabase failed.
    """
    project = await get_user_project(user, project_id)
    
    r2_client = get_r2_client()
    bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
    client = get_supabase_client()
    
    # Get existing documents from Supabase
    result = client.table("documents").select("filename").eq("rag_project_id", project_id).execute()
    existing_filenames = set(d["filename"] for d in result.data or [])
    
    # Get files from R2
    prefix = f"rags/{project_id}/input-pdfs/"
    paginator = r2_client.get_paginator("list_objects_v2")
    
    synced = 0
    already_exists = 0
    errors = 0
    
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.replace(prefix, "")
            doc_id = os.path.splitext(filename)[0]
            
            if doc_id in existing_filenames:
                already_exists += 1
                continue
            
            # Extract original filename from doc_id (format: hash_originalname)
            parts = doc_id.split("_", 1)
            if len(parts) > 1:
                original_name = parts[1] + ".pdf"
                content_hash = parts[0]
            else:
                original_name = filename
                content_hash = ""
            
            try:
                client.table("documents").insert({
                    "rag_project_id": project_id,
                    "filename": doc_id,
                    "original_filename": original_name,
                    "file_size_bytes": obj.get("Size", 0),
                    "mime_type": "application/pdf",
                    "status": "pending",
                    "r2_input_key": key,
                    "metadata": {"content_hash": content_hash} if content_hash else {},
                }).execute()
                synced += 1
                logger.info(f"Synced orphaned R2 file to Supabase: {doc_id}")
            except Exception as e:
                errors += 1
                logger.error(f"Failed to sync {doc_id}: {e}")
    
    return SyncResponse(
        synced=synced,
        already_exists=already_exists,
        errors=errors,
        message=f"Synced {synced} orphaned files, {already_exists} already existed, {errors} errors",
    )


# =============================================================================
# Document Upload Helpers
# =============================================================================

def compute_content_hash(content: bytes) -> str:
    """Compute SHA-256 hash of content, truncated for use in filenames."""
    return hashlib.sha256(content).hexdigest()[:12]


def find_existing_document_for_project(r2_client, bucket_name: str, project_id: str, content_hash: str, base_name: str) -> dict | None:
    """Check if a document with the same content hash already exists in the project's R2 folder."""
    prefix = f"rags/{project_id}/input-pdfs/"
    try:
        response = r2_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        for obj in response.get("Contents", []):
            key = obj["Key"]
            # Doc ID is the filename without .pdf
            filename = key.replace(prefix, "")
            if filename.startswith(f"{content_hash}_"):
                doc_id = os.path.splitext(filename)[0]
                return {
                    "key": key,
                    "doc_id": doc_id,
                    "size": obj["Size"],
                }
    except Exception as e:
        logger.warning(f"Error checking for duplicates: {e}")
    return None


class UploadResponse(BaseModel):
    """Response for file upload."""
    success: bool
    filename: str
    r2_key: Optional[str] = None
    size_bytes: Optional[int] = None
    queued_for_processing: bool = False
    doc_id: Optional[str] = None
    message: Optional[str] = None
    is_duplicate: bool = False


@router.post("/{project_id}/documents/upload", response_model=UploadResponse)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    force_upload: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
) -> UploadResponse:
    """
    Upload a PDF document to a RAG project.
    
    Uses content-based deduplication: files with identical content won't be uploaded twice.
    Set force_upload=true to bypass duplicate detection.
    """
    project = await get_user_project(user, project_id)
    
    # Validate file type (only PDFs supported)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext != ".pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF files are supported. Got: {file_ext}"
        )
    
    try:
        # Read file content for deduplication
        content = await file.read()
        size_bytes = len(content)
        
        # Compute content hash for deduplication
        content_hash = compute_content_hash(content)
        
        safe_filename = file.filename.replace(" ", "_").replace("/", "_")
        base_name = os.path.splitext(safe_filename)[0]
        
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Check for existing document with same content
        if not force_upload:
            existing = find_existing_document_for_project(r2_client, bucket_name, project_id, content_hash, base_name)
            if existing:
                logger.info(f"Duplicate detected: {file.filename} matches existing {existing['doc_id']} in project {project_id}")
                return UploadResponse(
                    success=True,
                    filename=file.filename,
                    r2_key=existing["key"],
                    size_bytes=existing["size"],
                    queued_for_processing=False,
                    doc_id=existing["doc_id"],
                    message=f"Document already exists as {existing['doc_id']}. No duplicate created.",
                    is_duplicate=True,
                )
        
        # Generate doc_id using content hash
        doc_id = f"{content_hash}_{base_name}"
        r2_key = f"rags/{project_id}/input-pdfs/{doc_id}{file_ext}"
        
        # Upload to R2
        r2_client.put_object(
            Bucket=bucket_name,
            Key=r2_key,
            Body=content,
            ContentType=file.content_type or "application/pdf",
            Metadata={
                "doc_id": doc_id,
                "content_hash": content_hash,
                "original_filename": file.filename,
                "upload_timestamp": datetime.utcnow().isoformat(),
                "project_id": project_id,
            }
        )
        
        logger.info(f"Uploaded {file.filename} to R2 as {r2_key} (doc_id={doc_id}, project={project_id}, {size_bytes} bytes)")
        
        # Create document record in database (atomic with R2 - rollback on failure)
        try:
            client = get_supabase_client()
            client.table("documents").upsert({
                "rag_project_id": project_id,
                "filename": doc_id,
                "original_filename": file.filename,
                "file_size_bytes": size_bytes,
                "mime_type": file.content_type or "application/pdf",
                "status": "pending",
                "r2_input_key": r2_key,
                "metadata": {"content_hash": content_hash},
            }, on_conflict="filename,rag_project_id").execute()
        except Exception as db_error:
            # Rollback: delete from R2 if Supabase insert fails
            logger.error(f"Supabase insert failed, rolling back R2 upload: {db_error}")
            try:
                r2_client.delete_object(Bucket=bucket_name, Key=r2_key)
                logger.info(f"Rolled back R2 upload: {r2_key}")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback R2 upload: {rollback_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save document record: {str(db_error)}"
            )
        
        return UploadResponse(
            success=True,
            filename=file.filename,
            r2_key=r2_key,
            size_bytes=size_bytes,
            queued_for_processing=True,
            doc_id=doc_id,
        )
        
    except ClientError as e:
        logger.error(f"R2 upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload to R2: {str(e)}")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# =============================================================================
# Bibliography Import - Match RIS/BibTeX/CSV to Documents
# =============================================================================

class BibliographyMatchResult(BaseModel):
    """Result of matching a single bibliography entry."""
    entry_id: str
    entry_title: str
    entry_authors: Optional[str]
    entry_year: Optional[int]
    document_id: Optional[str] = None
    document_filename: Optional[str] = None
    confidence: float
    match_method: str
    match_details: str


class BibliographyImportResponse(BaseModel):
    """Response for bibliography import."""
    total_entries: int
    matched: List[BibliographyMatchResult]
    unmatched: List[BibliographyMatchResult]
    auto_applied: int = 0
    message: str


@router.post("/{project_id}/documents/import-bibliography", response_model=BibliographyImportResponse)
async def import_bibliography(
    project_id: str,
    file: UploadFile = File(...),
    auto_apply: bool = False,
    min_confidence: float = 0.8,
    user: AuthenticatedUser = Depends(get_current_user),
) -> BibliographyImportResponse:
    """
    Import bibliography from RIS, BibTeX, or CSV file and match to existing documents.
    
    The system will try to match each entry to existing documents using:
    1. DOI matching (most reliable)
    2. Title similarity (>85%)
    3. Author+Year combination
    4. Filename pattern (author_year.pdf)
    
    Args:
        file: RIS, BibTeX, or CSV file
        auto_apply: If True, automatically apply metadata from matched entries
        min_confidence: Minimum confidence threshold for auto_apply (0.0-1.0)
    
    Returns:
        List of matched and unmatched entries for review
    """
    from src.ingestion.bibliography_parser import parse_bibliography
    from src.ingestion.bibliography_matcher import match_entries, BibliographyEntry
    
    project = await get_user_project(user, project_id)
    
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    allowed_extensions = ['.ris', '.bib', '.csv', '.txt']
    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    try:
        # Read and parse file
        content = await file.read()
        content_str = content.decode('utf-8', errors='ignore')
        
        entries = parse_bibliography(content_str, file.filename)
        
        if not entries:
            return BibliographyImportResponse(
                total_entries=0,
                matched=[],
                unmatched=[],
                message="No bibliography entries found in file"
            )
        
        # Get existing documents for this project
        client = get_supabase_client()
        docs_result = client.table("documents").select(
            "id, filename, original_filename, metadata"
        ).eq("rag_project_id", project_id).execute()
        
        documents = docs_result.data or []
        
        # Match entries to documents
        matched_results, unmatched_results = match_entries(entries, documents)
        
        # Format results for response
        def format_result(result) -> BibliographyMatchResult:
            doc_filename = None
            if result.document_id:
                doc = next((d for d in documents if d['id'] == result.document_id), None)
                if doc:
                    doc_filename = doc.get('original_filename') or doc.get('filename')
            
            return BibliographyMatchResult(
                entry_id=result.entry.id,
                entry_title=result.entry.title,
                entry_authors=", ".join(result.entry.authors) if result.entry.authors else None,
                entry_year=result.entry.year,
                document_id=result.document_id,
                document_filename=doc_filename,
                confidence=result.confidence,
                match_method=result.method.value,
                match_details=result.match_details,
            )
        
        matched = [format_result(r) for r in matched_results]
        unmatched = [format_result(r) for r in unmatched_results]
        
        # Auto-apply metadata if requested
        auto_applied = 0
        if auto_apply:
            for result in matched_results:
                if result.confidence >= min_confidence and result.document_id:
                    entry = result.entry
                    # Build metadata update from entry
                    metadata_update = {}
                    if entry.title:
                        metadata_update['title'] = entry.title
                    if entry.authors:
                        metadata_update['authors'] = ", ".join(entry.authors)
                    if entry.year:
                        metadata_update['year'] = entry.year
                    if entry.doi:
                        metadata_update['doi'] = entry.doi
                    if entry.journal:
                        metadata_update['journal'] = entry.journal
                    if entry.abstract:
                        metadata_update['abstract'] = entry.abstract
                    
                    metadata_update['metadata_source'] = f'bibliography_{entry.source_format}'
                    
                    try:
                        # Get existing metadata and merge
                        doc = next((d for d in documents if d['id'] == result.document_id), None)
                        existing_meta = doc.get('metadata', {}) if doc else {}
                        merged_meta = {**existing_meta, **metadata_update}
                        
                        client.table("documents").update({
                            "metadata": merged_meta,
                            "import_source": entry.source_format,
                            "match_confidence": result.confidence,
                            "external_id": entry.doi or entry.id,
                        }).eq("id", result.document_id).execute()
                        
                        auto_applied += 1
                    except Exception as e:
                        logger.warning(f"Failed to apply metadata to {result.document_id}: {e}")
        
        return BibliographyImportResponse(
            total_entries=len(entries),
            matched=matched,
            unmatched=unmatched,
            auto_applied=auto_applied,
            message=f"Found {len(matched)} matches, {len(unmatched)} unmatched"
            + (f", applied {auto_applied} metadata updates" if auto_applied else "")
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Bibliography import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


class ApplyMatchRequest(BaseModel):
    """Request to apply a manual match."""
    entry_data: dict  # The bibliography entry data
    document_id: str  # Document to apply metadata to


class ApplyMatchResponse(BaseModel):
    """Response for applying a match."""
    success: bool
    message: str


@router.post("/{project_id}/documents/apply-match", response_model=ApplyMatchResponse)
async def apply_bibliography_match(
    project_id: str,
    request: ApplyMatchRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ApplyMatchResponse:
    """
    Apply metadata from a bibliography entry to a document (manual matching).
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Verify document belongs to project
    doc_result = client.table("documents").select("id, metadata").eq(
        "id", request.document_id
    ).eq("rag_project_id", project_id).single().execute()
    
    if not doc_result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    existing_meta = doc_result.data.get('metadata', {})
    entry = request.entry_data
    
    # Build metadata from entry
    metadata_update = {}
    if entry.get('title'):
        metadata_update['title'] = entry['title']
    if entry.get('authors'):
        metadata_update['authors'] = entry['authors'] if isinstance(entry['authors'], str) else ", ".join(entry['authors'])
    if entry.get('year'):
        metadata_update['year'] = entry['year']
    if entry.get('doi'):
        metadata_update['doi'] = entry['doi']
    if entry.get('journal'):
        metadata_update['journal'] = entry['journal']
    if entry.get('abstract'):
        metadata_update['abstract'] = entry['abstract']
    
    metadata_update['metadata_source'] = 'bibliography_manual'
    
    merged_meta = {**existing_meta, **metadata_update}
    
    try:
        client.table("documents").update({
            "metadata": merged_meta,
            "import_source": "manual",
            "match_confidence": 1.0,
            "external_id": entry.get('doi') or entry.get('id'),
        }).eq("id", request.document_id).execute()
        
        return ApplyMatchResponse(
            success=True,
            message=f"Applied metadata to document"
        )
    except Exception as e:
        logger.error(f"Failed to apply match: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class JobResponse(BaseModel):
    """Response for a processing job."""
    id: str
    job_type: str
    status: str
    progress: int
    message: Optional[str]
    error_message: Optional[str] = None
    created_at: datetime


class JobListResponse(BaseModel):
    """Response for listing jobs."""
    jobs: List[JobResponse]


@router.get("/{project_id}/jobs", response_model=JobListResponse)
async def list_project_jobs(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> JobListResponse:
    """List processing jobs for a RAG project."""
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    result = client.table("processing_jobs").select("*").eq("rag_project_id", project_id).order("created_at", desc=True).limit(50).execute()
    
    jobs = [
        JobResponse(
            id=str(j["id"]),
            job_type=j["job_type"],
            status=j["status"],
            progress=j.get("progress", 0),
            message=j.get("message"),
            error_message=j.get("error_message"),
            created_at=j["created_at"],
        )
        for j in result.data or []
    ]
    
    return JobListResponse(jobs=jobs)


# =============================================================================
# Processing Trigger - Modal Integration
# =============================================================================

class ProcessResponse(BaseModel):
    """Response for processing trigger."""
    message: str
    queued: int
    skipped: int
    function_id: Optional[str] = None


@router.post("/{project_id}/process", response_model=ProcessResponse)
async def trigger_processing(
    project_id: str,
    force: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessResponse:
    """
    Trigger Modal processing for all unprocessed documents in this RAG project.
    
    This calls Modal's orchestrate_rag function which:
    1. Finds all PDFs in rags/{project_id}/input-pdfs/
    2. Processes each with MinerU (text extraction)
    3. Enriches metadata from CrossRef/OpenAlex
    4. Embeds chunks to Qdrant (project-specific collection)
    5. Syncs metadata back to Supabase documents table
    
    Args:
        project_id: The RAG project ID
        force: If True, reprocess all documents (even already processed ones)
    """
    import httpx
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get documents that need processing (status != 'completed')
    if force:
        docs_result = client.table("documents").select("id, original_filename, status").eq("rag_project_id", project_id).execute()
    else:
        docs_result = client.table("documents").select("id, original_filename, status").eq("rag_project_id", project_id).neq("status", "completed").execute()
    
    pending_docs = docs_result.data or []
    
    if not pending_docs:
        return ProcessResponse(
            message="No documents to process",
            queued=0,
            skipped=0,
        )
    
    # Update status to 'processing' for all pending docs
    doc_ids = [d["id"] for d in pending_docs]
    client.table("documents").update({
        "status": "processing",
        "updated_at": datetime.utcnow().isoformat(),
    }).in_("id", doc_ids).execute()
    
    # Trigger Modal function
    # Modal needs to know:
    # 1. The R2 prefix to scan: rags/{project_id}/input-pdfs/
    # 2. The Qdrant collection: rag_{project_id}
    # 3. The project_id for syncing back to Supabase
    
    modal_webhook_url = os.environ.get("MODAL_WEBHOOK_URL")
    
    if modal_webhook_url:
        # Call Modal webhook to trigger processing
        # The webhook expects: { "project_id": "uuid", "force_reprocess": bool, "max_documents": int }
        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                response = await http_client.post(
                    modal_webhook_url,
                    json={
                        "project_id": project_id,
                        "force_reprocess": force,
                        "max_documents": 0,  # 0 = unlimited
                    },
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Modal triggered for project {project_id}: {result}")
                    
                    # Webhook returns: { success, project_id, processed, failed, skipped, total, message }
                    if result.get("success"):
                        return ProcessResponse(
                            message=result.get("message", f"Processing {len(pending_docs)} documents"),
                            queued=result.get("total", len(pending_docs)),
                            skipped=result.get("skipped", 0),
                        )
                    else:
                        logger.error(f"Modal webhook returned error: {result.get('error')}")
                        # Fall through to manual processing message
                else:
                    logger.error(f"Modal webhook failed: {response.status_code} - {response.text}")
                    # Fall through to manual processing message
                    
        except Exception as e:
            logger.error(f"Modal webhook error: {e}")
            # Fall through to manual processing message
    
    # If no Modal webhook or it failed, return instructions for manual trigger
    r2_prefix = f"rags/{project_id}/input-pdfs/"
    qdrant_collection = project.qdrant_collection
    
    return ProcessResponse(
        message=f"Documents marked as queued. Run Modal manually: modal run infrastructure/modal_mineru.py::orchestrate_rag --project-id {project_id}",
        queued=len(pending_docs),
        skipped=0,
    )


@router.delete("/{project_id}/locks")
async def clear_project_locks(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Clear processing locks for stuck documents.
    Resets any documents stuck in 'processing' status back to 'pending'.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Find stuck documents
    stuck_result = client.table("documents").select("id").eq("rag_project_id", project_id).eq("status", "processing").execute()
    stuck_count = len(stuck_result.data or [])
    
    if stuck_count > 0:
        # Reset to pending
        client.table("documents").update({
            "status": "pending",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("rag_project_id", project_id).eq("status", "processing").execute()
    
    return {"message": f"Cleared {stuck_count} stuck documents", "cleared": stuck_count}


@router.post("/{project_id}/retry-failed")
async def retry_failed_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retry processing failed documents.
    Resets their status to 'pending' and triggers reprocessing.
    """
    import httpx
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Find failed documents
    failed_result = client.table("documents").select("id, original_filename").eq("rag_project_id", project_id).eq("status", "failed").execute()
    failed_count = len(failed_result.data or [])
    
    if failed_count == 0:
        return {"message": "No failed documents to retry", "retried": 0}
    
    # Reset to pending
    doc_ids = [d["id"] for d in failed_result.data]
    client.table("documents").update({
        "status": "pending",
        "error_message": None,
        "updated_at": datetime.utcnow().isoformat(),
    }).in_("id", doc_ids).execute()
    
    # Trigger Modal processing
    modal_webhook_url = os.environ.get("MODAL_WEBHOOK_URL")
    
    if modal_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                response = await http_client.post(
                    modal_webhook_url,
                    json={
                        "project_id": project_id,
                        "force_reprocess": False,
                        "max_documents": 0,
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Modal triggered for retry: {result}")
        except Exception as e:
            logger.error(f"Modal webhook error on retry: {e}")
    
    return {"message": f"Retrying {failed_count} failed documents", "retried": failed_count}


# =============================================================================
# Per-RAG Metadata Endpoints (Zotero-Compatible)
# =============================================================================

class MetadataDetail(BaseModel):
    """Full Zotero-compatible metadata for a document."""
    id: str
    title: str
    filename: str
    authors: List[str] = []
    year: Optional[int] = None
    abstract: Optional[str] = None
    
    # Zotero item type
    item_type: Optional[str] = None
    
    # Identifiers
    doi: Optional[str] = None
    isbn: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None
    
    # Publication info
    publication: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    edition: Optional[str] = None
    
    # Publisher info
    publisher: Optional[str] = None
    place: Optional[str] = None
    
    # Series
    series: Optional[str] = None
    series_number: Optional[str] = None
    
    # Book/Book Section
    book_title: Optional[str] = None
    num_pages: Optional[int] = None
    
    # Report/Working Paper
    institution: Optional[str] = None
    report_number: Optional[str] = None
    report_type: Optional[str] = None
    
    # Thesis
    thesis_type: Optional[str] = None
    
    # Conference
    conference_name: Optional[str] = None
    proceedings_title: Optional[str] = None
    
    # Access
    accessed_date: Optional[str] = None
    
    # 3ie Classification
    countries: List[str] = []
    sectors: List[str] = []
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    
    # Processing metadata
    metadata_source: Optional[str] = "extraction"
    metadata_confidence: float = 0.0
    needs_review: bool = True
    chunk_count: int = 0
    
    # Flags for issues
    needs_reprocessing: bool = False  # True if chunk_count=0 but status=completed


class MetadataListResponse(BaseModel):
    """Response for listing documents with metadata."""
    documents: List[MetadataDetail]
    total_count: int
    needs_review_count: int
    page: int
    limit: int


class MetadataUpdateRequest(BaseModel):
    """Request to update document metadata - Zotero compatible."""
    # Core
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    item_type: Optional[str] = None
    
    # Identifiers
    doi: Optional[str] = None
    isbn: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None
    
    # Publication info
    publication: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    edition: Optional[str] = None
    
    # Publisher info
    publisher: Optional[str] = None
    place: Optional[str] = None
    
    # Series
    series: Optional[str] = None
    series_number: Optional[str] = None
    
    # Book/Book Section
    book_title: Optional[str] = None
    num_pages: Optional[str] = None
    
    # Report/Working Paper
    institution: Optional[str] = None
    report_number: Optional[str] = None
    report_type: Optional[str] = None
    
    # Thesis
    thesis_type: Optional[str] = None
    
    # Conference
    conference_name: Optional[str] = None
    proceedings_title: Optional[str] = None
    
    # Access
    accessed_date: Optional[str] = None
    
    # 3ie Classification
    countries: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    
    # Review status
    needs_review: Optional[bool] = None


@router.get("/{project_id}/metadata", response_model=MetadataListResponse)
async def list_project_metadata(
    project_id: str,
    filter_type: Optional[str] = None,  # "needs_review" or "all"
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataListResponse:
    """
    List all documents with full metadata for a RAG project.
    Zotero-compatible fields.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get unfiltered total count first
    total_query = client.table("documents").select("*", count="exact", head=True).eq("rag_project_id", project_id)
    total_res = total_query.execute()
    unfiltered_total = total_res.count or 0
    
    # Base query with potential filters
    query = client.table("documents").select("*", count="exact").eq("rag_project_id", project_id)
    
    # Apply filters
    if filter_type == "needs_review":
        # Filter where needs_review is NOT false (so True or Null)
        query = query.neq("metadata->>needs_review", "false")
        
    # Search
    if search:
        # Search in filename OR title
        query = query.or_(f"original_filename.ilike.%{search}%,metadata->>title.ilike.%{search}%")

    # Pagination
    start = (page - 1) * limit
    end = start + limit - 1
    
    result = query.order("created_at", desc=True).range(start, end).execute()
    
    # Get total needs_review count separately if we are not already filtering for it
    if filter_type == "needs_review" and not search:
        needs_review_count = result.count
    else:
        # Separate query for count
        count_query = client.table("documents").select("*", count="exact", head=True).eq("rag_project_id", project_id).neq("metadata->>needs_review", "false")
        count_res = count_query.execute()
        needs_review_count = count_res.count or 0

    documents = []
    
    for d in result.data or []:
        metadata = d.get("metadata", {}) or {}
        
        # Parse authors - could be string or list
        authors_raw = metadata.get("authors", [])
        if isinstance(authors_raw, str):
            authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
        elif isinstance(authors_raw, list):
            authors = authors_raw
        else:
            authors = []
        
        needs_review = metadata.get("needs_review", True)
        
        documents.append(MetadataDetail(
            id=str(d["id"]),
            title=metadata.get("title") or d.get("original_filename", "Unknown"),
            filename=d["original_filename"],
            authors=authors,
            year=metadata.get("year"),
            abstract=metadata.get("abstract"),
            item_type=metadata.get("item_type"),
            doi=metadata.get("doi"),
            isbn=metadata.get("isbn"),
            issn=metadata.get("issn"),
            url=metadata.get("url"),
            publication=metadata.get("publication"),
            journal=metadata.get("journal"),
            volume=metadata.get("volume"),
            issue=metadata.get("issue"),
            pages=metadata.get("pages"),
            edition=metadata.get("edition"),
            publisher=metadata.get("publisher"),
            place=metadata.get("place"),
            series=metadata.get("series"),
            series_number=metadata.get("series_number"),
            book_title=metadata.get("book_title"),
            num_pages=metadata.get("num_pages"),
            institution=metadata.get("institution"),
            report_number=metadata.get("report_number"),
            report_type=metadata.get("report_type"),
            thesis_type=metadata.get("thesis_type"),
            conference_name=metadata.get("conference_name"),
            proceedings_title=metadata.get("proceedings_title"),
            accessed_date=metadata.get("accessed_date"),
            countries=metadata.get("countries", []),
            sectors=metadata.get("sectors", []),
            study_type=metadata.get("study_type"),
            intervention_type=metadata.get("intervention_type"),
            metadata_source=metadata.get("metadata_source", "extraction"),
            metadata_confidence=metadata.get("metadata_confidence", 0.0),
            needs_review=needs_review,
            chunk_count=d.get("chunk_count", 0),
            needs_reprocessing=d.get("chunk_count", 0) == 0 and d.get("status") == "completed",
        ))
    
    return MetadataListResponse(
        documents=documents,
        total_count=unfiltered_total,  # Always return unfiltered total for stats cards
        needs_review_count=needs_review_count,
        page=page,
        limit=limit
    )


@router.get("/{project_id}/metadata/{doc_id}")
async def get_document_metadata(
    project_id: str,
    doc_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataDetail:
    """Get full metadata for a single document."""
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    d = result.data
    metadata = d.get("metadata", {}) or {}
    
    authors_raw = metadata.get("authors", [])
    if isinstance(authors_raw, str):
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
    elif isinstance(authors_raw, list):
        authors = authors_raw
    else:
        authors = []
    
    return MetadataDetail(
        id=str(d["id"]),
        title=metadata.get("title") or d.get("original_filename", "Unknown"),
        filename=d["original_filename"],
        authors=authors,
        year=metadata.get("year"),
        abstract=metadata.get("abstract"),
        item_type=metadata.get("item_type"),
        doi=metadata.get("doi"),
        isbn=metadata.get("isbn"),
        issn=metadata.get("issn"),
        url=metadata.get("url"),
        publication=metadata.get("publication"),
        journal=metadata.get("journal"),
        volume=metadata.get("volume"),
        issue=metadata.get("issue"),
        pages=metadata.get("pages"),
        publisher=metadata.get("publisher"),
        place=metadata.get("place"),
        countries=metadata.get("countries", []),
        sectors=metadata.get("sectors", []),
        study_type=metadata.get("study_type"),
        intervention_type=metadata.get("intervention_type"),
        metadata_source=metadata.get("metadata_source", "extraction"),
        metadata_confidence=metadata.get("metadata_confidence", 0.0),
        needs_review=metadata.get("needs_review", True),
        chunk_count=d.get("chunk_count", 0),
        needs_reprocessing=d.get("chunk_count", 0) == 0 and d.get("status") == "completed",
    )


@router.patch("/{project_id}/metadata/{doc_id}")
async def update_document_metadata(
    project_id: str,
    doc_id: str,
    update: MetadataUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataDetail:
    """
    Update metadata for a document.
    Also syncs the metadata to Qdrant vectors for search.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get current document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    current_metadata = result.data.get("metadata", {}) or {}
    
    # Merge updates into metadata
    update_dict = update.model_dump(exclude_none=True)
    new_metadata = {**current_metadata, **update_dict}
    
    # Mark as user-verified
    new_metadata["metadata_source"] = "user"
    new_metadata["metadata_confidence"] = 1.0
    if "needs_review" not in update_dict:
        new_metadata["needs_review"] = False
    
    # Update in Supabase
    client.table("documents").update({
        "metadata": new_metadata,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", doc_id).execute()
    
    # Sync to Qdrant vectors
    try:
        indexer = QdrantIndexer(collection_name=project["qdrant_collection"])
        
        # Build Qdrant payload update
        qdrant_update = {}
        if update.title:
            qdrant_update["title"] = update.title
        if update.authors:
            qdrant_update["authors"] = ", ".join(update.authors)
        if update.year:
            qdrant_update["year"] = update.year
        if update.doi:
            qdrant_update["doi"] = update.doi
        if update.countries:
            qdrant_update["country"] = update.countries[0] if update.countries else None
            qdrant_update["countries"] = update.countries
        if update.sectors:
            qdrant_update["sector"] = update.sectors[0] if update.sectors else None
            qdrant_update["sectors"] = update.sectors
        if update.study_type:
            qdrant_update["study_type"] = update.study_type
        
        if qdrant_update:
            # Update all vectors for this document
            indexer.client.set_payload(
                collection_name=project["qdrant_collection"],
                payload=qdrant_update,
                points=indexer.client.scroll(
                    collection_name=project["qdrant_collection"],
                    scroll_filter={
                        "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                    },
                    limit=1000,
                    with_payload=False,
                )[0],
            )
            logger.info(f"Synced metadata to Qdrant for doc {doc_id}")
    except Exception as e:
        logger.warning(f"Failed to sync metadata to Qdrant: {e}")
    
    # Return updated metadata
    return await get_document_metadata(project_id, doc_id, user)


@router.post("/{project_id}/metadata/{doc_id}/enrich")
async def enrich_document_metadata(
    project_id: str,
    doc_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataDetail:
    """
    Enrich document metadata from CrossRef/OpenAlex.
    
    If DOI is present, uses DOI lookup.
    If no DOI, tries to extract DOI from filename or search by title.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get current document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    current_metadata = result.data.get("metadata", {}) or {}
    doi = current_metadata.get("doi")
    original_filename = result.data.get("original_filename", "")
    
    # Try to extract DOI from filename if not present
    # Pattern: files often contain DOI-like strings like "10.xxxx_xxxxx" 
    if not doi:
        import re
        # Look for DOI pattern in filename
        doi_match = re.search(r'10\.\d{4,}/[^\s]+', original_filename.replace('_', '/'))
        if doi_match:
            doi = doi_match.group(0)
            logger.info(f"Extracted DOI from filename: {doi}")
    
    # Import metadata clients
    from src.ingestion.metadata.crossref_client import CrossRefClient
    from src.ingestion.metadata.openalex_client import OpenAlexClient
    
    enriched = {**current_metadata}
    source = None
    
    try:
        if doi:
            # Try CrossRef first
            crossref = CrossRefClient()
            work = await crossref.get_by_doi(doi)
            
            if work:
                enriched.update({
                    "doi": doi,
                    "title": work.title or enriched.get("title"),
                    "authors": work.authors or enriched.get("authors", []),
                    "year": work.year or enriched.get("year"),
                    "journal": work.journal or enriched.get("journal"),
                    "publisher": work.publisher or enriched.get("publisher"),
                    "volume": work.volume or enriched.get("volume"),
                    "issue": work.issue or enriched.get("issue"),
                    "pages": work.pages or enriched.get("pages"),
                    "item_type": work.type or enriched.get("item_type"),
                })
                source = "crossref"
            
            # Also try OpenAlex for additional data
            openalex = OpenAlexClient()
            oa_work = await openalex.get_by_doi(doi)
            
            if oa_work:
                # OpenAlex often has better abstract, concepts, SDGs
                if oa_work.abstract and not enriched.get("abstract"):
                    enriched["abstract"] = oa_work.abstract
                if oa_work.concepts:
                    # concepts are dicts with 'name' key
                    enriched["keywords"] = [c["name"] for c in oa_work.concepts[:10] if c.get("name")]
                if oa_work.is_open_access is not None:
                    enriched["is_open_access"] = oa_work.is_open_access
                if not source:
                    source = "openalex"
        
        else:
            # No DOI - try OpenAlex search by title
            openalex = OpenAlexClient()
            
            # Prefer title from metadata (extracted from PDF) over filename
            search_title = current_metadata.get("title")
            if not search_title or len(search_title) < 10:
                # Fallback to filename if title is missing or too short
                search_title = original_filename.replace('.pdf', '').replace('_', ' ')
                # Remove common prefixes like hash
                import re
                search_title = re.sub(r'^[a-f0-9]{10,}_', '', search_title)
            
            # Fetch top 3 results to find best match
            works = await openalex.search(title=search_title, per_page=3)
            
            if works and len(works) > 0:
                # Check similarity to avoid hallucinations
                from difflib import SequenceMatcher
                def similarity(a, b):
                    return SequenceMatcher(None, a.lower(), b.lower()).ratio()
                
                best_match = None
                best_score = 0.0
                
                for work in works:
                    if not work.title: continue
                    score = similarity(search_title, work.title)
                    if score > best_score:
                        best_score = score
                        best_match = work
                
                # Only accept if similarity is reasonable (> 0.8)
                logger.info(f"Best match score: {best_score} for '{search_title}' vs '{best_match.title}'")
                if best_match and best_score > 0.8:
                    oa_work = best_match
                    enriched.update({
                        "title": oa_work.title or enriched.get("title"),
                        "authors": oa_work.authors or enriched.get("authors", []),
                        "year": oa_work.year or enriched.get("year"),
                        "doi": oa_work.doi or enriched.get("doi"),
                        "abstract": oa_work.abstract or enriched.get("abstract"),
                    })
                    if oa_work.concepts:
                        # concepts are dicts with 'name' key
                        enriched["keywords"] = [c["name"] for c in oa_work.concepts[:10] if c.get("name")]
                    source = "openalex"
                    logger.info(f"Enriched via title search: '{search_title}' -> '{oa_work.title}' (score: {best_score:.2f})")
                else:
                    logger.info(f"No good match for title '{search_title}' (best score: {best_score:.2f})")
                    raise HTTPException(status_code=404, detail=f"No confident match found for '{search_title}'. Try adding a DOI manually.")
            else:
                raise HTTPException(status_code=404, detail="Could not find metadata. Try adding a DOI manually.")
        
        if source:
            enriched["metadata_source"] = source
            enriched["metadata_confidence"] = 0.95 if doi else 0.7
            enriched["needs_review"] = False
        
        # Update in Supabase
        client.table("documents").update({
            "metadata": enriched,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", doc_id).execute()
        
        logger.info(f"Enriched doc {doc_id} from {source}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {e}")
    
    return await get_document_metadata(project_id, doc_id, user)


@router.post("/{project_id}/metadata/enrich-all")
async def enrich_all_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Enrich metadata for all documents in a project.
    Returns a summary of enriched vs failed documents.
    """
    import re
    from src.ingestion.metadata.crossref_client import CrossRefClient
    from src.ingestion.metadata.openalex_client import OpenAlexClient
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get all documents
    result = client.table("documents").select("*").eq("rag_project_id", project_id).execute()
    
    if not result.data:
        return {"enriched": 0, "failed": 0, "skipped": 0, "total": 0, "details": []}
    
    enriched_count = 0
    failed_count = 0
    skipped_count = 0
    details = []
    
    crossref = CrossRefClient()
    openalex = OpenAlexClient()
    
    for doc in result.data:
        doc_id = doc["id"]
        current_metadata = doc.get("metadata", {}) or {}
        doi = current_metadata.get("doi")
        original_filename = doc.get("original_filename", "")
        
        # Skip if already enriched with high confidence
        if current_metadata.get("metadata_source") and current_metadata.get("metadata_confidence", 0) >= 0.9:
            skipped_count += 1
            details.append({"id": doc_id, "status": "skipped", "reason": "Already enriched"})
            continue
        
        # Try to extract DOI from filename if not present
        if not doi:
            doi_match = re.search(r'10\.\d{4,}/[^\s]+', original_filename.replace('_', '/'))
            if doi_match:
                doi = doi_match.group(0)
        
        try:
            enriched = {**current_metadata}
            source = None
            
            if doi:
                # Try CrossRef
                work = await crossref.get_by_doi(doi)
                if work:
                    enriched.update({
                        "doi": doi,
                        "title": work.title or enriched.get("title"),
                        "authors": work.authors or enriched.get("authors", []),
                        "year": work.year or enriched.get("year"),
                        "journal": work.journal or enriched.get("journal"),
                        "publisher": work.publisher or enriched.get("publisher"),
                        "item_type": work.type or enriched.get("item_type"),
                    })
                    source = "crossref"
                
                # Also try OpenAlex for additional data
                oa_work = await openalex.get_by_doi(doi)
                if oa_work:
                    if oa_work.abstract and not enriched.get("abstract"):
                        enriched["abstract"] = oa_work.abstract
                    if oa_work.concepts:
                        # concepts are dicts with 'name' key
                        enriched["keywords"] = [c["name"] for c in oa_work.concepts[:10] if c.get("name")]
                    if not source:
                        source = "openalex"
            else:
                # Search by title from filename
                search_title = original_filename.replace('.pdf', '').replace('_', ' ')
                search_title = re.sub(r'^[a-f0-9]{10,}_', '', search_title)
                
                # Fetch top 3 results
                works = await openalex.search(title=search_title, per_page=3)
                
                if works and len(works) > 0:
                    # Check similarity to avoid hallucinations
                    from difflib import SequenceMatcher
                    def similarity(a, b):
                        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
                    
                    best_match = None
                    best_score = 0.0
                    
                    for work in works:
                        if not work.title: continue
                        score = similarity(search_title, work.title)
                        if score > best_score:
                            best_score = score
                            best_match = work
                    
                    # Only accept if similarity is reasonable (> 0.8)
                    if best_match and best_score > 0.8:
                        oa_work = best_match
                        enriched.update({
                            "title": oa_work.title or enriched.get("title"),
                            "authors": oa_work.authors or enriched.get("authors", []),
                            "year": oa_work.year or enriched.get("year"),
                            "doi": oa_work.doi or enriched.get("doi"),
                        })
                        if oa_work.concepts:
                            # concepts are dicts with 'name' key
                            enriched["keywords"] = [c["name"] for c in oa_work.concepts[:10] if c.get("name")]
                        source = "openalex"
            
            if source:
                enriched["metadata_source"] = source
                enriched["metadata_confidence"] = 0.95 if doi else 0.7
                enriched["needs_review"] = False
                
                client.table("documents").update({
                    "metadata": enriched,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", doc_id).execute()
                
                enriched_count += 1
                details.append({"id": doc_id, "status": "enriched", "source": source})
            else:
                failed_count += 1
                details.append({"id": doc_id, "status": "failed", "reason": "No metadata found"})
                
        except Exception as e:
            failed_count += 1
            details.append({"id": doc_id, "status": "failed", "reason": str(e)})
            logger.warning(f"Failed to enrich doc {doc_id}: {e}")
    
    logger.info(f"Enrich all: {enriched_count} enriched, {failed_count} failed, {skipped_count} skipped")
    
    return {
        "enriched": enriched_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "total": len(result.data),
        "details": details,
    }


@router.get("/{project_id}/documents/{doc_id}/pdf")
async def get_document_pdf_url(
    project_id: str,
    doc_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Get a presigned URL to view the PDF for a document.
    """
    import os
    from botocore.exceptions import ClientError
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = result.data
    
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Try the stored r2_input_key first, then fallback to constructed paths
        possible_keys = []
        
        # 1. Use stored R2 key if available
        if doc.get("r2_input_key"):
            possible_keys.append(doc["r2_input_key"])
        
        # 2. Multi-tenant path: rags/{project_id}/input-pdfs/{filename}.pdf
        possible_keys.extend([
            f"rags/{project_id}/input-pdfs/{doc['filename']}.pdf",
            f"rags/{project_id}/input-pdfs/{doc['filename']}",
        ])
        
        # 3. Legacy paths (for backwards compatibility)
        possible_keys.extend([
            f"input-pdfs/{doc['filename']}",
            f"input-pdfs/{doc['original_filename']}",
            f"input-pdfs/{doc_id}.pdf",
        ])
        
        r2_key = None
        for key in possible_keys:
            try:
                r2_client.head_object(Bucket=bucket_name, Key=key)
                r2_key = key
                break
            except ClientError:
                continue
        
        if not r2_key:
            logger.warning(f"PDF not found for doc {doc_id}. Tried keys: {possible_keys}")
            raise HTTPException(status_code=404, detail="PDF not found in storage")
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = r2_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': r2_key,
            },
            ExpiresIn=3600,
        )
        
        return {"url": presigned_url, "expires_in": 3600}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate PDF URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get PDF URL: {str(e)}")


@router.get("/{project_id}/documents/{doc_id}/pdf-highlighted")
async def get_highlighted_pdf(
    project_id: str,
    doc_id: str,
    page: int = 1,
    text: str = "",
):
    """
    Get a PDF with highlighted text for a specific citation.
    
    Downloads the PDF from R2, adds yellow highlight annotation to the specified text,
    and returns the modified PDF as a streaming response.
    
    No auth required for public projects. For private projects, returns 403.
    
    Args:
        project_id: The RAG project ID or slug
        doc_id: The document ID
        page: The page number (1-indexed) where the text appears
        text: The text to highlight (URL-encoded)
    """
    import io
    import re
    from fastapi.responses import StreamingResponse
    
    try:
        import pymupdf
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install pymupdf")
        raise HTTPException(status_code=500, detail="PDF highlighting not available")
    
    client = get_supabase_client()
    
    # Resolve project_id (could be UUID or slug)
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    is_uuid = bool(uuid_pattern.match(project_id))
    
    project = None
    if is_uuid:
        result = client.table("rag_projects").select("*").eq("id", project_id).execute()
        if result.data:
            project = result.data[0]
    
    if not project:
        # Try by slug
        result = client.table("rag_projects").select("*").eq("slug", project_id).execute()
        if result.data:
            project = result.data[0]
    
    if not project:
        raise HTTPException(status_code=404, detail="RAG project not found")
    
    # Check if public (no auth required for public projects)
    if not project.get("is_public", False):
        raise HTTPException(status_code=403, detail="This RAG is private. Authentication required.")
    
    actual_project_id = project["id"]
    
    # Get document - doc_id might be a UUID or a study_id (hash_filename format)
    # Try by database ID first, then by filename pattern
    doc = None
    uuid_pattern_local = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    
    if uuid_pattern_local.match(doc_id):
        # It's a UUID, look up directly
        try:
            result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", actual_project_id).single().execute()
            if result.data:
                doc = result.data
        except Exception:
            pass
    
    if not doc:
        # Try to extract filename from study_id (format: hash_filename or filename)
        # study_id might be "abc123_myfile" or just "myfile"
        parts = doc_id.split("_", 1)
        filename_search = parts[1] if len(parts) > 1 else doc_id
        
        # Search by filename containing the pattern (case-insensitive)
        try:
            result = client.table("documents").select("*").eq("rag_project_id", actual_project_id).ilike("filename", f"%{filename_search}%").execute()
            if result.data and len(result.data) == 1:
                doc = result.data[0]
            elif result.data and len(result.data) > 1:
                # Multiple matches, try exact match first
                for d in result.data:
                    if filename_search in d.get("filename", ""):
                        doc = d
                        break
                if not doc:
                    doc = result.data[0]  # Fall back to first match
        except Exception:
            pass
    
    if not doc:
        # Last resort: just get any document from this project 
        try:
            result = client.table("documents").select("*").eq("rag_project_id", actual_project_id).limit(1).execute()
            if result.data:
                doc = result.data[0]
                logger.warning(f"Could not find document {doc_id}, falling back to: {doc.get('filename')}")
        except Exception:
            pass
    
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Find the PDF key (same logic as get_document_pdf_url)
        possible_keys = []
        if doc.get("r2_input_key"):
            possible_keys.append(doc["r2_input_key"])
        possible_keys.extend([
            f"rags/{actual_project_id}/input-pdfs/{doc['filename']}.pdf",
            f"rags/{actual_project_id}/input-pdfs/{doc['filename']}",
            f"input-pdfs/{doc['filename']}",
            f"input-pdfs/{doc.get('original_filename', '')}",
            f"input-pdfs/{doc_id}.pdf",
        ])
        
        r2_key = None
        for key in possible_keys:
            try:
                r2_client.head_object(Bucket=bucket_name, Key=key)
                r2_key = key
                break
            except ClientError:
                continue
        
        if not r2_key:
            raise HTTPException(status_code=404, detail="PDF not found in storage")
        
        # Download PDF content
        response = r2_client.get_object(Bucket=bucket_name, Key=r2_key)
        pdf_bytes = response['Body'].read()
        
        # Open PDF with PyMuPDF and add highlights
        pdf_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        
        # Validate page number
        page_idx = page - 1  # PyMuPDF uses 0-indexed pages
        if page_idx < 0 or page_idx >= len(pdf_doc):
            page_idx = 0  # Fallback to first page
        
        # Add highlight if text is provided
        if text and len(text) > 10:
            pdf_page = pdf_doc[page_idx]
            all_rects = []
            
            # Clean the text for better matching - use up to 1500 chars (full chunk)
            search_text = text[:1500] if len(text) > 1500 else text
            search_text = search_text.replace('\n', ' ').replace('\r', ' ')
            search_text = ' '.join(search_text.split())  # Normalize whitespace
            
            # Strategy: Search for overlapping word groups (6-8 words)
            # PDFs often have line breaks that prevent long text matches
            words = search_text.split()
            
            if len(words) <= 8:
                # Short text - try to find it directly
                rects = pdf_page.search_for(search_text)
                all_rects.extend(rects)
            else:
                # For longer text, search for word groups with overlap
                group_size = 6  # Words per group
                step = 4  # Overlap by 2 words
                
                for i in range(0, len(words) - group_size + 1, step):
                    phrase = ' '.join(words[i:i + group_size])
                    rects = pdf_page.search_for(phrase)
                    if rects:
                        all_rects.extend(rects)
                
                # Also try the last group if we didn't cover it
                if len(words) > group_size:
                    last_phrase = ' '.join(words[-group_size:])
                    rects = pdf_page.search_for(last_phrase)
                    if rects:
                        all_rects.extend(rects)
            
            if all_rects:
                # Add yellow highlight annotation for all found rectangles
                highlight = pdf_page.add_highlight_annot(all_rects)
                highlight.set_colors(stroke=(1, 0.9, 0))  # Yellow
                highlight.update()
                logger.info(f"Added highlight to page {page} with {len(all_rects)} rectangles from {len(words)} words")
            else:
                # Last resort: try just the first 5 words
                fallback = ' '.join(words[:5])
                rects = pdf_page.search_for(fallback)
                if rects:
                    highlight = pdf_page.add_highlight_annot(rects)
                    highlight.set_colors(stroke=(1, 0.9, 0))
                    highlight.update()
                    logger.info(f"Added fallback highlight with first 5 words")
                else:
                    logger.warning(f"Text not found on page {page}: {search_text[:50]}...")
        
        # Save to bytes
        output = io.BytesIO()
        pdf_doc.save(output)
        pdf_doc.close()
        output.seek(0)
        
        # Return as streaming response with page anchor
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=highlighted_{doc_id}.pdf",
                "Cache-Control": "max-age=300",  # Cache for 5 minutes
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate highlighted PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to highlight PDF: {str(e)}")


# =============================================================================
# Per-RAG Danger Zone Endpoints
# =============================================================================

@router.delete("/{project_id}/vectors")
async def reset_project_vectors(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete all vector embeddings for this project from Qdrant.
    Documents will need to be reprocessed.
    """
    from qdrant_client import models
    
    project = await get_user_project(user, project_id)
    
    try:
        indexer = QdrantIndexer(collection_name=project["qdrant_collection"])
        
        # Delete all points in the collection using FilterSelector
        indexer.client.delete(
            collection_name=project["qdrant_collection"],
            points_selector=models.FilterSelector(
                filter=models.Filter()  # Empty filter = match all
            ),
        )
        
        # Update chunk counts in documents
        client = get_supabase_client()
        client.table("documents").update({
            "chunk_count": 0,
            "status": "pending",
        }).eq("rag_project_id", project_id).execute()
        
        logger.info(f"Reset vectors for project {project_id}")
        return {"message": "Vectors reset successfully", "collection": project["qdrant_collection"]}
        
    except Exception as e:
        logger.error(f"Failed to reset vectors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset vectors: {str(e)}")


@router.delete("/{project_id}/storage")
async def clear_project_storage(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete all PDFs and processed outputs for this project from R2.
    """
    import os
    
    project = await get_user_project(user, project_id)
    
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        deleted_count = 0
        
        # Multi-tenant path: rags/{project_id}/
        prefix = f"rags/{project_id}/"
        paginator = r2_client.get_paginator("list_objects_v2")
        
        # Delete all objects under the project prefix
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                try:
                    r2_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {obj['Key']}: {e}")
        
        logger.info(f"Cleared {deleted_count} files from R2 for project {project_id}")
        return {"message": "Storage cleared", "deleted": deleted_count}
        
    except Exception as e:
        logger.error(f"Failed to clear storage: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear storage: {str(e)}")


@router.post("/{project_id}/sync-status")
async def sync_document_status(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Sync document status from R2 outputs.
    
    Checks which documents have JSON outputs in R2 and updates their
    status to 'completed' in Supabase. Useful if Modal processing 
    completed but status sync failed.
    """
    from pathlib import Path
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    r2 = get_r2_client()
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat")
    
    try:
        # Get completed outputs from R2
        output_prefix = f"rags/{project_id}/outputs/json/"
        completed_stems = set()
        
        continuation_token = None
        while True:
            if continuation_token:
                response = r2.list_objects_v2(
                    Bucket=bucket, Prefix=output_prefix, ContinuationToken=continuation_token
                )
            else:
                response = r2.list_objects_v2(Bucket=bucket, Prefix=output_prefix)
            
            if "Contents" in response:
                for obj in response["Contents"]:
                    stem = Path(obj["Key"]).stem
                    completed_stems.add(stem)
            
            if response.get("IsTruncated"):
                continuation_token = response.get("NextContinuationToken")
            else:
                break
        
        logger.info(f"Found {len(completed_stems)} JSON outputs in R2")
        
        # Get all documents from Supabase
        docs_result = client.table("documents").select("id, filename, status").eq("rag_project_id", project_id).execute()
        docs = docs_result.data or []
        
        updated = 0
        for doc in docs:
            filename = doc.get("filename", "")
            if doc["status"] != "completed" and filename in completed_stems:
                # Update to completed
                client.table("documents").update({
                    "status": "completed",
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", doc["id"]).execute()
                updated += 1
                logger.info(f"  Synced to completed: {filename}")
        
        # Count final status
        final_result = client.table("documents").select("status").eq("rag_project_id", project_id).execute()
        status_counts = {}
        for d in final_result.data or []:
            s = d["status"]
            status_counts[s] = status_counts.get(s, 0) + 1
        
        return {
            "message": f"Synced {updated} documents to completed",
            "updated": updated,
            "r2_outputs": len(completed_stems),
            "status_counts": status_counts,
        }
        
    except Exception as e:
        logger.error(f"Failed to sync status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync status: {str(e)}")


@router.delete("/{project_id}/documents")
async def reset_project_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete all document records from the database for this project.
    Does not delete files from R2 or vectors from Qdrant.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    try:
        # Count documents first
        count_result = client.table("documents").select("id", count="exact").eq("rag_project_id", project_id).execute()
        doc_count = count_result.count or 0
        
        # Delete all documents
        client.table("documents").delete().eq("rag_project_id", project_id).execute()
        
        # Also delete any jobs
        client.table("processing_jobs").delete().eq("rag_project_id", project_id).execute()
        
        logger.info(f"Deleted {doc_count} documents from project {project_id}")
        return {"message": "Documents reset", "deleted": doc_count}
        
    except Exception as e:
        logger.error(f"Failed to reset documents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset documents: {str(e)}")


@router.delete("/{project_id}/documents/{document_id}")
async def delete_single_document(
    project_id: str,
    document_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete a single document from the project.
    Also deletes associated vectors from Qdrant and files from R2.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    try:
        # Get document info first
        doc_result = client.table("documents").select("filename, r2_key").eq("id", document_id).eq("rag_project_id", project_id).execute()
        if not doc_result.data:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = doc_result.data[0]
        filename = doc.get("filename", "")
        r2_key = doc.get("r2_key", "")
        
        # Delete vectors from Qdrant
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue
            import os
            
            qdrant_url = os.environ.get("QDRANT_URL", "")
            qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
            
            if qdrant_url:
                qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
                collection_name = f"rag_{project_id}"
                
                # Check if collection exists
                collections = qdrant.get_collections().collections
                if any(c.name == collection_name for c in collections):
                    # Delete by document_id filter
                    qdrant.delete(
                        collection_name=collection_name,
                        points_selector=Filter(
                            must=[
                                FieldCondition(
                                    key="document_id",
                                    match=MatchValue(value=document_id)
                                )
                            ]
                        )
                    )
                    logger.info(f"Deleted vectors for document {document_id} from Qdrant")
        except Exception as e:
            logger.warning(f"Failed to delete vectors from Qdrant: {e}")
        
        # Delete files from R2
        try:
            import boto3
            
            r2_endpoint = os.environ.get("R2_ENDPOINT_URL", "")
            r2_access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
            r2_secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
            r2_bucket = os.environ.get("R2_BUCKET_NAME", "devchat-docs")
            
            if r2_endpoint and r2_key:
                s3 = boto3.client(
                    "s3",
                    endpoint_url=r2_endpoint,
                    aws_access_key_id=r2_access_key,
                    aws_secret_access_key=r2_secret_key,
                )
                
                # Delete PDF
                try:
                    s3.delete_object(Bucket=r2_bucket, Key=r2_key)
                    logger.info(f"Deleted PDF from R2: {r2_key}")
                except Exception as e:
                    logger.warning(f"Failed to delete PDF from R2: {e}")
                
                # Delete markdown output if exists
                md_key = r2_key.replace("/pdfs/", "/outputs/").replace(".pdf", ".md")
                try:
                    s3.delete_object(Bucket=r2_bucket, Key=md_key)
                    logger.info(f"Deleted markdown from R2: {md_key}")
                except Exception:
                    pass
                    
        except Exception as e:
            logger.warning(f"Failed to delete files from R2: {e}")
        
        # Delete from database
        client.table("documents").delete().eq("id", document_id).execute()
        
        logger.info(f"Deleted document {document_id} ({filename}) from project {project_id}")
        return {"message": "Document deleted", "document_id": document_id, "filename": filename}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


