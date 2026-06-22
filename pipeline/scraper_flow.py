import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime

from prefect import flow, task

from config import settings, validate_on_startup
from pipeline.scraper import scrape_section
from pipeline.dedup import is_duplicate, dedup_batch
from pipeline.storage import upsert_record, record_exists
from schemas import ResearchPaper, AINewsArticle, AITool, BenchmarkEntry, TalkVideo

log = logging.getLogger(__name__)

SCHEMA_MAP = {
    "papers":     ResearchPaper,
    "news":       AINewsArticle,
    "tools":      AITool,
    "benchmarks": BenchmarkEntry,
    "talks":      TalkVideo,
}


# ── Tasks ─────────────────────────────────────────────────────────

@task(name="scrape-section", retries=2, retry_delay_seconds=30)
def scrape_task(section: str, limit: int) -> list[dict]:
    """Scrapes all sources for a section. Retries twice on network failure."""
    log.info(f"[{section}] Scraping (limit={limit})")
    try:
        records = scrape_section(section, limit=limit)
        log.info(f"[{section}] Scraped {len(records)} raw records")
        return records
    except Exception as e:
        log.error(f"[{section}] Scrape failed: {e}")
        return []


@task(name="validate-record")
def validate_task(section: str, raw: dict) -> dict | None:
    """
    Validates raw dict against Pydantic schema.
    Returns None on failure so caller skips this record.
    """
    schema = SCHEMA_MAP[section]
    try:
        schema(**raw)
        return raw
    except Exception as e:
        log.warning(f"[{section}] Validation failed for '{raw.get('id', '?')}': {e}")
        return None


@task(name="dedup-check")
def dedup_task(section: str, raw: dict) -> bool:
    """Returns True if this record already exists in Supabase."""
    return is_duplicate(section, raw)


@task(name="store-raw", retries=2, retry_delay_seconds=15)
def store_raw_task(section: str, record: dict) -> bool:
    """
    Stores raw record with summarised_at = NULL.
    Retries twice on transient Supabase connection failures.
    """
    try:
        upsert_record(section, record)
        return True
    except Exception as e:
        log.error(f"[{section}] Store failed for '{record.get('id', '?')}': {e}")
        log.error(f"[{section}] Failed record: {record}")
        return False


# ── Per-section scraper ───────────────────────────────────────────

# Replace the existing scrape_section_flow function
def scrape_section_flow(section: str) -> dict:
    """
    Runs scrape → batch dedup → validate → DB dedup → store raw.
    """
    limit = settings.max_per_run[section]

    stats = {
        "section":        section,
        "scraped":        0,
        "batch_deduped":  0,
        "invalid":        0,
        "db_duplicate":   0,
        "stored":         0,
        "failed":         0,
    }

    # Scrape
    raw_records      = scrape_task(section, limit)
    stats["scraped"] = len(raw_records)

    # Level 1 — Batch dedup (merge papers, semantic news dedup, etc.)
    deduped                 = dedup_batch(section, raw_records)
    stats["batch_deduped"]  = stats["scraped"] - len(deduped)
    log.info(f"[{section}] After batch dedup: {len(deduped)} records "
             f"({stats['batch_deduped']} merged/removed)")

    for raw in deduped:

        # Validate
        validated = validate_task(section, raw)
        if validated is None:
            stats["invalid"] += 1
            continue

        # Level 2 — DB dedup check
        if dedup_task(section, validated):
            stats["db_duplicate"] += 1
            log.debug(f"[{section}] DB duplicate skipped: '{validated.get('id', '?')}'")
            continue

        # Store raw
        stored = store_raw_task(section, validated)
        if stored:
            stats["stored"] += 1
            log.info(f"[{section}] Stored raw: '{validated.get('id', '?')}'")
        else:
            stats["failed"] += 1

    return stats


# ── Main flow ─────────────────────────────────────────────────────

@flow(name="ai-radar-scraper", description="AI Radar — scrape and store raw records")
def scraper_flow(section: str | None = None) -> None:
    """
    Scrapes all enabled sections (or one specific section) and stores
    raw records in Supabase with summarised_at = NULL.

    Args:
        section: optional — run only this section e.g. 'papers'
    """
    run_start = datetime.utcnow()
    log.info(f"Scraper flow started at {run_start.isoformat()}")

    if section:
        sections = [section]
    else:
        sections = settings.enabled_sections

    if not sections:
        log.warning("No sections enabled. Set ENABLE_* flags in .env")
        return

    log.info(f"Sections to scrape: {sections}")

    all_stats = []
    for sec in sections:
        log.info(f"--- Starting section: {sec} ---")
        try:
            stats = scrape_section_flow(sec)
            all_stats.append(stats)
        except Exception as e:
            log.error(f"Section '{sec}' failed entirely: {e}")
            all_stats.append({"section": sec, "error": str(e)})

    # Run report
    duration = (datetime.utcnow() - run_start).total_seconds()
    log.info("=" * 52)
    log.info(f"Scraper flow complete in {duration:.1f}s")
    log.info("=" * 52)
    for s in all_stats:
        if "error" in s:
            log.error(f"  {s['section']:12s}  FAILED: {s['error']}")
        else:
            log.info(
                f"  {s['section']:12s}"
                f"  scraped={s.get('scraped', 0):3d}"
                f"  batch_deduped={s.get('batch_deduped', 0):3d}"
                f"  stored={s.get('stored', 0):3d}"
                f"  db_dupes={s.get('db_duplicate', 0):3d}"
                f"  invalid={s.get('invalid', 0):3d}"
                f"  failed={s.get('failed', 0):3d}"
            )
    log.info("=" * 52)


# ── Schedule ──────────────────────────────────────────────────────

def create_scheduled_deployment():
    """Register 07:00 daily schedule with Prefect."""
    scraper_flow.serve(
        name="ai-radar-scraper-daily",
        cron="0 7 * * *",
    )
    log.info("Scraper deployment registered: runs daily at 07:00")


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    validate_on_startup()

    args = sys.argv[1:]

    if "--deploy" in args:
        create_scheduled_deployment()
        sys.exit(0)

    # Optional single-section flag: python scraper_flow.py --section papers
    section_filter = None
    if "--section" in args:
        idx = args.index("--section")
        if idx + 1 < len(args):
            section_filter = args[idx + 1]

    scraper_flow(section=section_filter)
