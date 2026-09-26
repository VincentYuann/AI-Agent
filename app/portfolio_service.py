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
_cached_resume_text: Optional[str] = None
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


async def fetch_resume_from_supabase_async() -> Optional[str]:
    """
    Fetches the live resume content (LaTeX or formatted text) from Supabase public.resume_latex.
    """
    supabase_url = (settings.SUPABASE_URL or "").rstrip("/")
    if not supabase_url:
        return None

    anon_key = settings.SUPABASE_ANON_KEY.get_secret_value() if settings.SUPABASE_ANON_KEY else ""
    if not anon_key:
        return None

    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
    }
    base_rest_url = f"{supabase_url}/rest/v1"

    try:
        async with httpx.AsyncClient(base_url=base_rest_url, headers=headers, timeout=8.0) as client:
            res = await client.get("/resume_latex?id=eq.1&select=latex,content,resume_link")
            if res.status_code == 200:
                data = res.json()
                if data and isinstance(data, list) and len(data) > 0:
                    row = data[0]
                    content = row.get("latex") or row.get("content") or ""
                    link = row.get("resume_link") or ""
                    if content and content.strip():
                        prefix = f"[Live Resume Link: {link}]\n\n" if link else ""
                        logger.info("Successfully fetched live resume from Supabase public.resume_latex.")
                        return prefix + content.strip()
    except Exception as e:
        logger.warning(f"Error fetching live resume from Supabase: {e}")
    return None


def fetch_resume_from_supabase() -> Optional[str]:
    """
    Thread-safe synchronous bridge for fetch_resume_from_supabase_async.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(fetch_resume_from_supabase_async())).result()
    return asyncio.run(fetch_resume_from_supabase_async())


def get_live_resume_context(fallback_fn=None) -> str:
    """
    Returns the live resume from Supabase public.resume_latex if available;
    falls back to local asset loader (PDF) if Supabase is unreachable or empty.
    """
    global _cached_resume_text
    if _cached_resume_text is not None:
        return _cached_resume_text

    with _lock:
        if _cached_resume_text is not None:
            return _cached_resume_text

        live_text = fetch_resume_from_supabase()
        if live_text and live_text.strip():
            _cached_resume_text = live_text
            return _cached_resume_text

        if fallback_fn:
            _cached_resume_text = fallback_fn()
            return _cached_resume_text

        return "Resume document not available."


def invalidate_portfolio_cache() -> Dict[str, Any]:
    """
    Invalidates the server-side portfolio cache (both portfolio data and live resume).
    Called when a database webhook fires or an admin triggers a refresh.
    """
    global _cached_portfolio_yaml, _cached_resume_text, _cached_at
    with _lock:
        was_cached = (_cached_portfolio_yaml is not None) or (_cached_resume_text is not None)
        _cached_portfolio_yaml = None
        _cached_resume_text = None
        _cached_at = None
        # Also clear any cached prompt markdown files from memory
        from .config import load_prompt_file
        load_prompt_file.cache_clear()

        timestamp = time.time()
        logger.info("Portfolio knowledge, resume, and prompt markdown caches invalidated.")
        return {
            "status": "success",
            "was_cached": was_cached,
            "invalidated_at": timestamp,
            "message": "Portfolio, resume, and prompt markdown caches invalidated successfully. Next inquiry will fetch fresh database state.",
        }


def get_cache_status() -> Dict[str, Any]:
    """Returns metadata regarding the server cache state."""
    with _lock:
        is_cached = _cached_portfolio_yaml is not None
        age_seconds = (time.time() - _cached_at) if _cached_at else None
        length = len(_cached_portfolio_yaml) if _cached_portfolio_yaml else 0
        return {
            "is_cached": is_cached,
            "is_resume_cached": _cached_resume_text is not None,
            "cached_at": _cached_at,
            "age_seconds": round(age_seconds, 2) if age_seconds is not None else None,
            "content_length_chars": length,
        }
