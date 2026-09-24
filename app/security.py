from typing import Annotated, Optional
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from pydantic import BaseModel

from .config import settings

# auto_error=False gives you the green "Authorize" button in Swagger UI (/docs) without blocking guests
security_scheme = HTTPBearer(auto_error=False)


class UserContext(BaseModel):
    is_authenticated: bool = False
    is_admin: bool = False
    user_id: Optional[str] = None
    email: Optional[str] = None


async def get_user_context(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security_scheme)]
) -> UserContext:
    if credentials is None:
        return UserContext(is_authenticated=False, is_admin=False)

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SUPABASE_JWT_SECRET.get_secret_value(),
            algorithms=["HS256"],
            audience="authenticated",
        )

        email = (payload.get("email") or "").strip().lower()
        user_id = payload.get("sub")
        app_metadata = payload.get("app_metadata", {})
        jwt_role = payload.get("role", "")

        # Dynamic admin verification against configured list and Supabase claims
        is_admin = (
            (email and email in settings.admin_emails_list)
            or app_metadata.get("role") in settings.admin_roles_list
            or app_metadata.get("is_admin") is True
            or jwt_role in settings.admin_roles_list
        )

        return UserContext(
            is_authenticated=True,
            is_admin=is_admin,
            user_id=user_id,
            email=email if email else None,
        )
    except jwt.PyJWTError:
        # Invalid or expired token defaults back to unauthenticated guest
        return UserContext(is_authenticated=False, is_admin=False)
