"""
api/routes/papers.py — AI Radar
GET /papers       → paginated list with filters
GET /papers/{id}  → full detail of one paper
"""
from fastapi import APIRouter, Query, HTTPException
from api.dependencies import get_db
from api.models import PaperCard, PaperDetail, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/papers", tags=["Papers"])


@router.get("", response_model=PaginatedResponse)
def list_papers(
    limit:    int   = Query(default=20, ge=1, le=100),
    offset:   int   = Query(default=0,  ge=0),
    date:     str   = Query(default=None, description="Filter by published_date YYYY-MM-DD"),
    source:   str   = Query(default=None, description="arxiv | hf_daily_papers | openreview"),
    category: str   = Query(default=None, description="e.g. cs.AI, cs.LG"),
    sort_by:  str   = Query(default="fetched_at", description="fetched_at | published_date | relevance_score | upvotes"),
):
    db = get_db()

    query = (
        db.table("research_papers")
        .select("*", count="exact")
        .not_.is_("summarised_at", "null")   # only summarised records
    )

    if date:
        query = query.eq("published_date", date)
    if source:
        query = query.eq("source", source)
    if category:
        query = query.eq("primary_category", category)

    # Sort
    desc = sort_by in ("fetched_at", "relevance_score", "upvotes", "published_date")
    query = query.order(sort_by, desc=desc)

    response = query.range(offset, offset + limit - 1).execute()

    total = response.count or 0
    return PaginatedResponse(
        data=[PaperCard(**r) for r in (response.data or [])],
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str):
    db = get_db()
    response = db.table("research_papers").select("*").eq("id", paper_id).limit(1).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail=f"Paper '{paper_id}' not found")
    return PaperDetail(**response.data[0])
