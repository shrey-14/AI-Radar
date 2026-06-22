"""
api/routes/ask.py
=================
RAG endpoint for AI Radar.

Pipeline per request:
  1. Query Router       — llama-3.1-8b-instant on Groq
                          classifies which sections to query + rewrites query
  2. Intent Detection    — superlative (best/cheapest/fastest), channel-name,
                          recency, and metadata-filter queries get routed to
                          direct SQL instead of search
  3. Hybrid Retrieval    — dense (jina-embeddings-v3 + pgvector cosine) FUSED
                          with keyword (Postgres full-text / BM25-equivalent
                          ts_rank_cd) via Reciprocal Rank Fusion, per section
  4. Context Assembly    — format retrieved records with source labels
  5. Answer Generation   — openai/gpt-oss-120b on Groq
                          grounded strictly in retrieved context

Requires sql/hybrid_search.sql to have been run in Supabase first
(adds fts tsvector columns + match_*_hybrid functions).

Mount in your main FastAPI app:
    from api.routes.ask import router as ask_router
    app.include_router(ask_router, prefix="/api")

Then call: POST /api/ask  {"query": "...", "top_k": 5}
"""

import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from groq import Groq

from config import settings
from storage.supabase_client import get_client
from pipeline.embedding_flow import embed_query   # reuse the Jina embed function

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

log    = logging.getLogger(__name__)
router = APIRouter()

# ── Groq client (used for both router and generator) ─────────────
groq = Groq(api_key=settings.groq_api_key)

ROUTER_MODEL    = "llama-3.1-8b-instant"   # fast, cheap, good for classification
GENERATOR_MODEL = "openai/gpt-oss-120b"    # strong reasoning, 128K context

VALID_SECTIONS = {"papers", "news", "tools", "benchmarks", "talks"}

# Hybrid (semantic + BM25-equivalent keyword, fused via RRF) RPC function per section
HYBRID_MATCH_FN = {
    "papers":     "match_papers_hybrid",
    "news":       "match_news_hybrid",
    "tools":      "match_tools_hybrid",
    "benchmarks": "match_benchmarks_hybrid",
    "talks":      "match_talks_hybrid",
}

# Underlying Supabase table name per section — used by the new recency
# and metadata-filter shortcuts, which query tables directly rather
# than through the hybrid RPC functions.
SECTION_TABLE = {
    "papers":     "research_papers",
    "news":       "ai_news",
    "tools":      "ai_tools",
    "benchmarks": "benchmark_entries",
    "talks":      "talk_videos",
}

RRF_K = 50   # standard RRF damping constant; higher = flatter rank weighting


# ══════════════════════════════════════════════════════════════════
#  INTENT DETECTION — superlative & exact-match queries bypass retrieval
# ══════════════════════════════════════════════════════════════════
#
# Hybrid search (dense + BM25) fixes exact-term/identifier precision, but
# it CANNOT answer "what is the maximum value of column X across the whole
# table" — both retrieval methods only ever return top-K matches to a query
# string, never an aggregate scan. Ranking questions ("best/cheapest model")
# still need a direct SQL ORDER BY shortcut regardless of retrieval quality.

SUPERLATIVE_PATTERN = re.compile(
    r'\b(best|highest|lowest|cheapest|fastest|top|worst|slowest|most expensive)\b',
    re.IGNORECASE,
)

SUPERLATIVE_METRIC_MAP: dict[str, tuple[str, bool]] = {
    "cheapest":        ("input_cost_per_1m", True),
    "most expensive":  ("input_cost_per_1m", False),
    "lowest":          ("input_cost_per_1m", True),
    "fastest":         ("speed_tps", False),
    "slowest":         ("speed_tps", True),
    "highest":         ("elo_score", False),
    "best":            ("elo_score", False),
    "top":             ("elo_score", False),
    "worst":           ("elo_score", True),
}

BENCHMARK_SELECT_FIELDS = (
    "id, model_display_name, source, model_summary, strengths, weaknesses, "
    "best_for, elo_score, intelligence_score, speed_tps, "
    "input_cost_per_1m, output_cost_per_1m, arena_rank"
)

