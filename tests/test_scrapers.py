import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Colour helpers ────────────────────────────────────────────────
OK   = "✅"
WARN = "⚠️"
FAIL = "❌"
SKIP = "⏭️"

def green(s):  return f"\033[92m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"

def header(title):
    print(f"\n{'='*62}")
    print(f"  {bold(title)}")
    print(f"{'='*62}")

def result_line(index, total, name, status, count, elapsed, note=""):
    status_str = {
        "ok":   green(f"{OK}  PASS"),
        "warn": yellow(f"{WARN} WARN"),
        "fail": red(f"{FAIL}  FAIL"),
        "skip": f"{SKIP} SKIP",
    }[status]
    count_str   = f"{count:>3} items" if count is not None else "  -      "
    elapsed_str = f"{elapsed:5.1f}s"
    print(f"  [{index:>2}/{total}] {name:<28} {status_str}  {count_str}  {elapsed_str}  {note}")

def preview_item(item: dict, label_field: str = None):
    """Print a compact preview of the first returned item."""
    if not item:
        return
    # find a human-readable label
    label = (
        item.get("title")
        or item.get("name")
        or item.get("model_display_name")
        or item.get("model_id")
        or item.get("id", "")
    )
    print(f"         ↳ {str(label)[:80]}")
    print(f"           fields: {', '.join(list(item.keys())[:10])}{'...' if len(item) > 10 else ''}")


# ── Individual scraper test runners ──────────────────────────────

def test_arxiv(limit=5):
    from scrapers.papers.arxiv import scrape
    return scrape(limit=limit)

def test_hf_papers(limit=5):
    from scrapers.papers.hf_papers import scrape
    return scrape(limit=limit)

def test_openreview(limit=5):
    from scrapers.papers.openreview import scrape
    return scrape(limit=limit)

def test_rss(limit=2):
    from scrapers.news.rss import scrape
    RSS_SOURCES = {
        "anthropic":       "https://raw.githubusercontent.com/taobojlen/anthropic-rss-feed/main/anthropic_news_rss.xml",
        "openai":          "https://openai.com/news/rss.xml",
        "google_deepmind": "https://deepmind.google/blog/rss.xml",
        "tldr_ai":         "https://tldr.tech/api/rss/ai",
        "techcrunch_ai":   "https://techcrunch.com/category/artificial-intelligence/feed/",
        "import_ai":       "https://importai.substack.com/feed",
    }
    results = []
    for source_key, feed_url in RSS_SOURCES.items():
        items = scrape(source=source_key, url=feed_url, limit=limit)
        results.extend(items)
    return results

def test_meta_ai(limit=2):
    from scrapers.news.meta_ai import scrape
    return scrape(limit=limit)

def test_github_trending(limit=5):
    from scrapers.tools.github_trending import scrape
    return scrape(limit=limit)

def test_hf_hub(limit=6):
    from scrapers.tools.hf_hub import scrape
    return scrape(limit=limit)

def test_hf_spaces(limit=5):
    from scrapers.tools.hf_spaces import scrape
    return scrape(limit=limit)

def test_product_hunt(limit=5):
    from scrapers.tools.product_hunt import scrape
    return scrape(limit=limit)

def test_open_llm(limit=10):
    # Full paginated fetch is slow (~30s) — use limit to stop after top N
    from scrapers.benchmarks.open_llm import scrape
    return scrape(limit=limit)

def test_lmsys(limit=10):
    from scrapers.benchmarks.lmsys import scrape
    return scrape(limit=limit)

def test_artificial_analysis(limit=5):
    from scrapers.benchmarks.artificial_analysis import scrape
    return scrape(limit=limit)

def test_youtube(limit=1):
    from scrapers.talks.youtube import scrape
    CHANNELS = {
        "Lex Fridman":       "UCSHZKyawb77ixDdsGog4iWA",
        "Yannic Kilcher":    "UCZHmQk67mSJgfCCTn7xBfew",
        "Two Minute Papers": "UCbfYPyITQ-7l4upoX8nvctg",
        "AI Explained":      "UCNJ1Ymd5yFuUPtn21xtRbbw",
    }
    results = []
    for ch_name, ch_id in CHANNELS.items():
        items = scrape(channel_name=ch_name, channel_id=ch_id, limit=limit)
        results.extend(items)
    return results


# ── Test registry ─────────────────────────────────────────────────

