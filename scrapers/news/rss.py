"""
scrapers/news/rss.py — AI Radar
Sources: Anthropic · OpenAI · DeepMind · TLDR AI · TechCrunch · Import AI
Method:  feedparser for feed metadata + Crawl4AI for full article content
Auth:    None required
"""
import re
import asyncio
import concurrent.futures
import feedparser
import hashlib
from datetime import datetime

SOURCE_DISPLAY_NAMES = {
    "anthropic":       "Anthropic",
    "openai":          "OpenAI",
    "google_deepmind": "Google DeepMind",
    "tldr_ai":         "TLDR AI",
    "techcrunch_ai":   "TechCrunch AI",
    "import_ai":       "Import AI",
}


def _run_crawl4ai(url: str) -> str:
    """Runs Crawl4AI in a fresh event loop — safe for Windows and Jupyter."""
    async def _crawl():
        from crawl4ai import AsyncWebCrawler
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
            return result.markdown

    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_crawl()) or ""
    except Exception as e:
        return f"[Scrape failed: {e}]"
    finally:
        loop.close()


def _scrape_article(url: str) -> str:
    """Fetches full article content via Crawl4AI in a thread."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_crawl4ai, url).result(timeout=30)
    except Exception as e:
        return f"[Scrape failed: {e}]"


def scrape(source: str, url: str, limit: int = 5, **kwargs) -> list[dict]:
    """
    Fetch articles from an RSS feed and scrape full content.

    Args:
        source: NewsSource key e.g. 'anthropic', 'tldr_ai'
        url:    RSS feed URL
        limit:  max articles to return
    """
    feed = feedparser.parse(url)
    entries = feed.entries

    if not entries:
        return []

    results = []

    for entry in entries[:limit]:
        link       = entry.get("link", "")
        published  = entry.get("published", "")
        full_md    = _scrape_article(link)
        word_count = len(full_md.split())

        # Parse date to YYYY-MM-DD
        try:
            from email.utils import parsedate_to_datetime
            pub_date = parsedate_to_datetime(published).date().isoformat()
        except Exception:
            pub_date = published[:10] if published else None

        results.append({
            "source":             source,
            "id":                 hashlib.sha256(link.encode()).hexdigest(),
            "source_display_name": SOURCE_DISPLAY_NAMES.get(source, source),
            "url":                link,
            "title":              entry.get("title"),
            "full_content":       full_md,
            "content_preview":    full_md[:300],
            "word_count":         word_count,
            "published_date":     pub_date,
        })

    return results
