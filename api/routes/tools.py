"""
api/routes/tools.py — AI Radar
GET /tools       → paginated list with filters
GET /tools/{id}  → full tool detail
"""
from fastapi import APIRouter, Query, HTTPException
from api.dependencies import get_db
from api.models import ToolCard, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/tools", tags=["Tools"])

SORT_COLUMN_MAP = {
    "fetched_at":        "fetched_at",
    "significance_score": "significance_score",
    "trending_score":     "trending_score",
    "stars":              "stars",
    "likes":              "likes",
    "downloads":          "downloads",
    "votes":              "votes",
}


@router.get("", response_model=PaginatedResponse)
def list_tools(
    limit:   int = Query(default=20, ge=1, le=100),
    offset:  int = Query(default=0,  ge=0),
    source:  str = Query(
        default=None, description="github_trending | hf_hub_model | hf_spaces | product_hunt"),
    sort_by: str = Query(
        default="fetched_at", description="fetched_at | significance_score | trending_score | stars | likes | downloads | votes"),
):
    db = get_db()

    sort_col = SORT_COLUMN_MAP.get(sort_by, "fetched_at")

    query = (
        db.table("ai_tools")
        .select("id, source, url, name, description, stars, votes, likes, "
                "downloads, trending_score, language, pipeline_task, tags, "
                "author, what_it_does, use_cases, why_trending, "
                "significance_score, ai_tags, summarised_at", count="exact")
        .not_.is_("summarised_at", "null")
    )

    if source:
        query = query.eq("source", source)

    query = query.order(sort_col, desc=True)
    response = query.range(offset, offset + limit - 1).execute()

    total = response.count or 0
    return PaginatedResponse(
        data=[ToolCard(**r) for r in (response.data or [])],
        pagination=PaginationMeta(
            total=total, limit=limit, offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get("/{tool_id}", response_model=ToolCard)
def get_tool(tool_id: str):
    db = get_db()
    response = (
        db.table("ai_tools")
        .select("*")
        .eq("id", tool_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=404, detail=f"Tool '{tool_id}' not found")
    return ToolCard(**response.data[0])
