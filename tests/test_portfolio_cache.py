import pytest
import time
import jwt
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.portfolio_service import (
    get_portfolio_context,
    invalidate_portfolio_cache,
    get_cache_status,
)
from app.tools import get_agent_tools, TOOL_FUNCTIONS

client = TestClient(app)


def create_mock_jwt(email: str, username: str = "") -> str:
    payload = {
        "sub": "test-uuid-12345",
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "user_metadata": {
            "email": email,
            "user_name": username,
        },
    }
    secret = settings.SUPABASE_JWT_SECRET.get_secret_value()
    return jwt.encode(payload, secret, algorithm="HS256")


MOCK_PORTFOLIO_YAML = """candidate: Vincent Yuan
profile:
  name: Vincent Yuan
  role: Software & Generative AI Engineer
  headline: Crafting thoughtful digital experiences with algorithmic clarity.
  email: vincentyuan1020@gmail.com
projects:
  - title: Sumi-OS
    overview: Aesthetic terminal workspace.
experience:
  - company: Freelance
    title: Systems Engineer
philosophy:
  - title: Simplicity
"""


@pytest.fixture(autouse=True)
def mock_supabase_fetch(monkeypatch):
    monkeypatch.setattr("app.portfolio_service.fetch_from_supabase", lambda: MOCK_PORTFOLIO_YAML)


@pytest.mark.asyncio
async def test_fetch_from_supabase_async_rpc(monkeypatch):
    from app.portfolio_service import fetch_from_supabase_async
    import httpx

    mock_payload = {
        "candidate": "Vincent Yuan",
        "profile": {"name": "Vincent Yuan"},
        "projects": [{"title": "Sumi-OS"}],
        "experience": [],
        "philosophy": [],
    }

    class MockResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return mock_payload

    class MockAsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert url == "/rpc/get_portfolio_ai_context"
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    yaml_result = await fetch_from_supabase_async()
    assert "candidate: Vincent Yuan" in yaml_result
    assert "Sumi-OS" in yaml_result


def test_tool_registration_for_roles():
    guest_tools = [t.get("name") for t in get_agent_tools(is_admin=False) if "name" in t]
    assert "get_vincent_info" in guest_tools
    assert "get_resume" in guest_tools
    assert "get_champ_tier_list" not in guest_tools
    # AI cache invalidation tool is intentionally omitted since cache invalidation is automated via webhooks
    assert "invalidate_portfolio_cache" not in guest_tools

    admin_tools = [t.get("name") for t in get_agent_tools(is_admin=True) if "name" in t]
    assert "get_vincent_info" in admin_tools
    assert "get_resume" in admin_tools
    assert "get_champ_tier_list" not in admin_tools
    assert "invalidate_portfolio_cache" not in admin_tools


def test_portfolio_service_caching_and_invalidation():
    # 1. Invalidate initially
    invalidate_portfolio_cache()
    status_before = get_cache_status()
    assert status_before["is_cached"] is False
    assert status_before["cached_at"] is None

    # 2. First call: fetches from Supabase and caches
    ctx1 = get_portfolio_context()
    assert len(ctx1) > 0
    assert "Vincent Yuan" in ctx1
    assert "profile:" in ctx1
    assert "projects:" in ctx1

    status_after = get_cache_status()
    assert status_after["is_cached"] is True
    assert status_after["cached_at"] is not None
    cached_timestamp = status_after["cached_at"]

    # 3. Second call: should serve identical cached content with same timestamp
    ctx2 = get_portfolio_context()
    assert ctx1 == ctx2
    assert get_cache_status()["cached_at"] == cached_timestamp

    # 4. Invalidate cache
    inv_res = invalidate_portfolio_cache()
    assert inv_res["status"] == "success"
    assert inv_res["was_cached"] is True
    assert get_cache_status()["is_cached"] is False

    # 5. Subsequent call: repopulates cache with fresh data
    ctx3 = get_portfolio_context()
    assert len(ctx3) > 0
    assert get_cache_status()["is_cached"] is True


def test_supabase_webhook_invalidate_endpoint():
    webhook_secret = settings.SUPABASE_WEBHOOK_SECRET.get_secret_value() if settings.SUPABASE_WEBHOOK_SECRET else ""

    # Ensure cache has data first
    get_portfolio_context()
    assert get_cache_status()["is_cached"] is True

    # 1. Request with invalid secret should be 401 Unauthorized
    res_bad = client.post(
        "/api/v1/webhook/supabase-invalidate",
        headers={"X-Webhook-Secret": "wrong_secret_123"},
        json={"type": "UPDATE", "table": "projects"},
    )
    assert res_bad.status_code == 401
    assert "Unauthorized" in res_bad.json()["detail"]

    # 2. Request with valid X-Webhook-Secret header
    res_good_header = client.post(
        "/api/v1/webhook/supabase-invalidate",
        headers={"X-Webhook-Secret": webhook_secret},
        json={"type": "UPDATE", "table": "projects"},
    )
    assert res_good_header.status_code == 200
    data = res_good_header.json()
    assert data["status"] == "success"
    assert data["table"] == "projects"
    assert data["event_type"] == "UPDATE"
    assert data["was_cached"] is True

    # Cache should now be invalidated
    assert get_cache_status()["is_cached"] is False

    # Repopulate cache
    get_portfolio_context()
    assert get_cache_status()["is_cached"] is True

    # 3. Request with Bearer token authorization header
    res_good_bearer = client.post(
        "/api/v1/webhook/supabase-invalidate",
        headers={"Authorization": f"Bearer {webhook_secret}"},
        json={"type": "DELETE", "table": "experience"},
    )
    assert res_good_bearer.status_code == 200
    data_bearer = res_good_bearer.json()
    assert data_bearer["status"] == "success"
    assert data_bearer["table"] == "experience"
    assert data_bearer["event_type"] == "DELETE"
    assert data_bearer["was_cached"] is True

    # Verify cache is cleared again
    assert get_cache_status()["is_cached"] is False


def test_admin_cache_status_endpoint():
    # 1. Guest access is forbidden
    res_guest = client.get("/api/v1/admin/cache/status")
    assert res_guest.status_code == 403

    # 2. Admin access returns cache status
    admin_token = create_mock_jwt(email="vincentyuan1020@gmail.com")
    res = client.get(
        "/api/v1/admin/cache/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "is_cached" in data
    assert "content_length_chars" in data
