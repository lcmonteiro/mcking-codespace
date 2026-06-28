"""
Authentication guards and dependencies.

Provides Bearer token extraction from the Authorization header and an admin
key guard for management endpoints.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

# ====================================================================================================
# Security
# ====================================================================================================

_bearer = HTTPBearer(auto_error=False)


def extract_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> str:
    """
    Extract the raw Bearer token from the request; raises 401 if missing.

    Args:
        credentials: The HTTP Authorization credentials, or None.

    Returns:
        The Bearer token string.

    Raises:
        HTTPException: If the Authorization header is absent or invalid.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Missing or invalid Authorization header. Use: Bearer <token>",
            headers     = {"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> None:
    """
    Guard for admin/management endpoints — checks static ADMIN_API_KEY.

    Args:
        credentials: The HTTP Authorization credentials, or None.

    Raises:
        HTTPException: If the admin key does not match.
    """
    if credentials is None or credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail      = "Admin API key required.",
        )