KNOWN_CHANNELS = [
    "AI Explained", "Lex Fridman", "Yannic Kilcher", "Two Minute Papers",
]


def is_superlative_query(query: str) -> bool:
    return bool(SUPERLATIVE_PATTERN.search(query))


def detect_superlative_metric(query: str) -> tuple[str, bool]:
    ql = query.lower()
    for keyword, (column, ascending) in SUPERLATIVE_METRIC_MAP.items():
        if keyword in ql:
            return column, ascending
    return "elo_score", False


def fetch_superlative_benchmark(query: str) -> Optional[dict]:
    """Direct SQL ORDER BY across the WHOLE rag_ready table — not a retrieval guess."""
    column, ascending = detect_superlative_metric(query)
    db = get_client()
    try:
        rows = (
            db.table("benchmark_entries")
            .select(BENCHMARK_SELECT_FIELDS)
            .not_.is_(column, "null")
            .order(column, desc=not ascending)
            .limit(1)
            .execute()
        ).data or []
        if rows:
            row = rows[0]
            row["_section"]     = "benchmarks"
            row["similarity"]   = 1.0
            row["_metric_used"] = column
            return row
    except Exception as e:
        log.warning(f"Superlative SQL lookup failed for column '{column}': {e}")
    return None


def extract_channel_filter(query: str) -> Optional[str]:
    ql = query.lower()
    for ch in KNOWN_CHANNELS:
        if ch.lower() in ql:
            return ch
    return None


def fetch_talks_by_channel(channel: str, top_k: int = 3) -> list[dict]:
    """Exact WHERE channel = '...' lookup — proper nouns need exact match, not similarity."""
    db = get_client()
    try:
        rows = (
            db.table("talk_videos")
            .select(
                "id, title, video_url, channel, summary, key_insights, "
                "topics_covered, people_mentioned, difficulty_level, "
                "relevance_score, fetched_at"
            )
            .eq("channel", channel)
            .order("fetched_at", desc=True)
            .limit(top_k)
            .execute()
        ).data or []
        for row in rows:
            row["_section"]   = "talks"
            row["similarity"] = 1.0
        return rows
    except Exception as e:
        log.warning(f"Channel filter lookup failed for '{channel}': {e}")
        return []


# ══════════════════════════════════════════════════════════════════
#  INTENT DETECTION — broad/intent-only queries (recency + metadata filters)
# ══════════════════════════════════════════════════════════════════
#
# "What has OpenAI announced recently" and "beginner-friendly talks" are
# not really search queries — they're disguised SQL filters. Hybrid search
# has no concept of "recently" (no time signal feeds into BM25/cosine at
# all) and no reliable way to recover a structured attribute like
# difficulty_level or pipeline_task purely from embedding similarity to
# a sentence that may not even use that exact word. Recovering these via
# better ranking (reranking) doesn't work because the relevance signal
# was never in the candidate pool's scoring to begin with — it needs to
# come from a real column lookup instead.

RECENCY_PATTERN = re.compile(
    r'\b(recent|recently|latest|new|newest|this week|today|lately)\b',
    re.IGNORECASE,
)

DIFFICULTY_KEYWORDS: dict[str, str] = {
    "beginner":     "beginner",
    "intro":        "beginner",
    "introductory": "beginner",
    "basic":        "beginner",
    "advanced":     "advanced",
    "expert":       "advanced",
}

PIPELINE_TASK_KEYWORDS: dict[str, str] = {
    "fine-tuning":      "text-generation",
    "fine tune":        "text-generation",
    "fine tuning":      "text-generation",
    "image generation": "text-to-image",
    "image editing":    "image-to-image",
    "coding":           "code-generation",
}


def is_recency_query(query: str) -> bool:
    return bool(RECENCY_PATTERN.search(query))

