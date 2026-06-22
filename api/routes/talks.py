"""
api/routes/talks.py — AI Radar
GET /talks       → paginated list with filters
GET /talks/{id}  → single talk detail
"""
from fastapi import APIRouter, Query, HTTPException
from api.dependencies import get_db
from api.models import TalkCard, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/talks", tags=["Talks"])

VALID_CHANNELS = {
    "Lex Fridman", "Yannic Kilcher",
    "Two Minute Papers", "AI Explained",
}


@router.get("", response_model=PaginatedResponse)
def list_talks(
    limit:      int = Query(default=20, ge=1, le=100),
    offset:     int = Query(default=0,  ge=0),
    channel:    str = Query(default=None, description="Lex Fridman | Yannic Kilcher | Two Minute Papers | AI Explained"),
    difficulty: str = Query(default=None, description="Beginner | Intermediate | Advanced"),
    sort_by:    str = Query(default="fetched_at", description="fetched_at | relevance_score | published_date"),
):
    db = get_db()

    query = (
        db.table("talk_videos")
        .select("id, channel, video_url, title, description, published_date, "
                "transcript_available, transcript_word_count, transcript_preview, "
                "summary, key_insights, topics_covered, papers_mentioned, "
                "people_mentioned, guest_name, guest_affiliation, "
                "difficulty_level, relevance_score, ai_tags, summarised_at",
                count="exact")
        .not_.is_("summarised_at", "null")
    )

    if channel:
        query = query.eq("channel", channel)
    if difficulty:
        query = query.eq("difficulty_level", difficulty)

    desc = sort_by in ("fetched_at", "relevance_score", "published_date")
    query = query.order(sort_by, desc=desc)
    response = query.range(offset, offset + limit - 1).execute()

    total = response.count or 0
    return PaginatedResponse(
        data=[TalkCard(**r) for r in (response.data or [])],
        pagination=PaginationMeta(
            total=total, limit=limit, offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get("/{talk_id}", response_model=TalkCard)
def get_talk(talk_id: str):
    db = get_db()
    response = (
        db.table("talk_videos")
        .select("*")
        .eq("id", talk_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail=f"Talk '{talk_id}' not found")
    return TalkCard(**response.data[0])