SCRAPERS = [
    # (section, name, test_fn, slow?)
    ("papers",     "arXiv",               test_arxiv,               False),
    ("papers",     "HF Daily Papers",     test_hf_papers,           False),
    ("papers",     "OpenReview",          test_openreview,          False),
    ("news",       "RSS (6 sources)",     test_rss,                 False),
    ("news",       "Meta AI (Crawl4AI)",  test_meta_ai,             True ),
    ("tools",      "GitHub Trending",     test_github_trending,     False),
    ("tools",      "HF Hub",              test_hf_hub,              False),
    ("tools",      "HF Spaces",           test_hf_spaces,           False),
    ("tools",      "Product Hunt",        test_product_hunt,        False),
    ("benchmarks", "Open LLM Leaderboard",test_open_llm,            False),
    ("benchmarks", "LMSYS Arena",         test_lmsys,               True ),
    ("benchmarks", "Artificial Analysis", test_artificial_analysis, True ),
    ("talks",      "YouTube (4 channels)",test_youtube,             False),
]

SECTION_LABELS = {
    "papers":     "📄 Section 1 — Research Papers",
    "news":       "📰 Section 2 — AI News",
    "tools":      "🛠️  Section 3 — Tools & GitHub",
    "benchmarks": "📊 Section 4 — Benchmarks",
    "talks":      "🎥 Section 5 — Talks & Explainers",
}


# ── Main runner ───────────────────────────────────────────────────

def run_all(filter_section: str | None = None, skip_slow: bool = False):
    total         = len(SCRAPERS)
    passed        = 0
    warned        = 0
    failed        = 0
    skipped       = 0
    run_start     = datetime.now()
    all_results   = []

    current_section = None

    for idx, (section, name, fn, is_slow) in enumerate(SCRAPERS, 1):

        # Section filter
        if filter_section and section != filter_section:
            continue

        # Print section header when it changes
        if section != current_section:
            header(SECTION_LABELS[section])
            current_section = section

        # Skip slow scrapers if --fast flag
        if skip_slow and is_slow:
            result_line(idx, total, name, "skip", None, 0.0, "skipped (--fast)")
            skipped += 1
            continue

        # Run the scraper
        t0 = time.time()
        try:
            items   = fn()
            elapsed = time.time() - t0

            if not items:
                result_line(idx, total, name, "warn", 0, elapsed, "returned 0 items")
                warned += 1
                all_results.append((section, name, "warn", 0, None))

            else:
                first = items[0]
                # Check for None title/id — sign of a broken parse
                label = first.get("title") or first.get("name") or first.get("model_id") or first.get("id")
                if not label or "[fetch failed" in str(label):
                    result_line(idx, total, name, "warn", len(items), elapsed, "parse issues in items")
                    preview_item(first)
                    warned += 1
                    all_results.append((section, name, "warn", len(items), first))
                else:
                    result_line(idx, total, name, "ok", len(items), elapsed)
                    preview_item(first)
                    passed += 1
                    all_results.append((section, name, "ok", len(items), first))

        except NotImplementedError:
            elapsed = time.time() - t0
            result_line(idx, total, name, "fail", None, elapsed, "NotImplementedError — scraper is a stub")
            failed += 1
            all_results.append((section, name, "fail", None, None))

        except Exception as e:
            elapsed = time.time() - t0
            short   = str(e)[:80]
            result_line(idx, total, name, "fail", None, elapsed, short)
            print(f"         traceback: {traceback.format_exc().splitlines()[-1]}")
            failed += 1
            all_results.append((section, name, "fail", None, None))

    # ── Summary ───────────────────────────────────────────────────
    total_elapsed = (datetime.now() - run_start).total_seconds()

    print(f"\n{'='*62}")
    print(bold("  SUMMARY"))
    print(f"{'='*62}")
    print(f"  {green(f'{OK}  Passed  : {passed}')}")
    if warned:
        print(f"  {yellow(f'{WARN} Warned  : {warned}')}")
    if failed:
        print(f"  {red(f'{FAIL}  Failed  : {failed}')}")
    if skipped:
        print(f"  {SKIP} Skipped : {skipped}")
    print(f"  Total time : {total_elapsed:.1f}s")
    print(f"{'='*62}\n")

    if failed:
        print(red("  Failed scrapers:"))
        for section, name, status, count, _ in all_results:
            if status == "fail":
                print(f"    ❌ {name}")
        print()

    return failed == 0


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    args            = sys.argv[1:]
    filter_section  = None
    skip_slow       = "--fast" in args

    if "--section" in args:
        idx = args.index("--section")
        if idx + 1 < len(args):
            filter_section = args[idx + 1]
            valid = {"papers", "news", "tools", "benchmarks", "talks"}
            if filter_section not in valid:
                print(f"Unknown section '{filter_section}'. Choose from: {valid}")
                sys.exit(1)

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    print(bold("\nAI Radar — Scraper Test Suite"))
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if filter_section:
        print(f"Section filter: {filter_section}")
    if skip_slow:
        print("Mode: --fast (skipping Crawl4AI scrapers)")

    success = run_all(filter_section=filter_section, skip_slow=skip_slow)
    sys.exit(0 if success else 1)