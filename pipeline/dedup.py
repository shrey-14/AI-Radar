import re
from hashlib import sha256
from difflib import SequenceMatcher

from pipeline.storage import get_client, TABLE_MAP
from config import settings


# ════════════════════════════════════════════════════════
# LEVEL 1 — BATCH DEDUP (in-memory)
# ════════════════════════════════════════════════════════

def dedup_batch(section: str, records: list[dict]) -> list[dict]:
    """
    Dispatcher — applies the correct batch dedup strategy per section.
    Called once per section after scraping, before the DB check loop.
    """
    if section == "papers":
        return _dedup_papers(records)
    if section == "news":
        return _dedup_news(records)
    if section == "tools":
        return _dedup_tools(records)
    if section == "benchmarks":
        return _merge_benchmarks(records)
    if section == "talks":
        return _dedup_talks(records)
    return records


def _dedup_papers(records: list[dict]) -> list[dict]:
    """
    Merges records from arXiv, HF Daily Papers, OpenReview
    by arxiv_id. OpenReview papers without arxiv_id kept standalone.

    Merge priority (fields added only if not already present):
      arXiv      → base record (always has arxiv_id, full metadata)
      HF Papers  → adds: upvotes, num_comments, featured_date, thumbnail
      OpenReview → adds: venue, decision, keywords
    """
    seen_arxiv      = {}   # arxiv_id  → merged record
    seen_openreview = {}   # note_id   → standalone record

    for r in records:
        arxiv_id = r.get("arxiv_id")
        if arxiv_id:
            if arxiv_id in seen_arxiv:
                # Merge — only add fields not already present
                seen_arxiv[arxiv_id].update(
                    {k: v for k, v in r.items()
                     if v is not None and seen_arxiv[arxiv_id].get(k) is None}
                )
            else:
                seen_arxiv[arxiv_id] = dict(r)
        else:
            # OpenReview paper with no arxiv_id — keep standalone
            note_id = r.get("openreview_note_id")
            if note_id and note_id not in seen_openreview:
                seen_openreview[note_id] = r

    return list(seen_arxiv.values()) + list(seen_openreview.values())


def _dedup_news(records: list[dict]) -> list[dict]:
    """
    Primary lab blogs (Anthropic, OpenAI, DeepMind, Meta AI) → always kept.
    Aggregators (TLDR AI, TechCrunch, Import AI) → deduped by:
      1. Exact URL hash
      2. Title similarity > threshold against already-kept titles
    """
    PRIMARY    = {"anthropic", "openai", "google_deepmind", "meta_ai"}
    AGGREGATORS = {"tldr_ai", "techcrunch_ai", "import_ai"}

    seen_urls   = set()
    seen_titles = []
    result      = []

    # Primary sources — always kept, no dedup
    for r in records:
        if r.get("source") in PRIMARY:
            url_hash = sha256((r.get("url") or "").encode()).hexdigest()
            seen_urls.add(url_hash)
            seen_titles.append((r.get("title") or "").lower())
            result.append(r)

    # Aggregators — exact URL dedup + semantic title dedup
    for r in records:
        if r.get("source") not in AGGREGATORS:
            continue

        url_hash = sha256((r.get("url") or "").encode()).hexdigest()
        if url_hash in seen_urls:
            continue   # exact duplicate URL

        title = (r.get("title") or "").lower()
        is_dupe = any(
            SequenceMatcher(None, title, t).ratio() >= settings.news_dedup_threshold
            for t in seen_titles
        )
        if not is_dupe:
            seen_urls.add(url_hash)
            seen_titles.append(title)
            result.append(r)

    return result