STOPWORDS_FOR_RECENCY = {
    "what", "has", "have", "had", "is", "are", "was", "were", "the", "a", "an",
    "any", "been", "did", "do", "does", "with", "about", "on", "in", "of", "to",
    "recently", "recent", "latest", "new", "newest", "lately", "this", "week",
    "today", "announced", "announce", "say", "said", "news", "happening",
}


def _extract_entity_terms(query: str) -> str:
    """
    Strip generic/recency words from a query, leaving only the likely
    entity/topic terms. text_search needs a focused term set — passing
    the full natural-language sentence causes plainto_tsquery to AND
    every word together, which almost never matches anything.
    """
    words = re.findall(r"[a-zA-Z0-9\-]+", query.lower())
    terms = [w for w in words if w not in STOPWORDS_FOR_RECENCY and len(w) > 2]
    return " ".join(terms) if terms else query


def fetch_recent_by_entity(query: str, section: str, top_k: int = 5) -> list[dict]:
    db    = get_client()
    entity_terms = _extract_entity_terms(query)

    rpc_fn = {
        "news": "fetch_recent_news",
        # add fetch_recent_papers / fetch_recent_tools / etc. as needed
    }.get(section)

    if not rpc_fn:
        return []

    try:
        rows = db.rpc(rpc_fn, {
            "search_terms": entity_terms,
            "match_count": top_k,
        }).execute().data or []
    except Exception as e:
        log.warning(f"Recency RPC failed for section '{section}' (terms='{entity_terms}'): {e}")
        return []

    for r in rows:
        r["_section"]   = section
        r["similarity"] = 1.0

    return rows


def detect_metadata_filter(query: str, section: str) -> Optional[dict]:
    """
    Detects category/filter-style intent ('beginner talks', 'tools for
    fine-tuning') that maps directly to a structured column already in
    the schema, rather than something embeddings need to infer from text.
    """
    ql = query.lower()
    if section == "talks":
        for kw, val in DIFFICULTY_KEYWORDS.items():
            if kw in ql:
                return {"column": "difficulty_level", "value": val}
    if section == "tools":
        for kw, val in PIPELINE_TASK_KEYWORDS.items():
            if kw in ql:
                return {"column": "pipeline_task", "value": val}
    return None


def fetch_by_metadata_filter(section: str, column: str, value: str, top_k: int = 5) -> list[dict]:
    """Direct WHERE column ILIKE value lookup, sorted by recency — a real filter, not a guess."""
    db    = get_client()
    table = SECTION_TABLE.get(section)
    if not table:
        return []

    try:
        rows = (
            db.table(table)
            .select("*")
            .ilike(column, f"%{value}%")
            .order("fetched_at", desc=True)
            .limit(top_k)
            .execute()
        ).data or []
    except Exception as e:
        log.warning(f"Metadata filter fetch failed for '{section}.{column}={value}': {e}")
        return []

    for r in rows:
        r["_section"]   = section
        r["similarity"] = 1.0

    return rows


# ══════════════════════════════════════════════════════════════════
#  REQUEST / RESPONSE MODELS
# ══════════════════════════════════════════════════════════════════

class AskRequest(BaseModel):
    query:    str            = Field(..., min_length=3, max_length=500)
    sections: Optional[list[str]] = Field(
        None,
        description="Force specific sections. None = auto-route.",
    )
    top_k:    int            = Field(5, ge=1, le=10)
    rrf_k:    int             = Field(RRF_K, ge=1, le=200,
                                      description="RRF damping constant for hybrid fusion")

class Source(BaseModel):
    index:      int
    section:    str
    title:      str
    url:        Optional[str] = None
    similarity: float

class AskResponse(BaseModel):
    answer:           str
    sources:          list[Source]
    sections_queried: list[str]
    query_rewritten:  str
    latency_ms:       int


# ══════════════════════════════════════════════════════════════════
#  STEP 1 — QUERY ROUTER
# ══════════════════════════════════════════════════════════════════

