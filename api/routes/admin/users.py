"""
Admin Users Routes

Endpoints for viewing users and their RAG projects.
Uses Supabase client for direct database access.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class RagProjectInfo(BaseModel):
    """RAG project summary for admin view."""
    id: str
    name: str
    description: Optional[str] = None
    slug: Optional[str] = None
    is_public: bool = False
    document_count: int
    chunk_count: int
    created_at: str
    last_query_at: Optional[str] = None


class UserWithRags(BaseModel):
    """User with their RAG projects and usage stats."""
    id: str
    email: str
    created_at: str
    last_sign_in_at: Optional[str] = None
    rag_projects: List[RagProjectInfo]
    total_queries: int
    total_cost_usd: float


# =============================================================================
# Supabase Client Helper
# =============================================================================

def get_supabase():
    """Get Supabase client."""
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception as e:
        logger.warning(f"Failed to create Supabase client: {e}")
        return None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/users", response_model=List[UserWithRags])
async def get_all_users():
    """
    Get all users with their RAG projects and usage statistics.
    
    Returns:
        List of users with their RAG projects, query counts, and costs
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Get all RAG projects with document counts
        rags_response = supabase.table("rag_projects").select(
            "id, name, description, slug, is_public, user_id, created_at"
        ).order("created_at", desc=True).execute()
        
        if not rags_response.data:
            return []
        
        # Get document counts per project
        docs_response = supabase.table("documents").select(
            "rag_project_id, chunk_count"
        ).execute()
        
        # Build document count map
        doc_counts: Dict[str, Dict[str, int]] = {}
        for doc in docs_response.data or []:
            project_id = doc.get("rag_project_id")
            if project_id:
                if project_id not in doc_counts:
                    doc_counts[project_id] = {"docs": 0, "chunks": 0}
                doc_counts[project_id]["docs"] += 1
                doc_counts[project_id]["chunks"] += doc.get("chunk_count") or 0
        
        # Get usage stats per user
        usage_response = supabase.table("usage_logs").select(
            "user_id, cost_usd"
        ).execute()
        
        # Build usage map
        usage_map: Dict[str, Dict[str, Any]] = {}
        for log in usage_response.data or []:
            user_id = log.get("user_id")
            if user_id:
                if user_id not in usage_map:
                    usage_map[user_id] = {"queries": 0, "cost": 0.0}
                usage_map[user_id]["queries"] += 1
                usage_map[user_id]["cost"] += log.get("cost_usd") or 0.0
        
        # Group RAGs by user
        users_map: Dict[str, Dict[str, Any]] = {}
        for rag in rags_response.data:
            user_id = rag.get("user_id")
            if not user_id:
                continue
                
            if user_id not in users_map:
                users_map[user_id] = {
                    "id": user_id,
                    "email": f"user-{user_id[:8]}...",  # Placeholder
                    "created_at": rag.get("created_at", ""),
                    "rag_projects": [],
                    "total_queries": usage_map.get(user_id, {}).get("queries", 0),
                    "total_cost_usd": usage_map.get(user_id, {}).get("cost", 0.0),
                }
            
            project_id = rag.get("id")
            counts = doc_counts.get(project_id, {"docs": 0, "chunks": 0})
            
            users_map[user_id]["rag_projects"].append(RagProjectInfo(
                id=project_id,
                name=rag.get("name", "Unnamed"),
                description=rag.get("description"),
                slug=rag.get("slug"),
                is_public=rag.get("is_public", False),
                document_count=counts["docs"],
                chunk_count=counts["chunks"],
                created_at=rag.get("created_at", ""),
                last_query_at=None,
            ))
        
        # Try to get actual emails from auth.users (requires service role)
        try:
            # Use Supabase admin API to get user emails
            auth_response = supabase.auth.admin.list_users()
            if auth_response:
                for user in auth_response:
                    user_id = str(user.id)
                    if user_id in users_map:
                        users_map[user_id]["email"] = user.email or f"user-{user_id[:8]}..."
                        users_map[user_id]["created_at"] = user.created_at if hasattr(user, 'created_at') else users_map[user_id]["created_at"]
                        if hasattr(user, 'last_sign_in_at') and user.last_sign_in_at:
                            users_map[user_id]["last_sign_in_at"] = user.last_sign_in_at
        except Exception as e:
            logger.debug(f"Could not fetch auth.users (expected if not using service role): {e}")
        
        # Convert to list and sort by most RAGs first
        users = [
            UserWithRags(**user_data)
            for user_data in sorted(
                users_map.values(),
                key=lambda x: len(x["rag_projects"]),
                reverse=True
            )
        ]
        
        return users
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch users: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str):
    """
    Get detailed information about a specific user.
    
    Args:
        user_id: The user's UUID
        
    Returns:
        User details with RAG projects and usage history
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Get user's RAG projects
        rags_response = supabase.table("rag_projects").select(
            "id, name, description, slug, is_public, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
        
        if not rags_response.data:
            raise HTTPException(status_code=404, detail="User not found or has no projects")
        
        # Get document counts for these projects
        project_ids = [r["id"] for r in rags_response.data]
        docs_response = supabase.table("documents").select(
            "rag_project_id, chunk_count"
        ).in_("rag_project_id", project_ids).execute()
        
        # Build document count map
        doc_counts: Dict[str, Dict[str, int]] = {}
        for doc in docs_response.data or []:
            project_id = doc.get("rag_project_id")
            if project_id:
                if project_id not in doc_counts:
                    doc_counts[project_id] = {"docs": 0, "chunks": 0}
                doc_counts[project_id]["docs"] += 1
                doc_counts[project_id]["chunks"] += doc.get("chunk_count") or 0
        
        # Build RAG projects list
        rag_projects = []
        for rag in rags_response.data:
            project_id = rag.get("id")
            counts = doc_counts.get(project_id, {"docs": 0, "chunks": 0})
            rag_projects.append({
                "id": project_id,
                "name": rag.get("name", "Unnamed"),
                "description": rag.get("description"),
                "slug": rag.get("slug"),
                "is_public": rag.get("is_public", False),
                "document_count": counts["docs"],
                "chunk_count": counts["chunks"],
                "created_at": rag.get("created_at", ""),
            })
        
        # Get usage history (last 30 days)
        usage_response = supabase.table("usage_logs").select(
            "created_at, model, input_tokens, output_tokens, cost_usd, latency_ms"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(100).execute()
        
        # Aggregate by date
        usage_by_date: Dict[str, Dict[str, Any]] = {}
        for log in usage_response.data or []:
            created = log.get("created_at", "")[:10]  # YYYY-MM-DD
            if created not in usage_by_date:
                usage_by_date[created] = {"queries": 0, "cost_usd": 0.0}
            usage_by_date[created]["queries"] += 1
            usage_by_date[created]["cost_usd"] += log.get("cost_usd") or 0.0
        
        usage_history = [
            {"date": date, **data}
            for date, data in sorted(usage_by_date.items(), reverse=True)
        ]
        
        # Get user email if possible
        email = f"user-{user_id[:8]}..."
        created_at = rags_response.data[0].get("created_at", "") if rags_response.data else ""
        last_sign_in_at = None
        
        try:
            user = supabase.auth.admin.get_user_by_id(user_id)
            if user and hasattr(user, 'user'):
                email = user.user.email or email
                if hasattr(user.user, 'created_at'):
                    created_at = user.user.created_at
                if hasattr(user.user, 'last_sign_in_at') and user.user.last_sign_in_at:
                    last_sign_in_at = user.user.last_sign_in_at
        except Exception as e:
            logger.debug(f"Could not fetch user from auth: {e}")
        
        # Calculate totals
        total_queries = sum(d["queries"] for d in usage_by_date.values())
        total_cost = sum(d["cost_usd"] for d in usage_by_date.values())
        
        return {
            "id": user_id,
            "email": email,
            "created_at": created_at,
            "last_sign_in_at": last_sign_in_at,
            "rag_projects": rag_projects,
            "usage_history": usage_history,
            "total_queries": total_queries,
            "total_cost_usd": total_cost,
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}")


@router.get("/rags")
async def get_all_rags():
    """
    Get all RAG projects across all users.
    
    Returns:
        List of RAG projects with owner info and stats
    """
    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Get all RAG projects
        rags_response = supabase.table("rag_projects").select(
            "id, name, description, slug, is_public, user_id, created_at"
        ).order("created_at", desc=True).execute()
        
        if not rags_response.data:
            return []
        
        # Get document counts
        docs_response = supabase.table("documents").select(
            "rag_project_id, chunk_count"
        ).execute()
        
        doc_counts: Dict[str, Dict[str, int]] = {}
        for doc in docs_response.data or []:
            project_id = doc.get("rag_project_id")
            if project_id:
                if project_id not in doc_counts:
                    doc_counts[project_id] = {"docs": 0, "chunks": 0}
                doc_counts[project_id]["docs"] += 1
                doc_counts[project_id]["chunks"] += doc.get("chunk_count") or 0
        
        # Get user emails
        user_emails: Dict[str, str] = {}
        try:
            auth_response = supabase.auth.admin.list_users()
            if auth_response:
                for user in auth_response:
                    user_emails[str(user.id)] = user.email or f"user-{str(user.id)[:8]}..."
        except Exception:
            pass
        
        # Build response
        rags = []
        for rag in rags_response.data:
            project_id = rag.get("id")
            user_id = rag.get("user_id", "")
            counts = doc_counts.get(project_id, {"docs": 0, "chunks": 0})
            
            rags.append({
                "id": project_id,
                "name": rag.get("name", "Unnamed"),
                "description": rag.get("description"),
                "slug": rag.get("slug"),
                "is_public": rag.get("is_public", False),
                "user_id": user_id,
                "user_email": user_emails.get(user_id, f"user-{user_id[:8]}..." if user_id else "unknown"),
                "document_count": counts["docs"],
                "chunk_count": counts["chunks"],
                "created_at": rag.get("created_at", ""),
            })
        
        return rags
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch RAGs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch RAGs: {str(e)}")
