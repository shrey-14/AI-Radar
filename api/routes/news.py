"""
api/routes/news.py — AI Radar
GET /news       → paginated list with filters
GET /news/{id}  → full article detail
"""
from fastapi import APIRouter, Query, HTTPException
from api.dependencies import get_db
from api.models import NewsCard, NewsDetail, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/news", tags=["News"])

VALID_SOURCES = {
    "anthropic", "openai", "google_deepmind",
    "meta_ai", "tldr_ai", "techcrunch_ai", "import_ai",
}

VALID_CATEGORIES = {
    "product_launch", "research", "partnership",
    "funding", "policy", "safety", "open_source", "general",
}


@router.get("", response_model=PaginatedResponse)
def list_news(
    limit:    int = Query(default=20, ge=1, le=100),
    offset:   int = Query(default=0,  ge=0),
    date:     str = Query(default=None, description="Filter by published_date YYYY-MM-DD"),
    source:   str = Query(default=None, description="anthropic | openai | google_deepmind | meta_ai | tldr_ai | techcrunch_ai | import_ai"),
    category: str = Query(default=None, description="product_launch | research | partnership | funding | policy | safety | open_source | general"),
    sort_by:  str = Query(default="fetched_at", description="fetched_at | significance_score | published_date"),
):
    db = get_db()

    query = (
        db.table("ai_news")
        .select("id, source, source_display_name, url, title, content_preview, "
                "word_count, published_date, summary, key_points, category, "
                "companies_mentioned, models_mentioned, significance_score, "
                "ai_tags, summarised_at", count="exact")
        .not_.is_("summarised_at", "null")
    )

    if date:
        query = query.eq("published_date", date)
    if source:
        query = query.eq("source", source)
    if category:
        query = query.eq("category", category)

    desc = sort_by in ("fetched_at", "significance_score", "published_date")
    query = query.order(sort_by, desc=desc)

    response = query.range(offset, offset + limit - 1).execute()

    total = response.count or 0
    return PaginatedResponse(
        data=[NewsCard(**r) for r in (response.data or [])],
        pagination=PaginationMeta(
            total=total, limit=limit, offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get("/{article_id}", response_model=NewsDetail)
def get_article(article_id: str):
    db = get_db()
    response = (
        db.table("ai_news")
        .select("*")
        .eq("id", article_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found")
    return NewsDetail(**response.data[0])