ROUTER_SYSTEM = """
You are a query router for an AI intelligence briefing platform with 5 data sections:

- papers:     academic AI/ML research papers and preprints
- news:       AI industry news, company announcements, product launches
- tools:      AI tools, libraries, open-source models, Hugging Face spaces
- benchmarks: LLM performance data, leaderboard comparisons, speed/cost analysis
- talks:      AI conference talks, video explainers, podcast summaries

Given a user query, return a JSON object with:
{
  "sections": ["section1", "section2"],
  "rewritten_query": "..."
}

Rules:
- sections: 1-3 most relevant sections. Always return at least 1.
- rewritten_query: rephrase the query to be more specific and retrieval-friendly.
  Expand abbreviations, add context. Keep it under 100 words.
- For broad queries like "what's new in AI", use ["news", "papers", "tools"].
- For model comparison questions, use ["benchmarks"].
- For "how to" or "what tool" questions, use ["tools"].
- For research/academic questions, use ["papers"].

Return ONLY valid JSON, no other text.
"""


def route_query(query: str) -> tuple[list[str], str]:
    """
    Classify query intent and rewrite for better retrieval.
    Returns (sections, rewritten_query).
    Falls back to all sections if router fails.
    """
    try:
        resp = groq.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user",   "content": query},
            ],
            temperature=0,
            max_tokens=200,
        )
        raw  = resp.choices[0].message.content.strip()
        data = json.loads(raw)

        sections = [s for s in data.get("sections", []) if s in VALID_SECTIONS]
        rewritten = data.get("rewritten_query", query)

        if not sections:
            sections = list(VALID_SECTIONS)

        return sections, rewritten

    except Exception as e:
        log.warning(f"Router failed ({e}) — defaulting to all sections")
        return list(VALID_SECTIONS), query


# ══════════════════════════════════════════════════════════════════
#  STEP 2 — HYBRID RETRIEVAL (dense + BM25-equivalent, fused via RRF)
# ══════════════════════════════════════════════════════════════════

def retrieve_hybrid(
    query_text:   str,
    query_vector: list[float],
    sections:     list[str],
    top_k:        int = 5,
    rrf_k:        int = RRF_K,
) -> list[dict]:
    """
    Run hybrid search (dense vector + keyword full-text, fused via RRF)
    across the requested sections. Each RPC call does both searches
    server-side in one round trip and returns a single fused ranking.

    query_text   — raw or rewritten query string, used for keyword/BM25 side
    query_vector — Jina embedding of the query, used for semantic side
    """
    db      = get_client()
    results = []

    for section in sections:
        fn = HYBRID_MATCH_FN[section]
        try:
            rows = db.rpc(fn, {
                "query_text":      query_text,
                "query_embedding": query_vector,
                "match_count":     top_k,
                "rrf_k":           rrf_k,
            }).execute().data or []

            for row in rows:
                row["_section"] = section
            results.extend(rows)

        except Exception as e:
            log.error(f"Hybrid retrieval failed for section '{section}': {e}")

    # similarity here is the fused RRF score, not raw cosine similarity —
    # still sortable/comparable the same way downstream
    results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════
#  STEP 2b — RETRIEVE-THEN-ROUTE FALLBACK (Architecture 2)
# ══════════════════════════════════════════════════════════════════
#
# The LLM router's guess is a fast first pass, not a gate. If hybrid
# search on the router's guessed sections produces only weak matches,
# this automatically fans out to ALL 5 sections and lets retrieval
# itself decide where the answer actually lives — using real keyword/
# semantic evidence rather than the router's text-only classification.
#
# This generalizes to any future entity (new tools, new models, new
# companies) without a hardcoded lookup list, because the correction
# signal is "did search find something strong," not "is this name in
# a list I wrote in advance."

WEAK_SCORE_THRESHOLD = 0.01
# Unused by the comparison-based logic below directly, kept as a
# documented reference point for what "weak" looks like in RRF score
# terms — see the MARGIN-based comparison in retrieve_with_fallback().