def _dedup_tools(records: list[dict]) -> list[dict]:
    """
    Exact URL dedup only. Each source (GitHub, HF Hub, HF Spaces, PH)
    produces distinct entities — no merging needed.
    """
    seen   = set()
    result = []
    for r in records:
        key = sha256((r.get("url") or "").encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            result.append(r)
    return result


def _normalise_model_id(model_id: str) -> str:
    """
    Normalises model IDs across leaderboards for merge matching.
      'Qwen/Qwen2.5-72B-Instruct' → 'qwen2-5-72b-instruct'
      'qwen2.5-72b-instruct'      → 'qwen2-5-72b-instruct'
    """
    name = (model_id or "").lower()
    if "/" in name:
        name = name.split("/")[-1]        # strip org prefix
    name = re.sub(r"[\s_\.]", "-", name)  # unify separators
    name = re.sub(r"-+", "-", name)       # collapse hyphens
    return name.strip("-")


def _merge_benchmarks(records: list[dict]) -> list[dict]:
    """
    Merges records for the same model from all 3 leaderboard sources.
    Each source contributes non-overlapping fields so all are kept.
    Merge key: normalised model_id.

    Note: the merged record keeps the `id` from the first source seen.
    The unique constraint in Supabase is (source, model_id) not just id,
    so merging here is for the LLM summariser to have all data in one pass.
    """
    merged = {}   # normalised_id → merged record

    for r in records:
        key = _normalise_model_id(r.get("model_id", ""))
        if key in merged:
            merged[key].update(
                {k: v for k, v in r.items()
                 if v is not None and merged[key].get(k) is None}
            )
        else:
            merged[key] = dict(r)

    return list(merged.values())


def _dedup_talks(records: list[dict]) -> list[dict]:
    """
    Exact video_id dedup. Each channel produces original content —
    no merging needed between channels.
    """
    seen   = set()
    result = []
    for r in records:
        vid = r.get("id")
        if vid and vid not in seen:
            seen.add(vid)
            result.append(r)
    return result


# ════════════════════════════════════════════════════════
# LEVEL 2 — DB CHECK (per record, against Supabase)
# ════════════════════════════════════════════════════════

def is_duplicate(section: str, raw: dict) -> bool:
    """
    Returns True if this record already exists in Supabase.
    Called per record after batch dedup, before storing.

    News aggregators also check title similarity against
    articles already stored today (catches cross-run duplicates).
    """
    db    = get_client()
    table = TABLE_MAP[section]

    col, val = _get_dedup_key(section, raw)
    if not col or not val:
        return False   # no key determinable — allow through

    response = (
        db.table(table)
        .select("id")
        .eq(col, val)
        .limit(1)
        .execute()
    )
    if response.data:
        return True

    # Extra semantic check for news aggregators against today's DB records
    AGGREGATORS = {"tldr_ai", "techcrunch_ai", "import_ai"}
    if section == "news" and raw.get("source") in AGGREGATORS:
        return _is_semantic_news_duplicate_in_db(raw)

    return False


def _get_dedup_key(section: str, raw: dict) -> tuple[str | None, str | None]:
    """Returns (column, value) for the Supabase existence check."""
    if section == "papers":
        if raw.get("arxiv_id"):
            return ("arxiv_id", raw["arxiv_id"])
        if raw.get("openreview_note_id"):
            return ("openreview_note_id", raw["openreview_note_id"])
        return (None, None)

    if section == "news":
        url = raw.get("url")
        return ("id", sha256(url.encode()).hexdigest()) if url else (None, None)

    if section == "tools":
        return ("url", raw.get("url"))

    if section == "benchmarks":
        return ("id", raw.get("id"))

    if section == "talks":
        return ("id", raw.get("id"))

    return (None, None)


def _is_semantic_news_duplicate_in_db(raw: dict) -> bool:
    """
    Checks title similarity against aggregator articles already stored
    today in Supabase. Catches duplicates across pipeline runs.
    """
    db        = get_client()
    title     = (raw.get("title") or "").lower()
    published = raw.get("published_date", "")

    if not title or not published:
        return False

    response = (
        db.table("ai_news")
        .select("title")
        .eq("published_date", published)
        .in_("source", ["tldr_ai", "techcrunch_ai", "import_ai"])
        .execute()
    )

    for row in (response.data or []):
        existing = (row.get("title") or "").lower()
        if SequenceMatcher(None, title, existing).ratio() >= settings.news_dedup_threshold:
            return True

    return False