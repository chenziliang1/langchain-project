"""
News Scraper — Fetch and summarize news content from event SOURCEURLs.

Provides async article fetching with:
- Timeout and size limits
- Smart content extraction (BeautifulSoup + fallback)
- In-memory URL cache (TTL 1 hour)
- ChromaDB fallback when URL fetch fails
- Batch fetching with concurrency control
"""

import asyncio
import hashlib
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import aiohttp
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FETCH_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)
MAX_CONCURRENT_FETCHES = 5
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB
MIN_ARTICLE_LENGTH = 150
MAX_ARTICLE_LENGTH = 12000  # Increased from 8000 for fuller content
CACHE_TTL_SECONDS = 3600  # 1 hour
# Content snippet shown in UI preview (expandable to full content)
MAX_SNIPPET_LENGTH = 800  # Increased from 500 for more meaningful previews

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    content: str
    title: Optional[str]
    fetched_at: float
    status: str  # "success" | "failed"


class _URLCache:
    """Simple in-memory TTL cache for fetched article content."""

    def __init__(self, ttl: float = CACHE_TTL_SECONDS):
        self._store: Dict[str, _CacheEntry] = {}
        self._ttl = ttl

    def _key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def get(self, url: str) -> Optional[_CacheEntry]:
        key = self._key(url)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() - entry.fetched_at > self._ttl:
            del self._store[key]
            return None
        return entry

    def set(self, url: str, content: str, title: Optional[str], status: str) -> None:
        self._store[self._key(url)] = _CacheEntry(
            content=content, title=title, fetched_at=time.time(), status=status
        )

    def clear(self) -> None:
        self._store.clear()

    def stats(self) -> Dict[str, Any]:
        now = time.time()
        valid = sum(1 for e in self._store.values() if now - e.fetched_at <= self._ttl)
        return {"total": len(self._store), "valid": valid, "ttl_seconds": self._ttl}


# Global cache instance
_url_cache = _URLCache()


# ---------------------------------------------------------------------------
# Content Extraction
# ---------------------------------------------------------------------------