def retrieve_with_fallback(
    query_text:      str,
    query_vector:    list[float],
    router_sections: list[str],
    top_k:           int = 5,
    rrf_k:           int = RRF_K,
) -> tuple[list[dict], list[str]]:
    """
    Architecture 2: always run both the router's guess AND a full
    fan-out, then take whichever produced the stronger top result.

    A flat threshold gate doesn't work because hybrid search on the
    WRONG section can still produce a non-trivial score from loose
    keyword overlap — there's no reliable "this is definitely weak"
    cutoff to gate on. Comparing both results directly sidesteps that
    problem: the correct section's score will be meaningfully higher
    than the wrong section's score for the SAME query, because BM25
    rewards a strong, near-exact token match much more than a loose
    partial one.
    """
    primary_hits = retrieve_hybrid(query_text, query_vector, router_sections, top_k, rrf_k)
    primary_top  = primary_hits[0].get("similarity", 0) if primary_hits else 0

    all_sections  = list(VALID_SECTIONS)
    # Skip re-searching sections the router already covered
    remaining     = [s for s in all_sections if s not in router_sections]

    if not remaining:
        return primary_hits, router_sections

    fallback_hits = retrieve_hybrid(query_text, query_vector, remaining, top_k, rrf_k)
    fallback_top  = fallback_hits[0].get("similarity", 0) if fallback_hits else 0

    log.info(
        f"Fallback comparison — router guess top_score={primary_top:.4f} "
        f"({router_sections}) vs fan-out top_score={fallback_top:.4f} ({remaining})"
    )

    # A meaningfully stronger match in the unsearched sections means the
    # router's guess was wrong. Require a clear margin, not just "greater
    # than," to avoid flip-flopping on near-tied scores.
    MARGIN = 1.5   # fan-out must score at least 50% higher to override

    if fallback_top > primary_top * MARGIN:
        actual_sections = list({h["_section"] for h in fallback_hits[:top_k]})
        log.info(
            f"Routing CORRECTED: original={router_sections} -> "
            f"actual={actual_sections} "
            f"(fan-out {fallback_top:.4f} > {MARGIN}x primary {primary_top:.4f})"
        )
        # Merge both result sets, sorted by score — don't discard primary_hits
        # entirely in case the router's guess was partially right too
        combined = sorted(primary_hits + fallback_hits, key=lambda x: x.get("similarity", 0), reverse=True)
        used_sections = list({h["_section"] for h in combined[:top_k]})
        return combined[:top_k], used_sections

    return primary_hits, router_sections


# ══════════════════════════════════════════════════════════════════
#  STEP 3 — CONTEXT ASSEMBLY
# ══════════════════════════════════════════════════════════════════

