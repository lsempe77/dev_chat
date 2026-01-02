"""
Supabase Authentication Module

Handles JWT token verification and user authentication for multi-tenant RAG.
"""

from typing import Optional
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from supabase import create_client, Client

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user from Supabase."""
    id: str  # UUID
    email: str
    role: str  # 'authenticated', 'anon', etc.
    
    
@lru_cache()
def get_supabase_client() -> Client:
    """
    Get a cached Supabase client using the service role key.
    
    Service role key bypasses RLS for admin operations.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ValueError("Supabase URL and service role key must be configured")
    
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key
    )


def get_supabase_anon_client() -> Client:
    """
    Get a Supabase client using the anon key.
    
    Use this for operations that should respect RLS.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase URL and anon key must be configured")
    
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key
    )


def verify_supabase_token(token: str) -> Optional[AuthenticatedUser]:
    """
    Verify a Supabase JWT token and extract user info.
    
    Args:
        token: JWT token from Authorization header
        
    Returns:
        AuthenticatedUser if valid, None otherwise
    """
    if not settings.supabase_jwt_secret:
        logger.warning("SUPABASE_JWT_SECRET not configured - using Supabase API for verification")
        return verify_token_via_api(token)
    
    try:
        # Verify JWT with secret
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated"
        )
        
        user_id = payload.get("sub")
        email = payload.get("email", "")
        role = payload.get("role", "authenticated")
        
        if not user_id:
            return None
            
        return AuthenticatedUser(
            id=user_id,
            email=email,
            role=role
        )
        
    except JWTError as e:
        logger.debug(f"JWT verification failed: {e}")
        return None


def verify_token_via_api(token: str) -> Optional[AuthenticatedUser]:
    """
    Verify token by calling Supabase API.
    
    Fallback when JWT secret is not available.
    """
    try:
        client = get_supabase_anon_client()
        # Get user from token
        response = client.auth.get_user(token)
        
        if response and response.user:
            return AuthenticatedUser(
                id=response.user.id,
                email=response.user.email or "",
                role=response.user.role or "authenticated"
            )
    except Exception as e:
        logger.debug(f"Token verification via API failed: {e}")
    
    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency to get the current authenticated user.
    
    Usage:
        @app.get("/api/protected")
        async def protected_route(user: AuthenticatedUser = Depends(get_current_user)):
            return {"user_id": user.id}
    """
    # Check if Supabase is configured
    if not settings.supabase_url:
        # Supabase not configured - fall back to legacy auth
        logger.debug("Supabase not configured, using legacy auth")
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Multi-tenant auth requires Supabase configuration"
        )
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    user = verify_supabase_token(token)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """
    FastAPI dependency to get the current user if authenticated, None otherwise.
    
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    if not credentials or not settings.supabase_url:
        return None
    
    return verify_supabase_token(credentials.credentials)


def is_multi_tenant_enabled() -> bool:
    """Check if multi-tenant mode is enabled (Supabase configured)."""
    return bool(settings.supabase_url and settings.supabase_anon_key)
