"""
api/models.py — AI Radar
Pydantic response models for all API endpoints.
Only returns fields relevant to the frontend — not raw scraped metadata.
"""
from typing import Optional
from pydantic import BaseModel


# ── Shared ────────────────────────────────────────────────────────

class PaginationMeta(BaseModel):
    total:   int
    limit:   int
    offset:  int
    has_more: bool


class PaginatedResponse(BaseModel):
    data:       list
    pagination: PaginationMeta


# ── Section 1 — Research Papers ───────────────────────────────────

class PaperCard(BaseModel):
    """Compact card view — used in list responses."""
    id:               str
    source:           str
    arxiv_id:         Optional[str]
    source_url:       str
    pdf_url:          Optional[str]
    title:            str
    abstract_preview: str
    first_author:     Optional[str]
    author_count:     int
    primary_category: Optional[str]
    published_date:   Optional[str]
    venue:            Optional[str]
    # HF Papers
    upvotes:          Optional[int]
    # OpenReview
    decision:         Optional[str]
    keywords:         list[str]
    # AI-generated
    one_line_summary: Optional[str]
    problem_solved:   Optional[str]   = None    
    approach_used:    Optional[str]   = None    
    key_results:      Optional[str]   = None    
    real_world_impact:Optional[str]   = None    
    limitations:      Optional[str]   = None    
    relevance_score:  Optional[int]
    ai_tags:          list[str]
    summarised_at:    Optional[str]


class PaperDetail(PaperCard):
    """Full detail view — includes all AI-generated fields."""
    abstract:          str
    authors:           list[str]
    all_categories:    list[str]
    problem_solved:    Optional[str]
    approach_used:     Optional[str]
    key_results:       Optional[str]
    real_world_impact: Optional[str]
    limitations:       Optional[str]


# ── Section 2 — AI News ───────────────────────────────────────────

class NewsCard(BaseModel):
    id:                  str
    source:              str
    source_display_name: str
    url:                 str
    title:               str
    content_preview:     str
    word_count:          int
    published_date:      Optional[str]
    # AI-generated
    summary:             Optional[str]
    key_points:          list[str]
    category:            Optional[str]
    companies_mentioned: list[str]
    models_mentioned:    list[str]
    significance_score:  Optional[int]
    ai_tags:             list[str]
    summarised_at:       Optional[str]


class NewsDetail(NewsCard):
    full_content: str


# ── Section 3 — Tools & GitHub ────────────────────────────────────

class ToolCard(BaseModel):
    id:                 str
    source:             str
    url:                str
    name:               str
    description:        str
    # Popularity
    stars:              Optional[int]
    votes:              Optional[int]
    likes:              Optional[int]
    downloads:          Optional[int]
    trending_score:     Optional[float]
    # Meta
    language:           Optional[str]
    pipeline_task:      Optional[str]
    tags:               list[str]
    author:             Optional[str]
    # AI-generated
    what_it_does:       Optional[str]
    use_cases:          list[str]
    why_trending:       Optional[str]
    significance_score: Optional[int]
    ai_tags:            list[str]
    summarised_at:      Optional[str]


# ── Section 4 — Benchmarks ───────────────────────────────────────

class BenchmarkCard(BaseModel):
    id:                 str
    source:             str
    model_id:           str
    model_display_name: str
    organisation:       Optional[str]
    hf_url:             Optional[str]
    license:            Optional[str]
    context_window:     Optional[str]
    # Open LLM scores
    params_billions:    Optional[float]
    average_score:      Optional[float]
    ifeval_score:       Optional[float]
    bbh_score:          Optional[float]
    math_score:         Optional[float]
    gpqa_score:         Optional[float]
    mmlu_pro_score:     Optional[float]
    # LMSYS
    arena_rank:         Optional[int]
    elo_score:          Optional[float]
    num_votes:          Optional[int]
    # Artificial Analysis
    intelligence_score: Optional[float]
    speed_tps:          Optional[float]
    input_cost_per_1m:  Optional[float]
    output_cost_per_1m: Optional[float]
    # AI-generated
    model_summary:      Optional[str]
    strengths:          list[str]
    weaknesses:         list[str]
    best_for:           Optional[str]
    summarised_at:      Optional[str]


# ── Section 5 — Talks ────────────────────────────────────────────

class TalkCard(BaseModel):
    id:                     str
    channel:                str
    video_url:              str
    title:                  str
    description:            str
    published_date:         str
    transcript_available:   bool
    transcript_word_count:  Optional[int]
    transcript_preview:     Optional[str]
    # AI-generated
    summary:                Optional[str]
    key_insights:           list[str]
    topics_covered:         list[str]
    papers_mentioned:       list[str]
    people_mentioned:       list[str]
    guest_name:             Optional[str]
    guest_affiliation:      Optional[str]
    difficulty_level:       Optional[str]
    relevance_score:        Optional[int]
    ai_tags:                list[str]
    summarised_at:          Optional[str]
    duration_seconds: Optional[int] = None    


# ── Digest ───────────────────────────────────────────────────────

class DailyDigest(BaseModel):
    date:       str
    papers:     list[PaperCard]
    news:       list[NewsCard]
    tools:      list[ToolCard]
    benchmarks: list[BenchmarkCard]
    talks:      list[TalkCard]


# ── Status ───────────────────────────────────────────────────────

class SectionStatus(BaseModel):
    total:         int
    summarised:    int
    pending:       int
    last_fetched:  Optional[str]


class PipelineStatus(BaseModel):
    papers:     SectionStatus
    news:       SectionStatus
    tools:      SectionStatus
    benchmarks: SectionStatus
    talks:      SectionStatus