def _format_record(record: dict, index: int) -> str:
    """Format a single retrieved record as a labelled context block."""
    section = record.get("_section", "unknown")
    label   = f"[{section.upper()} {index}]"
    sim     = record.get("similarity", 0)
    exact   = bool(record.get("_metric_used")) or sim == 1.0

    if section == "papers":
        lines = [
            f"{label} PAPER (match score: {sim:.3f})",
            f"Title: {record.get('title', 'N/A')}",
            f"Summary: {record.get('one_line_summary', 'N/A')}",
            f"Problem: {record.get('problem_solved', 'N/A')}",
            f"Approach: {record.get('approach_used', 'N/A')}",
            f"Results: {record.get('key_results', 'N/A')}",
            f"Tags: {', '.join(record.get('ai_tags') or [])}",
        ]

    elif section == "news":
        key_points = record.get("key_points") or []
        lines = [
            f"{label} NEWS (match score: {sim:.3f})",
            f"Title: {record.get('title', 'N/A')}",
            f"Summary: {record.get('summary', 'N/A')}",
            f"Key points: {' | '.join(key_points[:3])}",
            f"Companies: {', '.join(record.get('companies_mentioned') or [])}",
            f"Models: {', '.join(record.get('models_mentioned') or [])}",
            f"Significance: {record.get('significance_score', 'N/A')}/10",
        ]

    elif section == "tools":
        lines = [
            f"{label} TOOL (match score: {sim:.3f})",
            f"Name: {record.get('name', 'N/A')}",
            f"What it does: {record.get('what_it_does', 'N/A')}",
            f"Use cases: {' | '.join((record.get('use_cases') or [])[:3])}",
            f"Pipeline task: {record.get('pipeline_task', 'N/A')}",
            f"Language: {record.get('language', 'N/A')}",
            f"Why trending: {record.get('why_trending', 'N/A')}",
        ]

    elif section == "benchmarks":
        rank_note = ""
        if record.get("_metric_used"):
            rank_note = (
                f"\nNOTE: This record was selected because it has the {record['_metric_used']} "
                f"across the ENTIRE benchmark table (exact SQL ranking, not a retrieval guess). "
                f"Treat this as the authoritative answer for ranking questions."
            )
        lines = [
            f"{label} BENCHMARK (match score: {sim:.3f}){' [EXACT RANKING MATCH]' if exact else ''}",
            f"Model: {record.get('model_display_name', 'N/A')}",
            f"Summary: {record.get('model_summary', 'N/A')}",
            f"Strengths: {' | '.join((record.get('strengths') or [])[:3])}",
            f"Weaknesses: {' | '.join((record.get('weaknesses') or [])[:2])}",
            f"Best for: {record.get('best_for', 'N/A')}",
            f"Elo: {record.get('elo_score', 'N/A')} | "
            f"Intelligence: {record.get('intelligence_score', 'N/A')} | "
            f"Speed: {record.get('speed_tps', 'N/A')} t/s | "
            f"Cost: ${record.get('input_cost_per_1m', 'N/A')}/1M in"
            f"{rank_note}",
        ]

    elif section == "talks":
        channel_note = "\nNOTE: Retrieved via exact channel match, not search ranking." if exact else ""
        lines = [
            f"{label} TALK (match score: {sim:.3f}){' [EXACT CHANNEL MATCH]' if exact else ''}",
            f"Title: {record.get('title', 'N/A')}",
            f"Channel: {record.get('channel', 'N/A')}",
            f"Summary: {record.get('summary', 'N/A')}",
            f"Key insights: {' | '.join((record.get('key_insights') or [])[:3])}",
            f"Topics: {', '.join((record.get('topics_covered') or [])[:5])}",
            f"Difficulty: {record.get('difficulty_level', 'N/A')}"
            f"{channel_note}",
        ]

    else:
        lines = [f"{label} {str(record)[:200]}"]

    return "\n".join(line for line in lines if line)


def assemble_context(records: list[dict]) -> tuple[str, list[dict]]:
    """
    Build context string for the LLM and source list for the response.
    Returns (context_string, source_metadata_list).
    """
    context_blocks = []
    sources        = []

    for i, record in enumerate(records, 1):
        section = record.get("_section", "unknown")
        context_blocks.append(_format_record(record, i))

        url = (
            record.get("url") or
            record.get("video_url") or
            None
        )
        title = (
            record.get("title") or
            record.get("name") or
            record.get("model_display_name") or
            f"Record {i}"
        )
        sources.append({
            "index":      i,
            "section":    section,
            "title":      title,
            "url":        url,
            "similarity": round(record.get("similarity", 0), 3),
        })

    return "\n\n---\n\n".join(context_blocks), sources


# ══════════════════════════════════════════════════════════════════
#  STEP 4 — ANSWER GENERATION
# ══════════════════════════════════════════════════════════════════

GENERATOR_SYSTEM = """
You are an AI research briefing assistant. You answer questions about AI research,
industry news, tools, benchmarks, and talks using ONLY the provided context.

Rules:
1. Base every claim strictly on the provided context. Do not use outside knowledge.
2. Cite sources using their label in brackets, e.g. [PAPERS 1], [NEWS 3], [BENCHMARKS 2].
3. If the context does not contain enough information to answer, say so directly.
4. Keep answers concise and direct — 2-5 sentences for simple questions,
   structured lists for comparisons or multi-part questions.
5. For benchmark/comparison questions, use the actual numbers from the context.
   If a record is marked [EXACT RANKING MATCH], it was selected by directly
   sorting the full database on the relevant metric — treat it as the
   definitive answer for "best/cheapest/fastest" questions rather than
   comparing it against other records in the context.
6. For news questions, mention the significance score to convey importance.
7. If multiple sources agree, synthesise them into one answer.
8. If sources contradict, note the discrepancy.
9. Never blend two different records into a single claim. Each fact must be
   attributed to exactly one source label.
"""


