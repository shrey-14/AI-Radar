"""
scrapers/news/meta_ai.py — AI Radar
Source: Meta AI Blog (ai.meta.com/blog)
Method: Crawl4AI — Meta AI has no RSS feed
Auth:   None required
"""
import re
import asyncio
import concurrent.futures
import hashlib


def _run_crawl4ai(url: str) -> str:
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


def _scrape_url(url: str) -> str:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_crawl4ai, url).result(timeout=60)
    except Exception as e:
        return f"[Scrape failed: {e}]"


def scrape(limit: int = 5, **kwargs) -> list[dict]:
    """Scrape latest articles from Meta AI blog."""

    # Step 1: Crawl listing page to find article links
    listing_md = _scrape_url("https://ai.meta.com/blog/")

    raw_links = re.findall(r'https://ai\.meta\.com/blog/[a-z0-9\-]+/', listing_md)
    seen = set()
    article_links = [
        l for l in raw_links
        if not (l in seen or seen.add(l))
        if l != "https://ai.meta.com/blog/"
    ]

    results = []

    for link in article_links[:limit]:
        full_md    = _scrape_url(link)
        word_count = len(full_md.split())

        title_match = re.search(r'^#\s+(.+)', full_md, re.MULTILINE)
        title = (
            title_match.group(1)
            if title_match
            else link.split("/")[-2].replace("-", " ").title()
        )

        results.append({
            "source":              "meta_ai",
            "id":                  hashlib.sha256(link.encode()).hexdigest(),
            "source_display_name": "Meta AI",
            "url":                 link,
            "title":               title,
            "full_content":        full_md,
            "content_preview":     full_md[:300],
            "word_count":          word_count,
            "published_date":      None,   # Meta AI blog doesn't expose dates in markup
        })

    return results
