from config import settings
from supabase import create_client, Client

_client: Client | None = None

TABLE_MAP = {
    "papers":     "research_papers",
    "news":       "ai_news",
    "tools":      "ai_tools",
    "benchmarks": "benchmark_entries",
    "talks":      "talk_videos",
}

DEDUP_KEY = {
    "papers":     "arxiv_id",
    "news":       "url",
    "tools":      "url",
    "benchmarks": "id",
    "talks":      "id",
}


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


def record_exists(section: str, raw: dict) -> bool:
    """
    Returns True if a record with the same dedup key already exists.
    Used at dedup stage before storing raw records.
    """
    db    = get_client()
    table = TABLE_MAP[section]
    key   = DEDUP_KEY[section]
    value = raw.get(key)

    if not value:
        return False

    response = (
        db.table(table)
        .select("id")
        .eq(key, value)
        .limit(1)
        .execute()
    )
    return len(response.data) > 0


def upsert_record(section: str, record: dict) -> None:
    """
    Inserts a raw record (summarised_at = NULL).
    Talks: splits transcript_full into talk_transcripts table.
    Called by scraper_flow.
    """
    db    = get_client()
    table = TABLE_MAP[section]

    if section == "talks":
        transcript_full = record.pop("transcript_full", None)
        db.table(table).upsert(record).execute()
        if transcript_full and record.get("id"):
            db.table("talk_transcripts").upsert({
                "video_id":       record["id"],
                "transcript_full": transcript_full,
            }).execute()
    else:
        db.table(table).upsert(record).execute()


def fetch_pending(section: str, batch_size: int = 20) -> list[dict]:
    """
    Returns records that have been scraped but not yet summarised.
    Ordered by fetched_at ASC so oldest items are processed first.
    Called by summariser_flow.
    """
    db    = get_client()
    table = TABLE_MAP[section]

    # For talks, also fetch transcript_full via join
    if section == "talks":
        response = (
            db.table(table)
            .select("*, talk_transcripts(transcript_full)")
            .is_("summarised_at", "null")
            .order("fetched_at", desc=False)
            .limit(batch_size)
            .execute()
        )
        # Flatten joined transcript into the main record
        records = []
        for row in (response.data or []):
            transcript_data = row.pop("talk_transcripts", None)
            if isinstance(transcript_data, list) and transcript_data:
                row["transcript_full"] = transcript_data[0].get("transcript_full")
            elif isinstance(transcript_data, dict):
                row["transcript_full"] = transcript_data.get("transcript_full")
            records.append(row)
        return records

    response = (
        db.table(table)
        .select("*")
        .is_("summarised_at", "null")
        .order("fetched_at", desc=False)
        .limit(batch_size)
        .execute()
    )
    return response.data or []


def update_ai_fields(section: str, record_id: str, ai_fields: dict) -> None:
    """
    Updates an existing record with AI-generated fields + stamps summarised_at.
    Called by summariser_flow after LLM returns.
    """
    from datetime import datetime, timezone

    db    = get_client()
    table = TABLE_MAP[section]

    # Serialize any datetime objects — Supabase client cannot handle them
    # Also strip empty strings and empty lists that add no value
    clean = {}
    for k, v in ai_fields.items():
        if isinstance(v, datetime):
            clean[k] = v.isoformat()
        elif v in (None, "", []):
            continue   # don't write empty values — leave existing DB value intact
        else:
            clean[k] = v

    if not clean:
        import logging
        logging.getLogger(__name__).warning(
            f"[{section}] update_ai_fields called with empty payload for '{record_id}' — only stamping summarised_at"
        )

    payload = {
        **clean,
        "summarised_at": datetime.now(timezone.utc).isoformat(),
    }

    response = db.table(table).update(payload).eq("id", record_id).execute()

    # Supabase client does NOT raise on failed updates — check explicitly
    if hasattr(response, "error") and response.error:
        raise Exception(f"Supabase update error for '{record_id}': {response.error}")
    if not response.data:
        raise Exception(
            f"No rows updated for '{record_id}' in '{table}' — "
            f"id may not exist or RLS policy is blocking the update"
        )