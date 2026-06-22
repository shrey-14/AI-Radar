"""
scrapers/benchmarks/lmsys.py — AI Radar
Source: LMSYS Chatbot Arena (arena.ai/leaderboard/text)
Method: Crawl4AI with JS delay — page is fully JS-rendered
Auth:   None required
"""
import re
import asyncio
import concurrent.futures


def _crawl_arena() -> str:
    async def _run():
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        config = CrawlerRunConfig(delay_before_return_html=5.0, page_timeout=45000)
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url="https://arena.ai/leaderboard/text", config=config)
            md = result.markdown
            return md.raw_markdown if hasattr(md, "raw_markdown") else str(md)

    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run()) or ""
    finally:
        loop.close()


def scrape(limit: int = 20, **kwargs) -> list[dict]:
    """Fetch current Chatbot Arena leaderboard rankings."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        md = pool.submit(_crawl_arena).result(timeout=90)

    models  = []

    for line in md.split("\n"):
        line = line.strip()
        if not line.startswith("|") or "---" in line or "Rank" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 6:
            continue
        try:
            rank = int(cols[0])
        except ValueError:
            continue

        model_col  = cols[2]
        name_m     = re.search(r"\[([^\]]+)\]", model_col)
        url_m      = re.search(r"\(([^)]+)\)", model_col)
        model_name = name_m.group(1) if name_m else model_col
        model_url  = url_m.group(1).split('"')[0].strip() if url_m else None

        after_link   = re.sub(r"\[.*?\]\(.*?\)", "", model_col).strip()
        parts        = [p.strip() for p in re.split(r" · ", after_link) if p.strip()]
        org          = parts[0] if parts else None
        license_type = parts[1] if len(parts) > 1 else None

        score_m   = re.search(r"(\d+)", cols[3])
        ci_m      = re.search(r"±(\d+)", cols[3])
        elo_score = float(score_m.group(1)) if score_m else None
        elo_ci    = float(ci_m.group(1))    if ci_m    else None

        votes_raw = cols[4].replace(",", "").strip()
        try:
            num_votes = int(votes_raw)
        except ValueError:
            num_votes = None

        price_m     = re.findall(r"\d+\.?\d*", cols[5])
        input_cost  = float(price_m[0]) if len(price_m) > 0 else None
        output_cost = float(price_m[1]) if len(price_m) > 1 else None
        context     = cols[6].strip() if len(cols) > 6 else None

        models.append({
            "source":              "lmsys_arena",
            "id":                  f"lmsys_{model_name.lower().replace(' ', '_').replace('/', '_')}",
            "model_id":            model_name,
            "model_display_name":  model_name,
            "leaderboard_url":     model_url,
            "organisation":        org,
            "license":             license_type,
            "arena_rank":          rank,
            "elo_score":           elo_score,
            "elo_ci":              elo_ci,
            "num_votes":           num_votes,
            "input_cost_per_1m":   input_cost,
            "output_cost_per_1m":  output_cost,
            "context_window":      context,
        })

        if len(models) >= limit:
            break

    return models
