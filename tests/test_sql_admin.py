import pytest
import time
import jwt
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db_service import validate_safe_sql, execute_supabase_sql_async, execute_supabase_sql
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


# =============================================================================
# 1. SQL SAFETY VALIDATION TESTS
# =============================================================================

def test_validate_safe_sql_valid_queries():
    # Valid SELECT
    assert validate_safe_sql("SELECT * FROM projects WHERE id = 'akari-commerce';") is None

    # Valid UPDATE with dollar-quoting
    sql_update = """
    UPDATE projects 
    SET title = $$New Project Title$$, updated_at = NOW() 
    WHERE id = $$akari-commerce$$;
    """
    assert validate_safe_sql(sql_update) is None

    # Valid INSERT with array casting
    sql_insert = """
    INSERT INTO projects (id, title, tech_stacks, display_order)
    VALUES ($$test-proj$$, $$Test Title$$, ARRAY['React', 'Vite']::text[], 5);
    """
    assert validate_safe_sql(sql_insert) is None

    # Valid DELETE with WHERE clause
    assert validate_safe_sql("DELETE FROM projects WHERE id = 'old-proj';") is None


def test_validate_safe_sql_blocks_forbidden_commands():
    # DROP TABLE
    err = validate_safe_sql("DROP TABLE projects;")
    assert err is not None
    assert "forbidden command 'DROP'" in err

    # TRUNCATE
    err = validate_safe_sql("TRUNCATE TABLE experience;")
    assert err is not None
    assert "forbidden command 'TRUNCATE'" in err

    # ALTER TABLE
    err = validate_safe_sql("ALTER TABLE projects ADD COLUMN new_col text;")
    assert err is not None
    assert "forbidden command 'ALTER'" in err

    # GRANT
    err = validate_safe_sql("GRANT ALL ON projects TO public;")
    assert err is not None
    assert "forbidden command 'GRANT'" in err


def test_validate_safe_sql_blocks_forbidden_schemas():
    # System auth table
    err = validate_safe_sql("SELECT * FROM auth.users;")
    assert err is not None
    assert "Security violation" in err

    # Storage schema
    err = validate_safe_sql("DELETE FROM storage.objects WHERE id = 'abc';")
    assert err is not None
    assert "Security violation" in err

    # Internal contact_rate_limits
    err = validate_safe_sql("SELECT * FROM contact_rate_limits;")
    assert err is not None
    assert "Security violation" in err


def test_validate_safe_sql_blocks_unconditioned_delete():
    # Unconditioned DELETE on projects
    err = validate_safe_sql("DELETE FROM projects;")
    assert err is not None
    assert "Unbounded DELETE" in err

    # Unconditioned DELETE on experience
    err = validate_safe_sql("DELETE FROM experience")
    assert err is not None
    assert "Unbounded DELETE" in err


def test_validate_safe_sql_blocks_unauthorized_tables():
    # Table outside the allowed whitelist
    err = validate_safe_sql("SELECT * FROM secret_financial_records;")
    assert err is not None
    assert "Access restricted" in err


# =============================================================================
# 2. TOOL ACCESS & ROLE-BASED VISIBILITY TESTS
# =============================================================================

def test_admin_tool_visibility():
    # Guest / Non-admin tools
    guest_tools = get_agent_tools(is_admin=False)
    guest_tool_names = [t["name"] for t in guest_tools]
    assert "get_vincent_info" in guest_tool_names
    assert "get_resume" in guest_tool_names
    assert "get_champ_tier_list" in guest_tool_names
    assert "execute_supabase_sql" not in guest_tool_names

    # Admin tools
    admin_tools = get_agent_tools(is_admin=True)
    admin_tool_names = [t["name"] for t in admin_tools]
    assert "execute_supabase_sql" in admin_tool_names
    assert "execute_supabase_sql" in TOOL_FUNCTIONS


# =============================================================================
# 3. SUPABASE SQL EXECUTION & CACHE INVALIDATION
# =============================================================================

@pytest.mark.asyncio
async def test_execute_supabase_sql_async_mutation(monkeypatch):
    import httpx
    from app.portfolio_service import get_cache_status, get_portfolio_context

    # Pre-populate cache
    monkeypatch.setattr("app.portfolio_service.fetch_from_supabase", lambda: "cached: true")
    get_portfolio_context(force_refresh=True)
    assert get_cache_status()["is_cached"] is True

    # Mock httpx response from Supabase RPC
    class MockResponse:
        status_code = 200
        def json(self):
            return {"status": "success", "message": "Query executed successfully"}
        @property
        def text(self):
            return ""

    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def post(self, url, headers=None, json=None):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: MockAsyncClient())

    result = await execute_supabase_sql_async("UPDATE projects SET updated_at = NOW() WHERE id = 'akari-commerce';")
    assert result["status"] == "success"

    # Verify server cache was invalidated on mutation
    assert get_cache_status()["is_cached"] is False


@pytest.mark.asyncio
async def test_execute_supabase_sql_async_postgres_error(monkeypatch):
    import httpx

    class MockErrorResponse:
        status_code = 200
        def json(self):
            return {"status": "error", "message": "relation 'non_existent' does not exist"}
        @property
        def text(self):
            return '{"status": "error", "message": "relation does not exist"}'

    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def post(self, url, headers=None, json=None):
            return MockErrorResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: MockAsyncClient())
    result = await execute_supabase_sql_async("SELECT syntax_error FROM projects WHERE id = 1;")
    assert result["status"] == "error"
    assert result["error_type"] == "POSTGRES_ERROR"
    assert "relation 'non_existent' does not exist" in result["message"]


def test_non_admin_cannot_access_sql_tool():
    # Regular authenticated user (logged in, but not in admin list)
    guest_tools = get_agent_tools(is_admin=False)
    assert not any(t["name"] == "execute_supabase_sql" for t in guest_tools)

    # Admin user
    admin_tools = get_agent_tools(is_admin=True)
    assert any(t["name"] == "execute_supabase_sql" for t in admin_tools)
