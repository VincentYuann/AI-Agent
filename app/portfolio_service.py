import asyncio
import concurrent.futures
import logging
import threading
import time
from typing import Optional, Dict, Any, List
import httpx
import yaml

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global Thread-Safe Server Cache for Portfolio Knowledge
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_cached_portfolio_yaml: Optional[str] = None
_cached_at: Optional[float] = None


async def fetch_from_supabase_async() -> str:
    """
    Fetches the comprehensive portfolio knowledge base directly from the Supabase RPC
    function `get_portfolio_ai_context`.
    
    All field exclusion, relationship aggregation, and heavy asset stripping occur
    exclusively inside PostgreSQL, returning an AI-ready JSON payload that is dumped into YAML.
    """
    supabase_url = (settings.SUPABASE_URL or "").rstrip("/")
    if not supabase_url:
        logger.warning("SUPABASE_URL is not configured in settings.")
        return "Portfolio data unavailable: SUPABASE_URL not configured."

    anon_key = settings.SUPABASE_ANON_KEY.get_secret_value() if settings.SUPABASE_ANON_KEY else ""
    if not anon_key:
        logger.warning("SUPABASE_ANON_KEY is not configured in settings.")
        return "Portfolio data unavailable: SUPABASE_ANON_KEY not configured."

    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
    }
    base_rest_url = f"{supabase_url}/rest/v1"

    async with httpx.AsyncClient(base_url=base_rest_url, headers=headers, timeout=12.0) as client:
        res = await client.post("/rpc/get_portfolio_ai_context")
        res.raise_for_status()
        payload = res.json()
        logger.info("Successfully fetched AI context via Supabase RPC 'get_portfolio_ai_context'.")
        return yaml.dump(payload, sort_keys=False, allow_unicode=True, width=120)


def fetch_from_supabase() -> str:
    """
    Thread-safe synchronous bridge for fetch_from_supabase_async.
    Supports execution inside or outside existing asyncio event loops.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(fetch_from_supabase_async())).result()
    return asyncio.run(fetch_from_supabase_async())


def get_portfolio_context(force_refresh: bool = False) -> str:
    """
    Thread-safe getter for the portfolio knowledge base.
    Serves from in-memory cache if available; queries Supabase and caches upon initial call
    or after an invalidation.
    """
    global _cached_portfolio_yaml, _cached_at

    # Fast path: cache hit without acquiring lock
    if not force_refresh and _cached_portfolio_yaml is not None:
        logger.info("Serving portfolio knowledge base from server RAM cache (YAML).")
        return _cached_portfolio_yaml

    with _lock:
        # Double check after acquiring lock
        if not force_refresh and _cached_portfolio_yaml is not None:
            return _cached_portfolio_yaml

        logger.info("Cache miss: querying Supabase concurrently for portfolio data...")
        try:
            yaml_content = fetch_from_supabase()
            _cached_portfolio_yaml = yaml_content
            _cached_at = time.time()
            logger.info("Portfolio cache successfully updated (YAML).")
            return _cached_portfolio_yaml
        except Exception as e:
            logger.error(f"Error fetching portfolio data from Supabase: {e}", exc_info=True)
            if _cached_portfolio_yaml is not None:
                logger.warning("Returning stale cached portfolio data due to fetch error.")
                return _cached_portfolio_yaml
            return f"Unable to fetch portfolio data from Supabase: {e}"


def invalidate_portfolio_cache() -> Dict[str, Any]:
    """
    Invalidates the server-side portfolio cache.
    Called when a database webhook fires or an admin triggers a refresh.
    """
    global _cached_portfolio_yaml, _cached_at
    with _lock:
        was_cached = _cached_portfolio_yaml is not None
        _cached_portfolio_yaml = None
        _cached_at = None
        timestamp = time.time()
        logger.info("Portfolio cache invalidated.")
        return {
            "status": "success",
            "was_cached": was_cached,
            "invalidated_at": timestamp,
            "message": "Portfolio cache invalidated successfully. Next inquiry will fetch fresh database state.",
        }


def get_cache_status() -> Dict[str, Any]:
    """Returns metadata regarding the server cache state."""
    with _lock:
        is_cached = _cached_portfolio_yaml is not None
        age_seconds = (time.time() - _cached_at) if _cached_at else None
        length = len(_cached_portfolio_yaml) if _cached_portfolio_yaml else 0
        return {
            "is_cached": is_cached,
            "cached_at": _cached_at,
            "age_seconds": round(age_seconds, 2) if age_seconds is not None else None,
            "content_length_chars": length,
        }
