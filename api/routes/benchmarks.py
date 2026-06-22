"""
api/routes/benchmarks.py — AI Radar
GET /benchmarks        → paginated list with filters
GET /benchmarks/{id}   → single model detail
"""
from fastapi import APIRouter, Query, HTTPException
from api.dependencies import get_db
from api.models import BenchmarkCard, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])

SORT_COLUMN_MAP = {
    "fetched_at":        "fetched_at",
    "average_score":     "average_score",
    "arena_rank":        "arena_rank",
    "intelligence_score": "intelligence_score",
    "elo_score":         "elo_score",
    "speed_tps":         "speed_tps",
    "input_cost_per_1m": "input_cost_per_1m",
}


@router.get("", response_model=PaginatedResponse)
def list_benchmarks(
    limit:   int = Query(default=20, ge=1, le=100),
    offset:  int = Query(default=0,  ge=0),
    source:  str = Query(
        default=None, description="open_llm_leaderboard | lmsys_arena | artificial_analysis"),
    sort_by: str = Query(default="fetched_at",
                         description="fetched_at | average_score | arena_rank | intelligence_score | elo_score | speed_tps | input_cost_per_1m"),
):
    db = get_db()

    sort_col = SORT_COLUMN_MAP.get(sort_by, "fetched_at")
    # arena_rank: lower is better → ascending
    desc = sort_col != "arena_rank"

    query = (
        db.table("benchmark_entries")
        .select("id, source, model_id, model_display_name, organisation, "
                "hf_url, license, context_window, params_billions, "
                "average_score, ifeval_score, bbh_score, math_score, "
                "gpqa_score, mmlu_pro_score, arena_rank, elo_score, "
                "num_votes, intelligence_score, speed_tps, "
                "input_cost_per_1m, output_cost_per_1m, "
                "model_summary, strengths, weaknesses, best_for, "
                "summarised_at", count="exact")
        .not_.is_("summarised_at", "null")
    )

    if source:
        query = query.eq("source", source)

    query = query.order(sort_col, desc=desc)
    response = query.range(offset, offset + limit - 1).execute()

    total = response.count or 0
    return PaginatedResponse(
        data=[BenchmarkCard(**r) for r in (response.data or [])],
        pagination=PaginationMeta(
            total=total, limit=limit, offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


@router.get("/{entry_id}", response_model=BenchmarkCard)
def get_benchmark(entry_id: str):
    db = get_db()
    response = (
        db.table("benchmark_entries")
        .select("*")
        .eq("id", entry_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=404, detail=f"Benchmark entry '{entry_id}' not found")
    return BenchmarkCard(**response.data[0])
