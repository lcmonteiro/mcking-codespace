"""
Authentication middleware and dependencies.

- Bearer token extraction from Authorization header  
- Admin key guard for management endpoints
"""
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

_bearer = HTTPBearer(auto_error=False)


def extract_bearer_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    """Extract raw Bearer token; raises 401 if missing."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def require_admin(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> None:
    """Guard for admin/management endpoints — checks static ADMIN_API_KEY."""
    if credentials is None or credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key required.",
        )
