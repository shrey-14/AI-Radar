"""
pipeline/summariser_flow.py — AI Radar
========================================
Flow 2: Fetch pending → Summarise → Update AI fields

Reads records where summarised_at IS NULL from Supabase,
sends them to Groq LLM, and writes AI-generated fields back.

Run manually (all sections):
    python pipeline/summariser_flow.py

Run a single section:
    python pipeline/summariser_flow.py --section papers

Register schedule (runs 30 min after scraper_flow):
    python pipeline/summariser_flow.py --deploy
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import datetime

from prefect import flow, task

from config import settings, validate_on_startup
from pipeline.summariser import summarise
from pipeline.storage import fetch_pending, update_ai_fields

log = logging.getLogger(__name__)

# AI-generated field names per section — only these are written back
AI_FIELDS = {
    "papers": [
        "one_line_summary", "problem_solved", "approach_used",
        "key_results", "real_world_impact", "limitations",
        "relevance_score", "ai_tags",
    ],
    "news": [
        "summary", "key_points", "category",
        "companies_mentioned", "models_mentioned",
        "significance_score", "ai_tags",
    ],
    "tools": [
        "what_it_does", "use_cases", "why_trending",
        "significance_score", "ai_tags",
    ],
    "benchmarks": [
        "model_summary", "strengths", "weaknesses", "best_for",
    ],
    "talks": [
        "summary", "key_insights", "topics_covered",
        "papers_mentioned", "people_mentioned",
        "guest_name", "guest_affiliation",
        "difficulty_level", "relevance_score", "ai_tags",
    ],
}

# Groq free tier: ~30 req/min on 70b, ~60 req/min on 8b
# Conservative delay between LLM calls to avoid 429s
DELAY_BETWEEN_CALLS = {
    "papers":     1.5,   # 8b model
    "news":       2.5,   # 70b model — slower
    "tools":      1.5,   # 8b model
    "benchmarks": 1.5,   # 8b model
    "talks":      3.0,   # 70b model + long transcripts
}


# ── Tasks ─────────────────────────────────────────────────────────

@task(name="summarise-record", retries=1, retry_delay_seconds=15)
def summarise_task(section: str, record: dict) -> dict | None:
    try:
        llm_result = summarise(section, record)
        ai_only    = llm_result.model_dump(exclude_none=True)

        log.info(f"[{section}] ai_only keys: {list(ai_only.keys())} | values preview: { {k: str(v)[:60] for k, v in ai_only.items()} }")

        if not ai_only:
            log.warning(f"[{section}] LLM returned empty dict for '{record.get('id', '?')}'")
            return None

        return ai_only
    except Exception as e:
        log.error(f"[{section}] Summarise failed for '{record.get('id', '?')}': {e}")
        return None


@task(name="update-ai-fields", retries=2, retry_delay_seconds=10)
def update_task(section: str, record_id: str, ai_fields: dict) -> bool:
    """
    Writes AI-generated fields + summarised_at back to the existing record.
    """
    try:
        update_ai_fields(section, record_id, ai_fields)
        return True
    except Exception as e:
        log.error(f"[{section}] Update failed for '{record_id}': {e}")
        return False


# ── Per-section summariser ────────────────────────────────────────

def summarise_section(section: str) -> dict:
    """
    Fetches all pending records for a section, summarises them,
    and writes AI fields back. Returns stats dict.
    """
    batch_size = settings.max_per_run[section]
    delay      = DELAY_BETWEEN_CALLS[section]

    stats = {
        "section":    section,
        "pending":    0,
        "summarised": 0,
        "skipped":    0,
        "failed":     0,
    }

    pending          = fetch_pending(section, batch_size=batch_size)
    stats["pending"] = len(pending)

    if not pending:
        log.info(f"[{section}] No pending records to summarise")
        return stats

    log.info(f"[{section}] {len(pending)} records to summarise")

    for record in pending:
        record_id = record.get("id")

        # Summarise
        ai_fields = summarise_task(section, record)

        if ai_fields is None:
            stats["skipped"] += 1
            log.warning(f"[{section}] Skipped (LLM failed): '{record_id}'")
            continue

        # Write back
        updated = update_task(section, record_id, ai_fields)
        if updated:
            stats["summarised"] += 1
        else:
            stats["failed"] += 1

        # Rate limit guard between LLM calls
        time.sleep(delay)

    return stats


# ── Main flow ─────────────────────────────────────────────────────

@flow(
    name="ai-radar-summariser",
    description="AI Radar — summarise pending records with Groq LLM",
)
def summariser_flow(section: str | None = None) -> None:
    """
    Reads records with summarised_at = NULL from Supabase,
    sends them to Groq, and writes AI-generated fields back.

    Args:
        section: optional — summarise only this section e.g. 'papers'
    """
    run_start = datetime.utcnow()
    log.info(f"Summariser flow started at {run_start.isoformat()}")

    if section:
        sections = [section]
    else:
        sections = settings.enabled_sections

    if not sections:
        log.warning("No sections enabled.")
        return

    log.info(f"Sections to summarise: {sections}")

    all_stats = []
    for sec in sections:
        log.info(f"--- Summarising section: {sec} ---")
        try:
            stats = summarise_section(sec)
            all_stats.append(stats)
        except Exception as e:
            log.error(f"Section '{sec}' summariser failed: {e}")
            all_stats.append({"section": sec, "error": str(e)})

    # Run report
    duration = (datetime.utcnow() - run_start).total_seconds()
    log.info("=" * 52)
    log.info(f"Summariser flow complete in {duration:.1f}s")
    log.info("=" * 52)
    for s in all_stats:
        if "error" in s:
            log.error(f"  {s['section']:12s}  FAILED: {s['error']}")
        else:
            log.info(
                f"  {s['section']:12s}"
                f"  pending={s.get('pending', 0):3d}"
                f"  summarised={s.get('summarised', 0):3d}"
                f"  skipped={s.get('skipped', 0):3d}"
                f"  failed={s.get('failed', 0):3d}"
            )
    log.info("=" * 52)


# ── Schedule ──────────────────────────────────────────────────────

def create_scheduled_deployment():
    """
    Register Prefect schedule — runs at 07:30 daily,
    30 minutes after scraper_flow at 07:00.
    """
    summariser_flow.serve(
        name="ai-radar-summariser-daily",
        cron="30 7 * * *",
    )
    log.info("Summariser deployment registered: runs daily at 07:30")


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

    section_filter = None
    if "--section" in args:
        idx = args.index("--section")
        if idx + 1 < len(args):
            section_filter = args[idx + 1]

    summariser_flow(section=section_filter)