def generate_answer(query: str, context: str) -> str:
    """Generate a grounded answer using gpt-oss-120b on Groq."""
    try:
        resp = groq.chat.completions.create(
            model=GENERATOR_MODEL,
            messages=[
                {"role": "system", "content": GENERATOR_SYSTEM},
                {"role": "user",   "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}"},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return resp.choices[0].message.content.strip()

    except Exception as e:
        log.warning(f"Groq generation failed ({e}) — trying OpenRouter fallback")
        from openai import OpenAI as OpenAIClient
        client = OpenAIClient(
            api_key  = settings.openrouter_api_key,
            base_url = "https://openrouter.ai/api/v1",
        )
        resp = client.chat.completions.create(
            model=GENERATOR_MODEL,
            messages=[
                {"role": "system", "content": GENERATOR_SYSTEM},
                {"role": "user",   "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}"},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        return resp.choices[0].message.content.strip()


# ══════════════════════════════════════════════════════════════════
#  FASTAPI ENDPOINT
# ══════════════════════════════════════════════════════════════════

@router.post("/ask", response_model=AskResponse)
@limiter.limit("10/minute")
async def ask(req: AskRequest, request: Request) -> AskResponse:
    """
    RAG endpoint. Accepts a natural language query, returns a grounded answer
    with citations linking back to the source records.

    Retrieval layers, in order:
      1. Superlative shortcut    — "best/cheapest/fastest model" → direct SQL
         ORDER BY across the whole benchmarks table.
      2. Channel shortcut        — known channel name mentioned → exact
         WHERE channel = '...' lookup.
      3. Recency shortcut        — "recently/latest/new" queries → fts
         keyword pre-filter sorted by fetched_at, since "recentness" has
         no representation in similarity scoring otherwise.
      4. Metadata filter shortcut — category-style queries ("beginner
         talks", "tools for fine-tuning") → direct WHERE column = value
         lookup on difficulty_level / pipeline_task.
      5. Hybrid search            — dense + keyword fused via RRF, with
         retrieve-then-route fallback. Covers everything else.
    Results from all layers are merged and de-duplicated before generation.
    """
    t0 = time.perf_counter()

    if req.sections:
        invalid = [s for s in req.sections if s not in VALID_SECTIONS]
        if invalid:
            raise HTTPException(400, f"Invalid sections: {invalid}. Valid: {list(VALID_SECTIONS)}")

    # Step 1 — Route
    if req.sections:
        sections, rewritten = req.sections, req.query
    else:
        sections, rewritten = route_query(req.query)
    log.info(f"Query routed to: {sections} | Rewritten: {rewritten}")

    exact_hits: list[dict] = []

    # ── Intent shortcut A — superlative benchmark queries ──────────
    if is_superlative_query(req.query) and "benchmarks" in sections:
        top_row = fetch_superlative_benchmark(req.query)
        if top_row:
            exact_hits.append(top_row)
            log.info(f"Superlative match via SQL: {top_row.get('model_display_name')} "
                     f"(metric: {top_row.get('_metric_used')})")

    # ── Intent shortcut B — exact channel-name talk queries ────────
    channel = extract_channel_filter(req.query)
    if channel and "talks" in sections:
        channel_hits = fetch_talks_by_channel(channel, top_k=req.top_k)
        if channel_hits:
            exact_hits.extend(channel_hits)
            log.info(f"Channel match via SQL: '{channel}' ({len(channel_hits)} records)")

    # ── Intent shortcut C — recency queries ("what's new with X") ──
    # "Recently/latest/new" has no signal in hybrid search's scoring at
    # all — recover it as an explicit sort, per routed section.
    if is_recency_query(req.query):
        for sec in sections:
            recency_hits = fetch_recent_by_entity(req.query, sec, top_k=req.top_k)
            if recency_hits:
                exact_hits.extend(recency_hits)
                log.info(f"Recency match via SQL: section='{sec}' ({len(recency_hits)} records)")

    # ── Intent shortcut D — metadata/category filter queries ───────
    # "beginner talks", "tools for fine-tuning" map to real columns
    # (difficulty_level, pipeline_task) rather than needing embeddings
    # to infer a structured attribute from loose text similarity.
    for sec in sections:
        filt = detect_metadata_filter(req.query, sec)
        if filt:
            filter_hits = fetch_by_metadata_filter(sec, filt["column"], filt["value"], top_k=req.top_k)
            if filter_hits:
                exact_hits.extend(filter_hits)
                log.info(f"Metadata filter match via SQL: {sec}.{filt['column']}="
                         f"{filt['value']} ({len(filter_hits)} records)")

    # Step 2 — Embed query (for the semantic half of hybrid search)
    try:
        query_vector = embed_query(rewritten)
    except Exception as e:
        raise HTTPException(503, f"Embedding service unavailable: {e}")

    # Step 3 — Hybrid retrieval with retrieve-then-route fallback.
    # Router's guessed `sections` is the fast path; if confidence is weak,
    # this automatically fans out to all 5 sections and corrects the
    # routing based on actual retrieval evidence (Architecture 2).
    # `sections` is reassigned here because fallback may have corrected it —
    # the corrected value is what gets reported in the response and logs.
    hybrid_hits, sections = retrieve_with_fallback(
        query_text=req.query,
        query_vector=query_vector,
        router_sections=sections,
        top_k=req.top_k,
        rrf_k=req.rrf_k,
    )

    # Merge: exact SQL hits first (authoritative), then hybrid hits,
    # de-duplicated by (section, id).
    seen = {(h["_section"], h.get("id")) for h in exact_hits}
    merged_hits = exact_hits + [
        h for h in hybrid_hits if (h.get("_section"), h.get("id")) not in seen
    ]

    if not merged_hits:
        return AskResponse(
            answer=(
                "No relevant records found for your query. "
                "Try rephrasing with different keywords."
            ),
            sources=[],
            sections_queried=sections,
            query_rewritten=rewritten,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    # Step 4 — Assemble context
    context, sources = assemble_context(merged_hits)

    # Step 5 — Generate
    answer = generate_answer(req.query, context)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    log.info(f"RAG complete — {len(merged_hits)} records "
             f"({len(exact_hits)} exact, {len(merged_hits) - len(exact_hits)} hybrid), "
             f"{latency_ms}ms total")

    return AskResponse(
        answer=answer,
        sources=[Source(**s) for s in sources],
        sections_queried=sections,
        query_rewritten=rewritten,
        latency_ms=latency_ms,
    )


# ── Health check ─────────────────────────────────────────────────
@router.get("/ask/health")
async def ask_health():
    """Quick check that the RAG dependencies are reachable."""
    status = {"jina": False, "groq": False, "supabase": False, "hybrid_search": False}
    try:
        embed_query("test")
        status["jina"] = True
    except Exception as e:
        status["jina_error"] = str(e)

    try:
        groq.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        status["groq"] = True
    except Exception as e:
        status["groq_error"] = str(e)

    try:
        get_client().table("research_papers").select("id").limit(1).execute()
        status["supabase"] = True
    except Exception as e:
        status["supabase_error"] = str(e)

    # Confirm the hybrid SQL functions actually exist (catches missing migration)
    try:
        db = get_client()
        dummy_vec = [0.0] * 1024
        db.rpc("match_papers_hybrid", {
            "query_text": "test",
            "query_embedding": dummy_vec,
            "match_count": 1,
            "rrf_k": RRF_K,
        }).execute()
        status["hybrid_search"] = True
    except Exception as e:
        status["hybrid_search_error"] = str(e)

    all_ok = all(status[k] for k in ["jina", "groq", "supabase", "hybrid_search"])
    return {"status": "ok" if all_ok else "degraded", **status}