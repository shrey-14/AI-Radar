"""
pipeline/embedding_flow.py
==========================
Generates and stores vector embeddings for all rag_ready records
using Jina AI's jina-embeddings-v3 (570M params, 8192 token context).

Key features:
  - Asymmetric retrieval: passages embedded with task=retrieval.passage,
    queries embedded with task=retrieval.query (5-10% better accuracy)
  - Batched API calls (20 records per request)
  - Incremental: only embeds records without an existing embedding
  - --force flag to re-embed everything

Run standalone:
    python pipeline/embedding_flow.py                     # all sections
    python pipeline/embedding_flow.py --section papers    # one section
    python pipeline/embedding_flow.py --force             # re-embed all
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import logging
import argparse
import requests
from prefect import flow, task

from config import settings
from storage.supabase_client import get_client

log = logging.getLogger(__name__)

# ── Jina AI config ────────────────────────────────────────────────
JINA_URL     = "https://api.jina.ai/v1/embeddings"
JINA_HEADERS = {
    "Content-Type":  "application/json",
    "Authorization": f"Bearer {settings.jina_api_key}",
}
EMBED_MODEL = "jina-embeddings-v3"
EMBED_DIMS  = 1024   # default for v3; reduce to 512 to halve storage cost
BATCH_SIZE  = 20     # records per Jina API call

SECTION_TABLE = {
    "papers":     "research_papers",
    "news":       "ai_news",
    "tools":      "ai_tools",
    "benchmarks": "benchmark_entries",
    "talks":      "talk_videos",
}

# Fields to SELECT per section — only what we need, not the full row
SECTION_SELECT = {
    "papers":     "id, title, one_line_summary, problem_solved, approach_used, key_results, ai_tags",
    "news":       "id, title, summary, key_points, companies_mentioned, models_mentioned, category",
    "tools":      "id, name, description, what_it_does, use_cases, pipeline_task, tags",
    "benchmarks": "id, model_display_name, model_summary, strengths, weaknesses, best_for, source",
    "talks":      "id, title, summary, key_insights, topics_covered, people_mentioned",
}


# ══════════════════════════════════════════════════════════════════
#  TEXT BUILDER — constructs the string that gets embedded per record
# ══════════════════════════════════════════════════════════════════

def build_embed_text(record: dict, section: str) -> str:
    """
    Concatenate the most semantically rich fields for each section.
    Uses | as separator — keeps field boundaries clear in the vector space.
    """

    def join_list(items) -> str:
        if not items:
            return ""
        if isinstance(items, list):
            return " ".join(str(i) for i in items if i)
        return str(items)

    if section == "papers":
        parts = [
            record.get("title", ""),
            record.get("one_line_summary", ""),
            record.get("problem_solved", ""),
            record.get("approach_used", ""),
            record.get("key_results", ""),
            join_list(record.get("ai_tags")),
        ]

    elif section == "news":
        parts = [
            record.get("title", ""),
            record.get("summary", ""),
            join_list(record.get("key_points")),
            join_list(record.get("companies_mentioned")),
            join_list(record.get("models_mentioned")),
            record.get("category", ""),
        ]

    elif section == "tools":
        parts = [
            record.get("name", ""),
            record.get("name", ""),
            (record.get("description") or "")[:300],   # cap long descriptions
            record.get("what_it_does", ""),
            join_list(record.get("use_cases")),
            record.get("pipeline_task", ""),
            join_list(record.get("tags")),
        ]

    elif section == "benchmarks":
        parts = [
            record.get("model_display_name", ""),
            record.get("model_summary", ""),
            join_list(record.get("strengths")),
            join_list(record.get("weaknesses")),
            record.get("best_for", ""),
            record.get("source", ""),
        ]

    elif section == "talks":
        parts = [
            record.get("title", ""),
            record.get("summary", ""),
            record.get("channel", ""), 
            join_list(record.get("key_insights")),
            join_list(record.get("topics_covered")),
            join_list(record.get("people_mentioned")),
        ]

    else:
        return ""

    return " | ".join(p for p in parts if p and p.strip())


# ══════════════════════════════════════════════════════════════════
#  JINA API CALLS
# ══════════════════════════════════════════════════════════════════

def _call_jina(inputs: list[str], task_type: str) -> list[list[float]]:
    """
    Single Jina API call. Handles 429 rate limit with exponential backoff.
    task_type: 'retrieval.passage' for documents, 'retrieval.query' for queries.
    """
    resp = requests.post(
        JINA_URL,
        headers=JINA_HEADERS,
        json={
            "model":      EMBED_MODEL,
            "input":      inputs,
            "task":       task_type,
            "dimensions": EMBED_DIMS,
        },
        timeout=60,
    )

    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 30))
        log.warning(f"Jina rate limited — waiting {retry_after}s")
        time.sleep(retry_after + 2)
        return _call_jina(inputs, task_type)

    if not resp.ok:
        raise RuntimeError(f"Jina API error {resp.status_code}: {resp.text[:300]}")

    return [item["embedding"] for item in resp.json()["data"]]


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a list of document passages for indexing."""
    return _call_jina(texts, "retrieval.passage")


