from typing import Annotated, Optional, Dict, Any
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from .config import settings

# auto_error=False provides the green "Authorize" button in Swagger UI (/docs) without blocking guests
security_scheme = HTTPBearer(auto_error=False)

# Cache PyJWKClient instances per issuer URL
_jwks_clients: Dict[str, PyJWKClient] = {}


def _get_jwks_client(issuer: str) -> PyJWKClient:
    clean_iss = issuer.rstrip("/")
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
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            issuer = settings.SUPABASE_URL or unverified_payload.get("iss")
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
    except Exception:
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
    email = (payload.get("email") or "").strip().lower()
    user_meta = payload.get("user_metadata") or {}
    app_meta = payload.get("app_metadata") or {}

    username = (user_meta.get("user_name") or user_meta.get("preferred_username") or "").strip().lower()
    role = (app_meta.get("role") or payload.get("role") or "").strip()

    # Determine Admin status directly against configured settings
    is_admin = (
        (bool(email) and email in settings.admin_emails_list)
        or (bool(username) and username in settings.admin_usernames_list)
        or (bool(role) and role in settings.admin_roles_list)
    )

    return UserContext(
        is_authenticated=True,
        is_admin=is_admin,
        user_id=user_id,
        email=email if email else None,
        username=username if username else None,
    )
