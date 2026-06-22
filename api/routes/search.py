"""
api/routes/search.py — AI Radar
GET /search?q=...&sections=...
Full-text search across any combination of sections.
Uses Supabase's built-in text search (ilike) on AI-generated summary fields.
This is basic text search — will be replaced by vector RAG search later.
"""
from fastapi import APIRouter, Query
from api.dependencies import get_db
from api.models import (
    PaperCard, NewsCard, ToolCard,
    BenchmarkCard, TalkCard,
)

router = APIRouter(prefix="/search", tags=["Search"])

ALL_SECTIONS = {"papers", "news", "tools", "benchmarks", "talks"}


def _search_papers(q: str, limit: int) -> list[PaperCard]:
    db = get_db()
    response = (
        db.table("research_papers")
        .select("*")
        .not_.is_("summarised_at", "null")
        .or_(f"title.ilike.%{q}%,one_line_summary.ilike.%{q}%,abstract_preview.ilike.%{q}%")
        .order("relevance_score", desc=True)
        .limit(limit)
        .execute()
    )
    return [PaperCard(**r) for r in (response.data or [])]


def _search_news(q: str, limit: int) -> list[NewsCard]:
    db = get_db()
    response = (
        db.table("ai_news")
        .select("id, source, source_display_name, url, title, content_preview, "
                "word_count, published_date, summary, key_points, category, "
                "companies_mentioned, models_mentioned, significance_score, "
                "ai_tags, summarised_at")
        .not_.is_("summarised_at", "null")
        .or_(f"title.ilike.%{q}%,summary.ilike.%{q}%")
        .order("significance_score", desc=True)
        .limit(limit)
        .execute()
    )
    return [NewsCard(**r) for r in (response.data or [])]


def _search_tools(q: str, limit: int) -> list[ToolCard]:
    db = get_db()
    response = (
        db.table("ai_tools")
        .select("id, source, url, name, description, stars, votes, likes, "
                "downloads, trending_score, language, pipeline_task, tags, "
                "author, what_it_does, use_cases, why_trending, "
                "significance_score, ai_tags, summarised_at")
        .not_.is_("summarised_at", "null")
        .or_(f"name.ilike.%{q}%,description.ilike.%{q}%,what_it_does.ilike.%{q}%")
        .order("significance_score", desc=True)
        .limit(limit)
        .execute()
    )
    return [ToolCard(**r) for r in (response.data or [])]


def _search_benchmarks(q: str, limit: int) -> list[BenchmarkCard]:
    db = get_db()
    response = (
        db.table("benchmark_entries")
        .select("id, source, model_id, model_display_name, organisation, "
                "hf_url, license, context_window, params_billions, "
                "average_score, ifeval_score, bbh_score, math_score, "
                "gpqa_score, mmlu_pro_score, arena_rank, elo_score, "
                "num_votes, intelligence_score, speed_tps, "
                "input_cost_per_1m, output_cost_per_1m, "
                "model_summary, strengths, weaknesses, best_for, summarised_at")
        .not_.is_("summarised_at", "null")
        .or_(f"model_display_name.ilike.%{q}%,model_summary.ilike.%{q}%,best_for.ilike.%{q}%")
        .order("average_score", desc=True)
        .limit(limit)
        .execute()
    )
    return [BenchmarkCard(**r) for r in (response.data or [])]


def _search_talks(q: str, limit: int) -> list[TalkCard]:
    db = get_db()
    response = (
        db.table("talk_videos")
        .select("id, channel, video_url, title, description, published_date, "
                "transcript_available, transcript_word_count, transcript_preview, "
                "summary, key_insights, topics_covered, papers_mentioned, "
                "people_mentioned, guest_name, guest_affiliation, "
                "difficulty_level, relevance_score, ai_tags, summarised_at")
        .not_.is_("summarised_at", "null")
        .or_(f"title.ilike.%{q}%,summary.ilike.%{q}%")
        .order("relevance_score", desc=True)
        .limit(limit)
        .execute()
    )
    return [TalkCard(**r) for r in (response.data or [])]


@router.get("")
def search(
    q:        str = Query(..., min_length=2, description="Search query"),
    sections: str = Query(default="papers,news,tools,benchmarks,talks",
                          description="Comma-separated sections to search"),
    limit:    int = Query(default=5, ge=1, le=20,
                          description="Max results per section"),
):
    """
    Full-text search across selected sections.
    Returns a dict with results grouped by section.
    """
    requested = {s.strip().lower() for s in sections.split(",") if s.strip()}
    active    = requested & ALL_SECTIONS

    results = {}

    if "papers"     in active: results["papers"]     = _search_papers(q, limit)
    if "news"       in active: results["news"]        = _search_news(q, limit)
    if "tools"      in active: results["tools"]       = _search_tools(q, limit)
    if "benchmarks" in active: results["benchmarks"]  = _search_benchmarks(q, limit)
    if "talks"      in active: results["talks"]       = _search_talks(q, limit)

    total = sum(len(v) for v in results.values())
    return {"query": q, "total": total, "results": results}
