"""
api/routes/digest.py — AI Radar
GET /digest/today  → top items from all sections for today's briefing
GET /digest/{date} → digest for a specific date (YYYY-MM-DD)
"""
from datetime import date as date_type
from fastapi import APIRouter
from api.dependencies import get_db
from api.models import (
    DailyDigest, PaperCard, NewsCard,
    ToolCard, BenchmarkCard, TalkCard,
)

router = APIRouter(prefix="/digest", tags=["Digest"])


def _fetch_top(table: str, model, sort_col: str, limit: int,
               date_col: str = None, date_val: str = None,
               desc: bool = True, extra_filters: dict = None):
    db = get_db()
    query = (
        db.table(table)
        .select("*")
        .not_.is_("summarised_at", "null")
    )
    if date_col and date_val:
        query = query.eq(date_col, date_val)
    if extra_filters:
        for col, val in extra_filters.items():
            query = query.eq(col, val)

    query = query.order(sort_col, desc=desc).limit(limit)
    response = query.execute()
    return [model(**r) for r in (response.data or [])]


def _build_digest(target_date: str) -> DailyDigest:
    papers = _fetch_top(
        "research_papers", PaperCard,
        sort_col="relevance_score", limit=5,
        date_col="published_date", date_val=target_date,
    )
    # Fall back to recent if no papers for exact date
    if not papers:
        papers = _fetch_top(
            "research_papers", PaperCard,
            sort_col="relevance_score", limit=5,
        )

    news = _fetch_top(
        "ai_news", NewsCard,
        sort_col="significance_score", limit=5,
        date_col="published_date", date_val=target_date,
    )
    if not news:
        news = _fetch_top(
            "ai_news", NewsCard,
            sort_col="significance_score", limit=5,
        )

    tools = _fetch_top(
        "ai_tools", ToolCard,
        sort_col="significance_score", limit=5,
    )

    benchmarks = _fetch_top(
        "benchmark_entries", BenchmarkCard,
        sort_col="average_score", limit=5,
        extra_filters={"source": "open_llm_leaderboard"},
    )

    talks = _fetch_top(
        "talk_videos", TalkCard,
        sort_col="relevance_score", limit=3,
    )

    return DailyDigest(
        date=target_date,
        papers=papers,
        news=news,
        tools=tools,
        benchmarks=benchmarks,
        talks=talks,
    )


@router.get("/today", response_model=DailyDigest)
def get_today_digest():
    """Returns top items from all 5 sections for today."""
    today = str(date_type.today())
    return _build_digest(today)


@router.get("/{digest_date}", response_model=DailyDigest)
def get_digest_by_date(digest_date: str):
    """
    Returns top items from all 5 sections for a specific date.
    digest_date format: YYYY-MM-DD
    """
    return _build_digest(digest_date)