def embed_query(query: str) -> list[float]:
    """
    Embed a single user query for retrieval.
    Uses a different LoRA adapter than document embedding for better accuracy.
    Importable by api/routes/ask.py.
    """
    return _call_jina([query], "retrieval.query")[0]


# ══════════════════════════════════════════════════════════════════
#  PREFECT TASKS
# ══════════════════════════════════════════════════════════════════

@task(name="embed-section", retries=2, retry_delay_seconds=30)
def embed_section_task(section: str, force: bool = False) -> dict:
    """
    Fetch unembedded rag_ready records, generate embeddings, save to Supabase.

    Args:
        section: one of papers / news / tools / benchmarks / talks
        force:   if True, re-embeds records that already have embeddings
    """
    table  = SECTION_TABLE[section]
    select = SECTION_SELECT[section]
    db     = get_client()

    # Build query
    query = db.table(table).select(select)
    if not force:
        query = query.is_("embedding", "null")

    records = query.execute().data or []
    log.info(f"[{section}] {len(records)} records to embed")

    if not records:
        return {"section": section, "embedded": 0, "skipped": 0}

    embedded = 0
    skipped  = 0

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]

        # Build embed texts, skip empty records
        pairs  = [(r, build_embed_text(r, section)) for r in batch]
        valid  = [(r, t) for r, t in pairs if t.strip()]
        skipped += len(pairs) - len(valid)

        if not valid:
            continue

        batch_records, batch_texts = zip(*valid)

        try:
            vectors = embed_documents(list(batch_texts))
        except Exception as e:
            log.error(f"[{section}] Batch {i // BATCH_SIZE + 1} failed: {e}")
            skipped += len(valid)
            continue

        # Write each embedding back to Supabase
        for record, vector in zip(batch_records, vectors):
            try:
                db.table(table).update({"embedding": vector}).eq("id", record["id"]).execute()
                embedded += 1
            except Exception as e:
                log.error(f"[{section}] Failed to save embedding for {record['id']}: {e}")
                skipped += 1

        log.info(f"[{section}] Progress: {embedded}/{len(records)} embedded")
        time.sleep(0.3)   # gentle pacing between batches

    return {"section": section, "embedded": embedded, "skipped": skipped}


# ══════════════════════════════════════════════════════════════════
#  PREFECT FLOW
# ══════════════════════════════════════════════════════════════════

@flow(
    name="ai-radar-embedding",
    description="Generate jina-embeddings-v3 embeddings for all rag_ready records",
)
def embedding_flow(
    section: str | None = None,
    force:   bool       = False,
) -> None:
    """
    Embeds all rag_ready summaries using jina-embeddings-v3.

    Designed to run after summariser_flow.py completes —
    only processes records without existing embeddings unless --force is set.

    Args:
        section: embed one section only (None = all five)
        force:   re-embed records that already have an embedding
    """
    sections = list(SECTION_TABLE.keys()) if section is None else [section]

    log.info(f"Embedding flow started")
    log.info(f"  model      : {EMBED_MODEL}")
    log.info(f"  dimensions : {EMBED_DIMS}")
    log.info(f"  sections   : {sections}")
    log.info(f"  force      : {force}")

    results = []
    for sec in sections:
        result = embed_section_task(sec, force=force)
        results.append(result)

    # Summary
    log.info("\n══ EMBEDDING REPORT ══")
    total_embedded = 0
    total_skipped  = 0
    for r in results:
        log.info(
            f"  {r['section']:<15} embedded={r['embedded']}  skipped={r['skipped']}"
        )
        total_embedded += r["embedded"]
        total_skipped  += r["skipped"]
    log.info(f"  {'TOTAL':<15} embedded={total_embedded}  skipped={total_skipped}")


# ══════════════════════════════════════════════════════════════════
#  STANDALONE ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="AI Radar — Embedding Pipeline")
    parser.add_argument(
        "--section", default=None,
        choices=list(SECTION_TABLE.keys()),
        help="Embed one section only (default: all)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-embed records that already have embeddings",
    )
    args = parser.parse_args()

    embedding_flow(section=args.section, force=args.force)