def _extract_article_text(html: str) -> tuple[str, Optional[str]]:
    """Extract article text and title from HTML using BeautifulSoup.

    Returns (text, title).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style/nav/footer/header tags
    for tag_name in ("script", "style", "nav", "footer", "header", "aside", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Try to get title
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    # Fallback: h1
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    # Extract paragraphs — prioritize article/main/content divs
    text_parts = []

    # Strategy 1: look for article/main/content containers
    for container_name in ("article", "main", "[role='main']"):
        if container_name.startswith("["):
            container = soup.find(attrs={"role": "main"})
        else:
            container = soup.find(container_name)
        if container:
            paragraphs = container.find_all("p")
            if len(paragraphs) >= 3:
                text_parts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
                break

    # Strategy 2: all paragraphs, weighted by parent class hints
    if not text_parts:
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 20:
                # Boost score if parent has article/content classes
                parent = p.find_parent()
                boost = 1.0
                if parent and parent.get("class"):
                    cls = " ".join(parent.get("class", [])).lower()
                    if any(k in cls for k in ("article", "content", "story", "body", "text")):
                        boost = 2.0
                    elif any(k in cls for k in ("comment", "sidebar", "widget", "ad", "nav")):
                        boost = 0.3
                text_parts.append(text)

    article_text = " ".join(text_parts)

    # Clean up whitespace
    article_text = " ".join(article_text.split())

    return article_text, title


# ---------------------------------------------------------------------------
# Async Fetch
# ---------------------------------------------------------------------------

async def _fetch_article_raw(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """Fetch a single article with full error handling.

    Returns dict with keys: url, content, title, status, error.
    """
    # Check cache first
    cached = _url_cache.get(url)
    if cached:
        return {
            "url": url,
            "content": cached.content,
            "title": cached.title,
            "status": f"cached_{cached.status}",
            "error": None,
        }

    async with semaphore:
        try:
            async with session.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True) as resp:
                if resp.status != 200:
                    _url_cache.set(url, "", None, "failed")
                    return {
                        "url": url,
                        "content": "",
                        "title": None,
                        "status": f"http_{resp.status}",
                        "error": f"HTTP {resp.status}",
                    }

                # Check content length header
                cl = resp.headers.get("Content-Length")
                if cl and int(cl) > MAX_CONTENT_LENGTH:
                    _url_cache.set(url, "", None, "failed")
                    return {
                        "url": url,
                        "content": "",
                        "title": None,
                        "status": "too_large",
                        "error": f"Content-Length {int(cl)} > {MAX_CONTENT_LENGTH}",
                    }

                html = await resp.text()
                if len(html) > MAX_CONTENT_LENGTH:
                    _url_cache.set(url, "", None, "failed")
                    return {
                        "url": url,
                        "content": "",
                        "title": None,
                        "status": "too_large",
                        "error": f"Downloaded size {len(html)} > {MAX_CONTENT_LENGTH}",
                    }

                text, title = _extract_article_text(html)

                if len(text) < MIN_ARTICLE_LENGTH:
                    _url_cache.set(url, "", title, "failed")
                    return {
                        "url": url,
                        "content": "",
                        "title": title,
                        "status": "too_short",
                        "error": f"Extracted text {len(text)} chars < {MIN_ARTICLE_LENGTH}",
                    }

                # Truncate if too long
                if len(text) > MAX_ARTICLE_LENGTH:
                    text = text[:MAX_ARTICLE_LENGTH] + "..."

                _url_cache.set(url, text, title, "success")
                return {
                    "url": url,
                    "content": text,
                    "title": title,
                    "status": "success",
                    "error": None,
                }

        except asyncio.TimeoutError:
            _url_cache.set(url, "", None, "failed")
            return {
                "url": url,
                "content": "",
                "title": None,
                "status": "timeout",
                "error": "Request timeout",
            }
        except Exception as e:
            _url_cache.set(url, "", None, "failed")
            return {
                "url": url,
                "content": "",
                "title": None,
                "status": "error",
                "error": str(e)[:200],
            }


# ---------------------------------------------------------------------------
# ChromaDB Fallback
# ---------------------------------------------------------------------------

async def _chroma_fallback(query: str, n_results: int = 3) -> List[Dict[str, Any]]:
    """Fallback to ChromaDB vector search when URL fetch fails."""
    try:
        from backend.queries.core_queries import query_search_news_context
        result = await query_search_news_context(query, n_results)
        if result.get("error"):
            return []
        return result.get("results", [])
    except Exception as e:
        print(f"[NewsScraper] ChromaDB fallback failed: {e}", flush=True)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class NewsScraper:
    """Fetch and summarize news content from event SOURCEURLs."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_FETCHES):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # -- Single article --

    async def fetch_article(self, url: str) -> Dict[str, Any]:
        """Fetch a single article by URL.

        Returns dict with keys: url, content, title, status, error.
        """
        async with aiohttp.ClientSession() as session:
            return await _fetch_article_raw(session, url, self._semaphore)

    # -- Event-based fetching --

    async def fetch_for_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch news for a single event.

        Tries SOURCEURL first, falls back to ChromaDB search by event headline.
        Returns structured coverage data.
        """
        ed = event.get("event_data") or event
        url = ed.get("SOURCEURL") if isinstance(ed, dict) else None
        headline = event.get("headline") or (
            f"{ed.get('Actor1Name', '')} {ed.get('Actor2Name', '')}" if isinstance(ed, dict) else ""
        )
        event_id = ed.get("GlobalEventID") if isinstance(ed, dict) else None

        sources = []
        primary_content = ""

        # 1. Try SOURCEURL
        if url:
            result = await self.fetch_article(url)
            if result["status"] == "success":
                snippet = result["content"][:MAX_SNIPPET_LENGTH] + "..." if len(result["content"]) > MAX_SNIPPET_LENGTH else result["content"]
                sources.append({
                    "url": result["url"],
                    "title": result["title"],
                    "content_snippet": snippet,
                    "content_full": result["content"],  # Full content for expandable view
                    "fetch_status": "success",
                })
                primary_content = result["content"]
            else:
                sources.append({
                    "url": result["url"],
                    "title": result["title"],
                    "content_snippet": "",
                    "fetch_status": result["status"],
                    "error": result["error"],
                })

        # 2. ChromaDB fallback if no successful fetch
        if not primary_content and headline:
            chroma_results = await _chroma_fallback(headline, n_results=3)
            for r in chroma_results:
                chroma_content = r.get("content", "")
                snippet = chroma_content[:MAX_SNIPPET_LENGTH] + "..." if len(chroma_content) > MAX_SNIPPET_LENGTH else chroma_content
                sources.append({
                    "url": r.get("source_url", ""),
                    "title": r.get("title", None),
                    "content_snippet": snippet,
                    "content_full": chroma_content,  # Full content for expandable view
                    "fetch_status": "chroma_fallback",
                })
                if not primary_content:
                    primary_content = r.get("content", "")

        return {
            "event_id": event_id,
            "headline": headline,
            "sources": sources,
            "primary_content": primary_content,
            "source_count": len(sources),
            "has_content": bool(primary_content),
        }

    async def fetch_for_events(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Batch fetch news for multiple events with shared session."""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for event in events:
                ed = event.get("event_data") or event
                url = ed.get("SOURCEURL") if isinstance(ed, dict) else None
                if url:
                    tasks.append(_fetch_article_raw(session, url, self._semaphore))
                else:
                    # No URL — will be handled as empty
                    tasks.append(asyncio.sleep(0))  # placeholder

            results = await asyncio.gather(*tasks, return_exceptions=True)

        coverage_list = []
        for event, result in zip(events, results):
            if isinstance(result, Exception):
                coverage_list.append({
                    "event_id": event.get("GlobalEventID"),
                    "headline": event.get("headline"),
                    "sources": [],
                    "primary_content": "",
                    "source_count": 0,
                    "has_content": False,
                    "error": str(result),
                })
                continue

            # result is a dict from _fetch_article_raw
            if isinstance(result, dict) and result.get("status") == "success":
                coverage_list.append({
                    "event_id": event.get("GlobalEventID"),
                    "headline": event.get("headline"),
                    "sources": [{
                        "url": result["url"],
                        "title": result["title"],
                        "content_snippet": result["content"][:500] + "..." if len(result["content"]) > 500 else result["content"],
                        "fetch_status": "success",
                    }],
                    "primary_content": result["content"],
                    "source_count": 1,
                    "has_content": True,
                })
            else:
                # Try ChromaDB fallback
                headline = event.get("headline") or ""
                chroma_results = await _chroma_fallback(headline, n_results=2) if headline else []
                sources = []
                primary = ""
                for r in chroma_results:
                    sources.append({
                        "url": r.get("source_url", ""),
                        "title": None,
                        "content_snippet": r.get("content", "")[:500] + "..." if len(r.get("content", "")) > 500 else r.get("content", ""),
                        "fetch_status": "chroma_fallback",
                    })
                    if not primary:
                        primary = r.get("content", "")

                coverage_list.append({
                    "event_id": event.get("GlobalEventID"),
                    "headline": headline,
                    "sources": sources,
                    "primary_content": primary,
                    "source_count": len(sources),
                    "has_content": bool(primary),
                })

        return coverage_list

    # -- Utilities --

    @staticmethod
    def cache_stats() -> Dict[str, Any]:
        return _url_cache.stats()

    @staticmethod
    def clear_cache() -> None:
        _url_cache.clear()


# Singleton
news_scraper = NewsScraper()
