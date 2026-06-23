"""
api/routes/status.py — AI Radar
GET /status  → pipeline health: counts, pending items, last fetch time
"""
from fastapi import APIRouter
from api.dependencies import get_db
from api.models import PipelineStatus, SectionStatus

router = APIRouter(prefix="/status", tags=["Status"])

TABLE_MAP = {
    "papers":     "research_papers",
    "news":       "ai_news",
    "tools":      "ai_tools",
    "benchmarks": "benchmark_entries",
    "talks":      "talk_videos",
}


def _section_status(table: str) -> SectionStatus:
    db = get_db()

    # total rows
    total_res = db.table(table).select("id", count="exact").execute()
    total     = total_res.count or 0

    # summarised rows
    summ_res  = (
        db.table(table)
        .select("id", count="exact")
        .not_.is_("summarised_at", "null")
        .execute()
    )
    summarised = summ_res.count or 0

    # last fetched_at
    last_res = (
        db.table(table)
        .select("fetched_at")
        .order("fetched_at", desc=True)
        .limit(1)
        .execute()
    )
    last_fetched = (
        last_res.data[0]["fetched_at"] if last_res.data else None
    )

    return SectionStatus(
        total=total,
        summarised=summarised,
        pending=total - summarised,
        last_fetched=last_fetched,
    )


@router.get("", response_model=PipelineStatus)
def get_status():
    """Returns total, summarised, pending counts per section + last fetch time."""
    return PipelineStatus(
        papers=    _section_status(TABLE_MAP["papers"]),
        news=      _section_status(TABLE_MAP["news"]),
        tools=     _section_status(TABLE_MAP["tools"]),
        benchmarks=_section_status(TABLE_MAP["benchmarks"]),
        talks=     _section_status(TABLE_MAP["talks"]),
    )

@router.get("/debug")
def debug_status():
    """Temporary debug endpoint — remove after fixing."""
    db = get_db()
    try:
        res = db.table("research_papers").select("id", count="exact").execute()
        return {
            "count": res.count,
            "data_length": len(res.data) if res.data else 0,
            "first_row": res.data[0] if res.data else None,
            "raw_count": res.count,
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}
