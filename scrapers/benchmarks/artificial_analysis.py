"""
scrapers/benchmarks/artificial_analysis.py — AI Radar
Source: Artificial Analysis (artificialanalysis.ai)
Method: Crawl4AI — main page to find model slugs, then per-model pages
Auth:   None required
"""
import re
import asyncio
import concurrent.futures


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
    finally:
        loop.close()


def _scrape(url: str) -> str:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_crawl4ai, url).result(timeout=60)
    except Exception as e:
        return ""


def _parse_model(md: str, slug: str) -> dict:
    def find(patterns):
        for pat in patterns:
            m = re.search(pat, md, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    intel    = find([r"(\d+\.?\d*)\s*Artificial Analysis Intelligence Index",
                     r"Intelligence Index[^\d]*(\d+\.?\d*)"])
    speed    = find([r"(\d+\.?\d*)\s*Output tokens per second"])
    in_price = find([r"Input Price[^\$]*\$(\d+\.?\d*)",
                     r"\$(\d+\.?\d*)\s*USD per 1M tokens\s*Cache"])
    out_price= find([r"Output Price[^\$]*\$(\d+\.?\d*)"])
    context  = find([r"(\d[\d,\.]+[kKmM]?)\s*(?:token)?\s*context",
                     r"Context window[^\d]*(\d[\d,]+)"])
    provider = find([r"^([A-Za-z][\w\s]+)\s*[•·]\s*(?:Proprietary|Open)"])
    released = find([r"Released\s+([A-Za-z]+\s+\d{4})"])

    return {
        "source":              "artificial_analysis",
        "id":                  f"aa_{slug}",
        "model_id":            slug,
        "model_display_name":  slug.replace("-", " ").title(),
        "leaderboard_url":     f"https://artificialanalysis.ai/models/{slug}",
        "organisation":        provider,
        "intelligence_score":  float(intel)    if intel    else None,
        "speed_tps":           float(speed)    if speed    else None,
        "input_cost_per_1m":   float(in_price) if in_price else None,
        "output_cost_per_1m":  float(out_price)if out_price else None,
        "context_window":      context,
        "released_date":       released,
    }


def scrape(limit: int = 15, **kwargs) -> list[dict]:
    """Fetch intelligence/speed/cost data from Artificial Analysis."""

    # Step 1: Get model slugs from main page
    main_md = _scrape("https://artificialanalysis.ai")
    slugs   = re.findall(r'\(https://artificialanalysis\.ai/models/([^)]+)\)', main_md)
    seen    = set()
    unique  = [s for s in slugs if not (s in seen or seen.add(s))]

    # Step 2: Scrape individual model pages
    results = []
    for slug in unique[:limit]:
        md   = _scrape(f"https://artificialanalysis.ai/models/{slug}")
        data = _parse_model(md, slug)
        if data["intelligence_score"] is not None:   # only include parseable entries
            results.append(data)

    return results
