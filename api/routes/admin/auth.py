"""
Admin Authentication Routes

Provides login/logout endpoints for browser-based admin access.
"""

from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from src.config.settings import settings
from src.utils.logging import get_logger
from ..dependencies import (
    create_admin_session,
    invalidate_session,
    session_header,
)

logger = get_logger(__name__)

router = APIRouter(tags=["admin-auth"])


class LoginRequest(BaseModel):
    """Login request with password."""
    password: str


class LoginResponse(BaseModel):
    """Login response with session token."""
    success: bool
    token: str
    expires_in: int
    message: str


class LogoutResponse(BaseModel):
    """Logout response."""
    success: bool
    message: str


class AuthStatusResponse(BaseModel):
    """Authentication status check response."""
    authenticated: bool
    auth_required: bool
    message: str


@router.post("/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest):
    """
    Authenticate with admin password and receive a session token.
    
    The session token should be included in subsequent requests as:
    X-Admin-Session: <token>
    
    Session expires after 24 hours.
    """
    admin_password = settings.admin_password
    
    # If no password configured, auth is disabled
    if not admin_password:
        logger.warning("Login attempted but ADMIN_PASSWORD not set")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication not configured. Set ADMIN_PASSWORD environment variable.",
        )
    
    # Verify password
    if request.password != admin_password:
        logger.warning("Failed login attempt with incorrect password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    
    # Create session
    token, expires_in = create_admin_session()
    
    logger.info("Admin login successful")
    return LoginResponse(
        success=True,
        token=token,
        expires_in=expires_in,
        message="Login successful",
    )


@router.post("/logout", response_model=LogoutResponse)
async def admin_logout(
    session_token: str = Security(session_header),
):
    """
    Invalidate the current session token (logout).
    """
    if session_token and invalidate_session(session_token):
        logger.info("Admin logout successful")
        return LogoutResponse(
            success=True,
            message="Logged out successfully",
        )
    
    return LogoutResponse(
        success=False,
        message="No active session to logout",
    )


@router.get("/auth-status", response_model=AuthStatusResponse)
async def check_auth_status(
    session_token: str = Security(session_header),
):
    """
    Check if the current session is authenticated.
    
    This endpoint does NOT require authentication - it's used by the frontend
    to check if a login is needed.
    """
    from ..dependencies import verify_session_token
    
    admin_password = settings.admin_password
    admin_api_key = settings.admin_api_key
    
    # If no auth configured, no login required
    if not admin_password and not admin_api_key:
        return AuthStatusResponse(
            authenticated=True,
            auth_required=False,
            message="Authentication not configured (development mode)",
        )
    
    # Check if session is valid
    if session_token and verify_session_token(session_token):
        return AuthStatusResponse(
            authenticated=True,
            auth_required=True,
            message="Session valid",
        )
    
    return AuthStatusResponse(
        authenticated=False,
        auth_required=True,
        message="Login required",
    )
