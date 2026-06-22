import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import datetime, timezone

from prefect import flow

from config import settings, validate_on_startup
from pipeline.scraper_flow import scraper_flow
from pipeline.summariser_flow import summariser_flow
from pipeline.eval_flow import evaluation_flow
from pipeline.alert_flow import send_failure_alert, send_success_summary

log = logging.getLogger(__name__)


@flow(name="ai-radar-pipeline", description="AI Radar — full pipeline (scrape + summarise + evaluate)")
def ai_radar_pipeline(
    section:     str | None = None,
    eval_sample: int        = 50,
    skip_eval:   bool       = False,
) -> None:
    """
    Full pipeline:
      1. scraper_flow     — scrape → validate → dedup → store raw
      2. summariser_flow  — fetch pending → LLM → update AI fields
      3. evaluation_flow  — LLM-as-judge quality check on new summaries

    Args:
        section:     optional — run only this section e.g. 'papers'
        eval_sample: max records to evaluate per section (default 50)
        skip_eval:   set True to skip evaluation step (faster dev runs)
    """
    run_start = datetime.now(timezone.utc)
    log.info(f"AI Radar full pipeline started at {run_start.isoformat()}")

    # ── Flow 1: Scrape ────────────────────────────────────────────
    log.info("=" * 50)
    log.info("Flow 1/3 — Scraping")
    log.info("=" * 50)
    scraper_flow(section=section)

    # ── Flow 2: Summarise ─────────────────────────────────────────
    log.info("=" * 50)
    log.info("Flow 2/3 — Summarising")
    log.info("=" * 50)
    summariser_flow(section=section)

    # ── Flow 3: Evaluate ──────────────────────────────────────────
    if skip_eval:
        log.info("Flow 3/3 — Evaluation skipped (--skip-eval flag)")
    else:
        log.info("=" * 50)
        log.info("Flow 3/3 — Evaluating summary quality")
        log.info("=" * 50)
        evaluation_flow(section=section, sample=eval_sample)

    duration = (datetime.now(timezone.utc) - run_start).total_seconds()
    log.info(f"Full pipeline complete in {duration:.1f}s")


def create_scheduled_deployment():
    """
    Registers flows on their daily schedules:
      scraper_flow     → 07:00 UTC
      summariser_flow  → 07:30 UTC
      evaluation_flow  → 08:00 UTC (after summarisation finishes)
    """
    from pipeline.scraper_flow    import scraper_flow    as sf
    from pipeline.summariser_flow import summariser_flow as sumf
    from pipeline.eval_flow       import evaluation_flow as evf

    sf.serve(  name="ai-radar-scraper-daily",    cron="0 7 * * *")
    sumf.serve(name="ai-radar-summariser-daily", cron="30 7 * * *")
    evf.serve( name="ai-radar-evaluator-daily",  cron="0 8 * * *")
    log.info("Deployments registered: scraper 07:00 · summariser 07:30 · evaluator 08:00")


if __name__ == "__main__":
    try:
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s  %(levelname)-8s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        validate_on_startup()

        start_time     = time.perf_counter()
        args           = sys.argv[1:]
        section_filter = None
        eval_sample    = 50
        skip_eval      = False

        if "--deploy" in args:
            create_scheduled_deployment()
            sys.exit(0)

        if "--section" in args:
            idx = args.index("--section")
            if idx + 1 < len(args):
                section_filter = args[idx + 1]

        if "--eval-sample" in args:
            idx = args.index("--eval-sample")
            if idx + 1 < len(args):
                eval_sample = int(args[idx + 1])

        if "--skip-eval" in args:
            skip_eval = True

        ai_radar_pipeline(
            section     = section_filter,
            eval_sample = eval_sample,
            skip_eval   = skip_eval,
        )

        elapsed = time.perf_counter() - start_time
        print(f"\nTotal run time: {elapsed:.2f}s")
        send_success_summary(elapsed, section_counts={})

    except Exception as e:
        elapsed = time.perf_counter() - start_time
        send_failure_alert(
            pipeline_name="ai-radar-pipeline",
            error=e,
            context=f"Failed after {elapsed/60:.1f} minutes",
        )
        raise