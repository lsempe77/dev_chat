"""
Admin Users Routes

Endpoints for viewing users and their RAG projects.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.utils.logging import get_logger
from ..dependencies import get_db_session

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


class UsersResponse(BaseModel):
    """List of users with their RAG projects."""
    users: List[UserWithRags]
    total_users: int
    total_rags: int


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
    db = await get_db_session()
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        async with db:
            from sqlalchemy import text
            
            # Get distinct users from rag_projects (auth.users not directly accessible)
            # This gets all users who have at least one RAG project
            users_sql = text("""
                SELECT DISTINCT 
                    rp.user_id as id,
                    MIN(rp.created_at) as first_project_at
                FROM rag_projects rp
                GROUP BY rp.user_id
                ORDER BY first_project_at DESC
            """)
            
            users_result = await db.execute(users_sql)
            users_rows = users_result.fetchall()
            
            users = []
            for user_row in users_rows:
                user_id = str(user_row.id)
                
                # Get RAG projects for this user
                rags_sql = text("""
                    SELECT 
                        rp.id,
                        rp.name,
                        rp.description,
                        rp.created_at,
                        COUNT(DISTINCT d.id) as document_count,
                        COALESCE(SUM(d.chunk_count), 0) as chunk_count
                    FROM rag_projects rp
                    LEFT JOIN documents d ON d.rag_project_id = rp.id
                    WHERE rp.user_id = :user_id
                    GROUP BY rp.id, rp.name, rp.description, rp.created_at
                    ORDER BY rp.created_at DESC
                """)
                
                rags_result = await db.execute(rags_sql, {"user_id": user_id})
                rags_rows = rags_result.fetchall()
                
                rag_projects = []
                for rag_row in rags_rows:
                    rag_projects.append(RagProjectInfo(
                        id=str(rag_row.id),
                        name=rag_row.name,
                        description=rag_row.description,
                        document_count=rag_row.document_count or 0,
                        chunk_count=int(rag_row.chunk_count or 0),
                        created_at=rag_row.created_at.isoformat() if rag_row.created_at else "",
                        last_query_at=None,  # TODO: Get from usage_logs
                    ))
                
                # Get usage stats for this user (if usage_logs table exists)
                try:
                    usage_sql = text("""
                        SELECT 
                            COUNT(*) as total_queries,
                            COALESCE(SUM(cost_usd), 0) as total_cost_usd
                        FROM usage_logs
                        WHERE user_id = :user_id
                    """)
                    usage_result = await db.execute(usage_sql, {"user_id": user_id})
                    usage_row = usage_result.fetchone()
                    total_queries = usage_row.total_queries if usage_row else 0
                    total_cost = float(usage_row.total_cost_usd) if usage_row else 0.0
                except Exception:
                    # usage_logs table might not exist yet
                    total_queries = 0
                    total_cost = 0.0
                
                # Use truncated user_id as email placeholder since auth.users not accessible
                users.append(UserWithRags(
                    id=user_id,
                    email=f"user-{user_id[:8]}...",  # Placeholder, can't access auth.users
                    created_at=user_row.first_project_at.isoformat() if user_row.first_project_at else "",
                    last_sign_in_at=None,
                    rag_projects=rag_projects,
                    total_queries=total_queries,
                    total_cost_usd=total_cost,
                ))
            
            return users
            
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
    db = await get_db_session()
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        async with db:
            from sqlalchemy import text
            
            # Check if user exists by looking for their RAG projects
            check_sql = text("""
                SELECT user_id, MIN(created_at) as first_project_at
                FROM rag_projects
                WHERE user_id = :user_id
                GROUP BY user_id
            """)
            
            check_result = await db.execute(check_sql, {"user_id": user_id})
            check_row = check_result.fetchone()
            
            if not check_row:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Get RAG projects
            rags_sql = text("""
                SELECT 
                    rp.id,
                    rp.name,
                    rp.description,
                    rp.created_at,
                    COUNT(DISTINCT d.id) as document_count,
                    COALESCE(SUM(d.chunk_count), 0) as chunk_count
                FROM rag_projects rp
                LEFT JOIN documents d ON d.rag_project_id = rp.id
                WHERE rp.user_id = :user_id
                GROUP BY rp.id, rp.name, rp.description, rp.created_at
                ORDER BY rp.created_at DESC
            """)
            
            rags_result = await db.execute(rags_sql, {"user_id": user_id})
            rags_rows = rags_result.fetchall()
            
            rag_projects = []
            for rag_row in rags_rows:
                rag_projects.append({
                    "id": str(rag_row.id),
                    "name": rag_row.name,
                    "description": rag_row.description,
                    "document_count": rag_row.document_count or 0,
                    "chunk_count": int(rag_row.chunk_count or 0),
                    "created_at": rag_row.created_at.isoformat() if rag_row.created_at else "",
                })
            
            # Get recent usage (last 30 days)
            try:
                usage_sql = text("""
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as queries,
                        COALESCE(SUM(cost_usd), 0) as cost_usd
                    FROM usage_logs
                    WHERE user_id = :user_id
                      AND created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                """)
                usage_result = await db.execute(usage_sql, {"user_id": user_id})
                usage_rows = usage_result.fetchall()
                
                usage_history = [
                    {
                        "date": str(row.date),
                        "queries": row.queries,
                        "cost_usd": float(row.cost_usd),
                    }
                    for row in usage_rows
                ]
            except Exception:
                usage_history = []
            
            return {
                "id": user_id,
                "email": f"user-{user_id[:8]}...",  # Placeholder, can't access auth.users
                "created_at": check_row.first_project_at.isoformat() if check_row.first_project_at else "",
                "last_sign_in_at": None,
                "rag_projects": rag_projects,
                "usage_history": usage_history,
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}")
