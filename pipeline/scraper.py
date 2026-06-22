import logging
from config import settings

log = logging.getLogger(__name__)


def scrape_section(section: str, limit: int) -> list[dict]:
    """
    Scrapes all sources for a section and returns a flat list of raw dicts.
    Sources that fail are logged and skipped — other sources keep running.

    Args:
        section: 'papers' | 'news' | 'tools' | 'benchmarks' | 'talks'
        limit:   max total items to return across all sources in this section

    Returns:
        List of raw dicts (unvalidated — Pydantic validation happens in flow.py)
    """
    dispatch = {
        "papers":     _scrape_papers,
        "news":       _scrape_news,
        "tools":      _scrape_tools,
        "benchmarks": _scrape_benchmarks,
        "talks":      _scrape_talks,
    }

    if section not in dispatch:
        raise ValueError(f"Unknown section '{section}'")

    return dispatch[section](limit)


# ── Per-section scrapers ──────────────────────────────────────────

def _scrape_papers(limit: int) -> list[dict]:
    """Scrapes arXiv, HF Daily Papers, OpenReview."""
    from scrapers.papers.arxiv import scrape as arxiv_scrape
    from scrapers.papers.hf_papers import scrape as hf_scrape
    from scrapers.papers.openreview import scrape as openreview_scrape

    per_source = max(1, limit // 3)
    results = []

    for name, fn in [
        ("arXiv",       arxiv_scrape),
        ("HF Papers",   hf_scrape),
        ("OpenReview",  openreview_scrape),
    ]:
        try:
            items = fn(limit=per_source)
            log.info(f"[papers] {name}: {len(items)} items")
            results.extend(items)
        except Exception as e:
            log.error(f"[papers] {name} failed: {e}")

    return results[:limit]


def _scrape_news(limit: int) -> list[dict]:
    """Scrapes 7 news sources via RSS and Crawl4AI."""
    from scrapers.news.rss import scrape as rss_scrape
    from scrapers.news.meta_ai import scrape as meta_scrape

    # 6 RSS sources + 1 Crawl4AI (Meta AI)
    RSS_SOURCES = {
        "anthropic":       "https://raw.githubusercontent.com/taobojlen/anthropic-rss-feed/main/anthropic_news_rss.xml",
        "openai":          "https://openai.com/news/rss.xml",
        "google_deepmind": "https://deepmind.google/blog/rss.xml",
        "tldr_ai":         "https://tldr.tech/api/rss/ai",
        "techcrunch_ai":   "https://techcrunch.com/category/artificial-intelligence/feed/",
        "import_ai":       "https://importai.substack.com/feed",
    }

    per_source = max(1, limit // 7)
    results = []

    for source_key, feed_url in RSS_SOURCES.items():
        try:
            items = rss_scrape(source=source_key, url=feed_url, limit=per_source)
            log.info(f"[news] {source_key}: {len(items)} items")
            results.extend(items)
        except Exception as e:
            log.error(f"[news] {source_key} RSS failed: {e}")

    # Meta AI via Crawl4AI (no RSS)
    try:
        items = meta_scrape(limit=per_source)
        log.info(f"[news] meta_ai: {len(items)} items")
        results.extend(items)
    except Exception as e:
        log.error(f"[news] meta_ai Crawl4AI failed: {e}")

    return results[:limit]


def _scrape_tools(limit: int) -> list[dict]:
    """Scrapes GitHub Trending, HF Hub, HF Spaces, Product Hunt."""
    from scrapers.tools.github_trending import scrape as github_scrape
    from scrapers.tools.hf_hub import scrape as hf_hub_scrape
    from scrapers.tools.hf_spaces import scrape as hf_spaces_scrape
    from scrapers.tools.product_hunt import scrape as ph_scrape

    per_source = max(1, limit // 4)
    results = []

    for name, fn in [
        ("GitHub Trending", github_scrape),
        ("HF Hub",          hf_hub_scrape),
        ("HF Spaces",       hf_spaces_scrape),
        ("Product Hunt",    ph_scrape),
    ]:
        try:
            items = fn(limit=per_source)
            log.info(f"[tools] {name}: {len(items)} items")
            results.extend(items)
        except Exception as e:
            log.error(f"[tools] {name} failed: {e}")

    return results[:limit]


def _scrape_benchmarks(limit: int) -> list[dict]:
    """Scrapes Open LLM Leaderboard, LMSYS Arena, Artificial Analysis."""
    from scrapers.benchmarks.open_llm import scrape as open_llm_scrape
    from scrapers.benchmarks.lmsys import scrape as lmsys_scrape
    from scrapers.benchmarks.artificial_analysis import scrape as aa_scrape

    per_source = max(1, limit // 3)
    results = []

    for name, fn in [
        ("Open LLM Leaderboard", open_llm_scrape),
        ("LMSYS Arena",          lmsys_scrape),
        ("Artificial Analysis",  aa_scrape),
    ]:
        try:
            items = fn(limit=per_source)
            log.info(f"[benchmarks] {name}: {len(items)} items")
            results.extend(items)
        except Exception as e:
            log.error(f"[benchmarks] {name} failed: {e}")

    return results[:limit]


def _scrape_talks(limit: int) -> list[dict]:
    """Fetches latest videos + transcripts from 4 YouTube channels."""
    from scrapers.talks.youtube import scrape as youtube_scrape

    CHANNELS = {
        "Lex Fridman":       "UCSHZKyawb77ixDdsGog4iWA",
        "Yannic Kilcher":    "UCZHmQk67mSJgfCCTn7xBfew",
        "Two Minute Papers": "UCbfYPyITQ-7l4upoX8nvctg",
        "AI Explained":      "UCNJ1Ymd5yFuUPtn21xtRbbw",
    }

    per_channel = max(1, limit // len(CHANNELS))
    results = []

    for channel_name, channel_id in CHANNELS.items():
        try:
            items = youtube_scrape(
                channel_name=channel_name,
                channel_id=channel_id,
                limit=per_channel,
            )
            log.info(f"[talks] {channel_name}: {len(items)} items")
            results.extend(items)
        except Exception as e:
            log.error(f"[talks] {channel_name} failed: {e}")

    return results[:limit]