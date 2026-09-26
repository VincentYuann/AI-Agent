import logging
from contextvars import ContextVar
from typing import Annotated, Optional, Dict, Any
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)

# Request-scoped ContextVar to propagate the verified admin token to tool executions
admin_token_context: ContextVar[Optional[str]] = ContextVar("admin_token_context", default=None)

# auto_error=False provides the green "Authorize" button in Swagger UI (/docs) without blocking guests
security_scheme = HTTPBearer(auto_error=False)

# Cache PyJWKClient instances per issuer URL
_jwks_clients: Dict[str, PyJWKClient] = {}


def _get_jwks_client(issuer: str) -> PyJWKClient:
    clean_iss = issuer.rstrip("/")
    # Supabase JWKS endpoint is always under /auth/v1/.well-known/jwks.json
    if not clean_iss.endswith("/auth/v1"):
        clean_iss = f"{clean_iss}/auth/v1"
    if clean_iss not in _jwks_clients:
        jwks_url = f"{clean_iss}/.well-known/jwks.json"
        _jwks_clients[clean_iss] = PyJWKClient(jwks_url)
    return _jwks_clients[clean_iss]


class UserContext(BaseModel):
    is_authenticated: bool = False
    is_admin: bool = False
    user_id: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    raw_token: Optional[str] = None


def decode_supabase_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and validates a Supabase JWT (Access Token).
    Supports:
      - Asymmetric signing (ES256 / RS256) verified via Supabase JWKS endpoint.
      - Symmetric signing (HS256) verified via SUPABASE_JWT_SECRET.
    Validates signature, expiration, and audience ('authenticated').
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "HS256")

        if alg in ["ES256", "RS256"]:
            issuer = settings.SUPABASE_URL
            if not issuer:
                return None
            jwks_client = _get_jwks_client(issuer)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
            )

        # Fallback to HS256 with JWT Secret
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET.get_secret_value(),
            algorithms=["HS256"],
            audience="authenticated",
        )
    except Exception as e:
        logger.warning(f"JWT decode failed: {type(e).__name__} - {e}")
        return None


async def get_user_context(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security_scheme)]
) -> UserContext:
    if credentials is None:
        return UserContext(is_authenticated=False, is_admin=False)

    payload = decode_supabase_jwt(credentials.credentials)
    if not payload:
        return UserContext(is_authenticated=False, is_admin=False)

    user_id = payload.get("sub")
    user_meta = payload.get("user_metadata") or {}
    app_meta = payload.get("app_metadata") or {}

    # Top-level verified email and username for identification
    verified_email = (payload.get("email") or "").strip().lower()
    username = (user_meta.get("user_name") or user_meta.get("preferred_username") or "").strip().lower()
    role = (app_meta.get("role") or payload.get("role") or "").strip()

    # STRICT AUTHORIZATION:
    # Per Supabase Security Guidelines: Never use user_metadata claims in authorization decisions.
    # user_metadata is user-editable via client SDKs (signUp / updateUser).
    # Authorize exclusively via top-level verified email or trusted app_metadata role.
    is_admin = (
        (bool(verified_email) and verified_email in settings.admin_emails_list)
        or (bool(role) and role in settings.admin_roles_list)
    )

    return UserContext(
        is_authenticated=True,
        is_admin=is_admin,
        user_id=user_id,
        email=verified_email if verified_email else None,
        username=username if username else None,
        raw_token=credentials.credentials,
    )
