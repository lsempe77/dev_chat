"""
Authentication module for multi-tenant RAG.
"""

from .supabase_auth import (
    AuthenticatedUser,
    get_current_user,
    get_optional_user,
    get_supabase_client,
    get_supabase_anon_client,
    is_multi_tenant_enabled,
    verify_supabase_token,
)

__all__ = [
    "AuthenticatedUser",
    "get_current_user",
    "get_optional_user",
    "get_supabase_client",
    "get_supabase_anon_client",
    "is_multi_tenant_enabled",
    "verify_supabase_token",
]
