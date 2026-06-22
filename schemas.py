"""
schemas.py — Epoch AI Intelligence Agent
=========================================
Pydantic schemas for all 5 sections.

Final confirmed sources (21 total, Semantic Scholar excluded):

  Section 1 — Papers    (3): arXiv · HF Daily Papers · OpenReview
  Section 2 — News      (7): Anthropic · OpenAI · DeepMind · Meta AI
                              TLDR AI · TechCrunch AI · Import AI
  Section 3 — Tools     (4): GitHub Trending · HF Hub · HF Spaces · Product Hunt
  Section 4 — Benchmarks(3): Open LLM Leaderboard · LMSYS Arena · Artificial Analysis
  Section 5 — Talks     (4): Lex Fridman · Yannic Kilcher · Two Minute Papers · AI Explained
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════════════
#  ENUMS
# ══════════════════════════════════════════════════════════════════

class PaperSource(str, Enum):
    ARXIV      = "arxiv"
    HF_PAPERS  = "hf_daily_papers"
    OPENREVIEW = "openreview"


class NewsSource(str, Enum):
    ANTHROPIC  = "anthropic"
    OPENAI     = "openai"
    DEEPMIND   = "google_deepmind"
    META_AI    = "meta_ai"
    TLDR_AI    = "tldr_ai"
    TECHCRUNCH = "techcrunch_ai"
    IMPORT_AI  = "import_ai"


class ToolSource(str, Enum):
    GITHUB_TRENDING = "github_trending"
    HF_HUB          = "hf_hub_model"
    HF_SPACES        = "hf_spaces"
    PRODUCT_HUNT     = "product_hunt"


class BenchmarkSource(str, Enum):
    OPEN_LLM   = "open_llm_leaderboard"
    LMSYS      = "lmsys_arena"
    ARTIFICIAL = "artificial_analysis"


class TalkChannel(str, Enum):
    LEX_FRIDMAN       = "Lex Fridman"
    YANNIC_KILCHER    = "Yannic Kilcher"
    TWO_MINUTE_PAPERS = "Two Minute Papers"
    AI_EXPLAINED      = "AI Explained"


class NewsCategory(str, Enum):
    PRODUCT_LAUNCH = "product_launch"
    RESEARCH       = "research"
    PARTNERSHIP    = "partnership"
    FUNDING        = "funding"
    POLICY         = "policy"
    SAFETY         = "safety"
    OPEN_SOURCE    = "open_source"
    GENERAL        = "general"


# ══════════════════════════════════════════════════════════════════
#  SECTION 1 — RESEARCH PAPERS
#  Sources: arXiv · HF Daily Papers · OpenReview
# ══════════════════════════════════════════════════════════════════

class ResearchPaperLLMFields(BaseModel):
    """Only the fields the LLM generates — passed to with_structured_output.
    Uses plain non-Optional types with empty defaults to keep the JSON schema
    simple and avoid Groq function-call validation issues with nullable types."""
    one_line_summary: str = ""
    problem_solved: str = ""
    approach_used: str = ""
    key_results: str = ""
    real_world_impact: str = ""
    limitations: str = ""
    relevance_score: int = 5
    ai_tags: list[str] = Field(default_factory=list)

    @field_validator("ai_tags", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


class ResearchPaper(BaseModel):
    """
    Unified schema for all 3 research paper sources.
    Deduplication key: arxiv_id
    (OpenReview papers may not have one — use openreview_note_id as fallback)
    """

    # ── Identity ─────────────────────────────────────────────────
    id: str = Field(
        description="Unique record ID: '{source}_{arxiv_id}' or '{source}_{note_id}'"
    )
    source: PaperSource
    arxiv_id: Optional[str] = Field(
        None,
        description="arXiv paper ID e.g. '2605.30353'. Primary dedup key. "
                    "Present in arXiv and HF Papers. May be absent in OpenReview."
    )
    source_url: str = Field(
        description=(
            "Canonical URL to view this paper:\n"
            "  arXiv      -> https://arxiv.org/abs/{arxiv_id}\n"
            "  HF Papers  -> https://huggingface.co/papers/{arxiv_id}\n"
            "  OpenReview -> https://openreview.net/forum?id={forum_id}"
        )
    )
    pdf_url: Optional[str] = Field(
        None,
        description=(
            "Direct PDF link:\n"
            "  arXiv      -> https://arxiv.org/pdf/{arxiv_id}\n"
            "  HF Papers  -> https://arxiv.org/pdf/{arxiv_id}\n"
            "  OpenReview -> https://openreview.net/pdf?id={forum_id}"
        )
    )

    # ── Core Content ─────────────────────────────────────────────
    title: str
    abstract: str = Field(
        description="Full abstract text — fed to LLM for summarisation"
    )
    abstract_preview: str = Field(
        description="First 300 chars of abstract for card/list display"
    )

    # ── Authors ──────────────────────────────────────────────────
    authors: list[str] = Field(
        default_factory=list,
        description="Full ordered author list"
    )
    first_author: Optional[str] = Field(
        None,
        description="Lead author name for compact display"
    )
    author_count: int = Field(default=0)

    # ── Classification ───────────────────────────────────────────
    primary_category: Optional[str] = Field(
        None,
        description=(
            "Primary research category:\n"
            "  arXiv      -> cs.AI / cs.LG / cs.CL / cs.CV / cs.NE / stat.ML\n"
            "  OpenReview -> primary_area field"
        )
    )
    all_categories: list[str] = Field(
        default_factory=list,
        description=(
            "All categories this paper belongs to:\n"
            "  arXiv      -> full categories list\n"
            "  OpenReview -> subject_areas + keywords"
        )
    )

    # ── Dates ────────────────────────────────────────────────────
    published_date: Optional[str] = Field(
        None,
        description=(
            "Paper date (YYYY-MM-DD):\n"
            "  arXiv      -> submitted_date\n"
            "  HF Papers  -> published_date\n"
            "  OpenReview -> created_date (cdate)"
        )
    )

    # ── Venue / Conference ───────────────────────────────────────
    venue: Optional[str] = Field(
        None,
        description=(
            "Conference or journal:\n"
            "  OpenReview -> venueid e.g. 'NeurIPS 2024', 'ICLR 2025'\n"
            "  arXiv / HF -> None unless journal_ref is present"
        )
    )

    # ── HuggingFace Daily Papers only ────────────────────────────
    upvotes: Optional[int] = Field(
        None,
        description="[HF Papers only] Community upvotes — signals trending interest"
    )
    num_comments: Optional[int] = Field(
        None,
        description="[HF Papers only] Discussion comment count"
    )
    featured_date: Optional[str] = Field(
        None,
        description="[HF Papers only] Date the paper was featured on HF daily feed"
    )
    thumbnail: Optional[str] = Field(
        None,
        description="[HF Papers only] Thumbnail image URL if available"
    )

    # ── OpenReview only ──────────────────────────────────────────
    decision: Optional[str] = Field(
        None,
        description="[OpenReview only] Accept / Reject / Withdrawn"
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="[OpenReview only] Author-provided keyword tags"
    )
    openreview_note_id: Optional[str] = Field(
        None,
        description="[OpenReview only] Internal note ID — fallback dedup key when arxiv_id is absent"
    )

    # ── AI-Generated Fields (filled by summariser agent) ─────────
    one_line_summary: Optional[str] = Field(
        None,
        description="[LLM] One sentence: what this paper does and why it matters"
    )
    problem_solved: Optional[str] = Field(
        None,
        description="[LLM] What specific problem does this paper address?"
    )
    approach_used: Optional[str] = Field(
        None,
        description="[LLM] What method, technique, or architecture did they use?"
    )
    key_results: Optional[str] = Field(
        None,
        description="[LLM] Main findings, benchmark scores, or performance improvements"
    )
    real_world_impact: Optional[str] = Field(
        None,
        description="[LLM] What does this paper enable or improve in practice?"
    )
    limitations: Optional[str] = Field(
        None,
        description="[LLM] Known weaknesses, constraints, or gaps acknowledged by authors"
    )
    relevance_score: Optional[int] = Field(
        None, ge=1, le=10,
        description="[LLM] Importance for the AI community right now (1=niche, 10=landmark)"
    )
    ai_tags: list[str] = Field(
        default_factory=list,
        description="[LLM] Topic tags e.g. ['RAG', 'reasoning', 'multimodal', 'safety', 'agents']"
    )

    # ── Pipeline Meta ────────────────────────────────────────────
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    summarised_at: Optional[datetime] = None
    is_duplicate: bool = Field(
        default=False,
        description="True if another record with the same arxiv_id already exists in DB"
    )

    @field_validator("authors", "all_categories", "ai_tags", "keywords", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    class Config:
        use_enum_values = True


# ══════════════════════════════════════════════════════════════════
#  SECTION 2 — AI NEWS
#  Sources: Anthropic · OpenAI · DeepMind · Meta AI (Crawl4AI)
#           TLDR AI · TechCrunch AI · Import AI
# ══════════════════════════════════════════════════════════════════

class AINewsArticleLLMFields(BaseModel):
    """Only the fields the LLM generates for news articles."""
    summary:             str       = ""
    key_points:          list[str] = Field(default_factory=list)
    category:            str       = ""
    companies_mentioned: list[str] = Field(default_factory=list)
    models_mentioned:    list[str] = Field(default_factory=list)
    significance_score:  int       = 5
    ai_tags:             list[str] = Field(default_factory=list)

    @field_validator("key_points", "companies_mentioned",
                     "models_mentioned", "ai_tags", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []

class AINewsArticle(BaseModel):
    """
    Unified schema for all 7 AI news sources.
    Anthropic, OpenAI, DeepMind, TLDR AI, TechCrunch, Import AI -> RSS + Crawl4AI
    Meta AI -> Crawl4AI only (no RSS feed exists)
    All confirmed delivering full content in notebook.
    """

    # ── Identity ─────────────────────────────────────────────────
    id: str = Field(
        description="SHA256 hash of article URL — primary dedup key"
    )
    source: NewsSource
    source_display_name: str = Field(
        description="Human-readable label e.g. 'Google DeepMind', 'TechCrunch AI'"
    )
    url: str = Field(
        description="Canonical article URL"
    )

    # ── Core Content ─────────────────────────────────────────────
    title: str
    full_content: str = Field(
        description="Full article text — fetched via RSS body or Crawl4AI markdown"
    )
    content_preview: str = Field(
        description="First 300 chars of full_content for card/list display"
    )
    word_count: int = Field(
        description="Total word count of full_content"
    )

    # ── Dates ────────────────────────────────────────────────────
    published_date: Optional[str] = Field(
        None,
        description="Publication date (YYYY-MM-DD) parsed from RSS published field"
    )

    # ── AI-Generated Fields ───────────────────────────────────────
    summary: Optional[str] = Field(
        None,
        description="[LLM] 3-5 sentence structured summary of the article"
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="[LLM] 3-5 bullet-point takeaways from the article"
    )
    category: Optional[NewsCategory] = Field(
        None,
        description="[LLM] Article type classification"
    )
    companies_mentioned: list[str] = Field(
        default_factory=list,
        description="[LLM] AI companies or labs mentioned e.g. ['OpenAI', 'Google', 'Mistral']"
    )
    models_mentioned: list[str] = Field(
        default_factory=list,
        description="[LLM] Specific AI models referenced e.g. ['GPT-5', 'Gemini 2.0', 'Claude 4']"
    )
    significance_score: Optional[int] = Field(
        None, ge=1, le=10,
        description="[LLM] How important is this news for the AI industry? (1=minor, 10=major)"
    )
    ai_tags: list[str] = Field(
        default_factory=list,
        description="[LLM] Topic tags e.g. ['multimodal', 'agents', 'safety', 'open-source', 'funding']"
    )

    # ── Pipeline Meta ────────────────────────────────────────────
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    summarised_at: Optional[datetime] = None
    is_duplicate: bool = Field(
        default=False,
        description="True if same URL hash already exists in DB"
    )

    @field_validator("key_points", "companies_mentioned", "models_mentioned", "ai_tags", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    class Config:
        use_enum_values = True


# ══════════════════════════════════════════════════════════════════
#  SECTION 3 — TOOLS & GITHUB
#  Sources: GitHub Trending · HF Hub Models · HF Spaces · Product Hunt
# ══════════════════════════════════════════════════════════════════

class AIToolLLMFields(BaseModel):
    """Only the fields the LLM generates for tools and repos."""
    what_it_does:       str       = ""
    use_cases:          list[str] = Field(default_factory=list)
    why_trending:       str       = ""
    significance_score: int       = 5
    ai_tags:            list[str] = Field(default_factory=list)

    @field_validator("use_cases", "ai_tags", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []

class AITool(BaseModel):
    """
    Unified schema for all 4 tools & GitHub sources.
    Source-specific fields are Optional — only populated
    when that specific source is used.
    """

    # ── Identity ─────────────────────────────────────────────────
    id: str = Field(
        description="'{source}_{slugified_name}' e.g. 'github_trending_crawl4ai'"
    )
    source: ToolSource
    url: str = Field(
        description=(
            "Primary URL:\n"
            "  GitHub Trending -> https://github.com/{owner}/{repo}\n"
            "  HF Hub          -> https://huggingface.co/{model_id}\n"
            "  HF Spaces       -> https://huggingface.co/spaces/{space_id}\n"
            "  Product Hunt    -> producthunt.com URL"
        )
    )

    # ── Core Content ─────────────────────────────────────────────
    name: str = Field(
        description=(
            "Display name:\n"
            "  GitHub   -> '{owner}/{repo}' e.g. 'unclecode/crawl4ai'\n"
            "  HF Hub   -> model_id e.g. 'meta-llama/Llama-3.1-70B'\n"
            "  HF Space -> space_id e.g. 'black-forest-labs/FLUX.1-schnell'\n"
            "  PH       -> product name e.g. 'StoreClaw'"
        )
    )
    description: str = Field(
        description="One-line description: GitHub about field, HF model card tagline, or PH tagline"
    )

    # ── Popularity Signals ────────────────────────────────────────
    stars: Optional[int] = Field(None, description="[GitHub Trending] Star count")
    votes: Optional[int] = Field(None, description="[Product Hunt] Community upvote count")
    likes: Optional[int] = Field(None, description="[HF Hub / HF Spaces] Like count on HuggingFace")
    downloads: Optional[int] = Field(None, description="[HF Hub] Total all-time download count")
    trending_score: Optional[float] = Field(
        None,
        description="[HF Hub] HuggingFace internal trending score — measures momentum"
    )

    # ── Classification / Tags ─────────────────────────────────────
    tags: list[str] = Field(
        default_factory=list,
        description="Tags from source: GitHub topics, HF tags, or PH topics"
    )
    language: Optional[str] = Field(None, description="[GitHub Trending] Primary programming language e.g. 'Python'")
    pipeline_task: Optional[str] = Field(None, description="[HF Hub] Pipeline task e.g. 'text-generation', 'image-classification'")
    sdk: Optional[str] = Field(None, description="[HF Spaces] Space SDK: 'gradio', 'streamlit', or 'docker'")
    license: Optional[str] = Field(None, description="[HF Hub] License type e.g. 'mit', 'apache-2.0', 'llama3'")

    # ── Author / Owner ────────────────────────────────────────────
    author: Optional[str] = Field(
        None,
        description=(
            "Creator:\n"
            "  GitHub   -> repo owner username or org\n"
            "  HF Hub   -> model author or org\n"
            "  HF Space -> space author or org"
        )
    )

    # ── HF Hub specific ───────────────────────────────────────────
    base_model: Optional[str] = Field(None, description="[HF Hub] Base model this was fine-tuned from")
    last_modified: Optional[str] = Field(None, description="[HF Hub] Last modification date (YYYY-MM-DD)")
    framework: Optional[str] = Field(None, description="[HF Hub] ML framework e.g. 'transformers', 'diffusers', 'peft'")

    # ── Product Hunt specific ─────────────────────────────────────
    website_url: Optional[str] = Field(None, description="[Product Hunt] Actual product website URL")
    launch_date: Optional[str] = Field(None, description="[Product Hunt] Date launched on Product Hunt (YYYY-MM-DD)")

    # ── AI-Generated Fields ───────────────────────────────────────
    what_it_does: Optional[str] = Field(None, description="[LLM] Plain English explanation of what this tool/model/repo does")
    use_cases: list[str] = Field(default_factory=list, description="[LLM] 2-3 concrete practical use cases")
    why_trending: Optional[str] = Field(None, description="[LLM] Why is this gaining traction right now?")
    significance_score: Optional[int] = Field(None, ge=1, le=10, description="[LLM] How notable is this for the AI community? (1=minor, 10=landmark)")
    ai_tags: list[str] = Field(default_factory=list, description="[LLM] Topic tags e.g. ['fine-tuning', 'RAG', 'agents', 'vision', 'TTS']")

    # ── Pipeline Meta ────────────────────────────────────────────
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    summarised_at: Optional[datetime] = None
    is_duplicate: bool = False

    @field_validator("tags", "use_cases", "ai_tags", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("stars", "votes", "likes", "downloads", "trending_score",
                     "significance_score", mode="before")
    @classmethod
    def coerce_numeric(cls, v):
        if isinstance(v, str) and v.strip().upper() in ("N/A", "NA", "NULL", "NONE", ""):
            return None
        return v

    class Config:
        use_enum_values = True


# ══════════════════════════════════════════════════════════════════
#  SECTION 4 — BENCHMARKS & LEADERBOARDS
#  Sources: Open LLM Leaderboard · LMSYS Arena · Artificial Analysis
# ══════════════════════════════════════════════════════════════════

class BenchmarkEntryLLMFields(BaseModel):
    """Only the fields the LLM generates — passed to with_structured_output."""
    model_summary: Optional[str] = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    best_for: Optional[str] = None

    @field_validator("strengths", "weaknesses", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("model_summary", "best_for", mode="before")
    @classmethod
    def coerce_str(cls, v):
        if isinstance(v, str) and v.strip().upper() in ("NULL", "N/A", "NA", "NONE", ""):
            return None
        return v

class BenchmarkEntry(BaseModel):
    """
    Unified schema for all 3 benchmark sources.
    Each source tracks completely different metrics
    so most score fields are Optional.
    """

    # ── Identity ─────────────────────────────────────────────────
    id: str = Field(description="'{source}_{model_id_slug}'")
    source: BenchmarkSource
    model_id: str = Field(description="Model identifier from the leaderboard")
    model_display_name: str = Field(description="Clean display name e.g. 'Qwen 2.5-72B Instruct'")
    organisation: Optional[str] = Field(
        None,
        description="[LMSYS / AA] Developer or organisation e.g. 'Anthropic', 'Google', 'Meta'"
    )
    hf_url: Optional[str] = Field(None, description="[Open LLM] HuggingFace model page URL")
    leaderboard_url: Optional[str] = Field(None, description="Direct link to leaderboard entry")
    license: Optional[str] = Field(
        None,
        description="[Open LLM / LMSYS] License type e.g. 'mit', 'apache-2.0', 'Proprietary'"
    )
    context_window: Optional[str] = Field(
        None,
        description="[LMSYS / AA] Context window size e.g. '1M', '128K', '1.1M'"
    )
    released_date: Optional[str] = Field(
        None,
        description="[AA] Model release date e.g. 'April 2026'"
    )

    # ── Open LLM Leaderboard ─────────────────────────────────────
    architecture: Optional[str] = Field(None, description="[Open LLM] Model architecture type")
    model_type: Optional[str] = Field(None, description="[Open LLM] instruct / pretrained / RL-tuned / chat")
    base_model: Optional[str] = Field(None, description="[Open LLM] Parent model this was fine-tuned from")
    params_billions: Optional[float] = Field(None, description="[Open LLM] Parameter count in billions e.g. 77.965")
    precision: Optional[str] = Field(None, description="[Open LLM] Numerical precision e.g. 'float16', 'bfloat16'")
    is_moe: Optional[bool] = Field(None, description="[Open LLM] Is this a Mixture-of-Experts model?")
    flagged: Optional[bool] = Field(None, description="[Open LLM] Whether the submission has been flagged")
    submission_date: Optional[str] = Field(None, description="[Open LLM] Date submitted to leaderboard (YYYY-MM-DD)")
    hf_likes: Optional[int] = Field(None, description="[Open LLM] HuggingFace likes at snapshot time")

    # Open LLM benchmark scores
    average_score: Optional[float] = Field(None, description="[Open LLM] Average across all 6 benchmarks (%)")
    ifeval_score: Optional[float] = Field(None, description="[Open LLM] IFEval — instruction following score")
    bbh_score: Optional[float] = Field(None, description="[Open LLM] BBH — Big Bench Hard reasoning score")
    math_score: Optional[float] = Field(None, description="[Open LLM] MATH Level 5 — hard math score")
    gpqa_score: Optional[float] = Field(None, description="[Open LLM] GPQA — graduate-level science Q&A score")
    musr_score: Optional[float] = Field(None, description="[Open LLM] MuSR — multi-step reasoning score")
    mmlu_pro_score: Optional[float] = Field(None, description="[Open LLM] MMLU-Pro — multitask language understanding score")

    # ── LMSYS Chatbot Arena ───────────────────────────────────────
    elo_score: Optional[float] = Field(None, description="[LMSYS] Elo rating from human preference battles")
    elo_ci: Optional[float] = Field(
        None,
        description="[LMSYS] Elo confidence interval — lower value means more statistically reliable ranking"
    )
    arena_rank: Optional[int] = Field(None, description="[LMSYS] Current rank on Arena leaderboard")
    num_votes: Optional[int] = Field(
        None,
        description="[LMSYS] Total human votes cast — higher count means more reliable Elo score"
    )

    # ── Artificial Analysis ───────────────────────────────────────
    intelligence_score: Optional[float] = Field(None, description="[AA] Overall intelligence index score")
    speed_tps: Optional[float] = Field(None, description="[AA] Output speed in tokens per second")

    # Shared — both LMSYS and Artificial Analysis provide cost fields
    input_cost_per_1m: Optional[float] = Field(
        None,
        description="[LMSYS / AA] Cost per 1M input tokens (USD)"
    )
    output_cost_per_1m: Optional[float] = Field(
        None,
        description="[LMSYS / AA] Cost per 1M output tokens (USD)"
    )

    # ── AI-Generated Fields ───────────────────────────────────────
    model_summary: Optional[str] = Field(None, description="[LLM] What this model is, who made it, and how it's positioned")
    strengths: list[str] = Field(default_factory=list, description="[LLM] What this model is notably strong at based on scores")
    weaknesses: list[str] = Field(default_factory=list, description="[LLM] Where it underperforms compared to peers")
    best_for: Optional[str] = Field(None, description="[LLM] Ideal use case given its score + cost + speed profile")

    # ── Pipeline Meta ────────────────────────────────────────────
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    summarised_at: Optional[datetime] = None
    leaderboard_snapshot_date: Optional[str] = Field(
        None,
        description="Date this data was captured — rankings shift frequently"
    )

    @field_validator("strengths", "weaknesses", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator(
        "params_billions", "hf_likes", "average_score", "ifeval_score", "bbh_score",
        "math_score", "gpqa_score", "musr_score", "mmlu_pro_score", "elo_score",
        "elo_ci", "arena_rank", "num_votes", "intelligence_score", "speed_tps",
        "input_cost_per_1m", "output_cost_per_1m", mode="before"
    )
    @classmethod
    def coerce_numeric(cls, v):
        if isinstance(v, str) and v.strip().upper() in ("N/A", "NA", "NULL", "NONE", ""):
            return None
        return v

    class Config:
        use_enum_values = True


# ══════════════════════════════════════════════════════════════════
#  SECTION 5 — TALKS & EXPLAINERS
#  Sources: Lex Fridman · Yannic Kilcher · Two Minute Papers · AI Explained
# ══════════════════════════════════════════════════════════════════

class TalkVideoLLMFields(BaseModel):
    """Only the fields the LLM generates for YouTube talks."""
    summary:           str       = ""
    key_insights:      list[str] = Field(default_factory=list)
    topics_covered:    list[str] = Field(default_factory=list)
    papers_mentioned:  list[str] = Field(default_factory=list)
    people_mentioned:  list[str] = Field(default_factory=list)
    guest_name:        Optional[str] = None
    guest_affiliation: Optional[str] = None
    difficulty_level:  str       = ""
    relevance_score:   int       = 5
    ai_tags:           list[str] = Field(default_factory=list)

    @field_validator("key_insights", "topics_covered", "papers_mentioned",
                     "people_mentioned", "ai_tags", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []

class TalkVideo(BaseModel):
    """
    Schema for YouTube AI talks and explainer videos.
    All 4 channels confirmed working via YouTube Data API v3.
    Transcripts confirmed available via youtube-transcript-api.
    """

    # ── Identity ─────────────────────────────────────────────────
    id: str = Field(description="YouTube video ID e.g. 'nepKKz-MzFM' — globally unique dedup key")
    channel: TalkChannel
    channel_id: str = Field(
        description=(
            "YouTube channel ID:\n"
            "  Lex Fridman       -> UCSHZKyawb77ixDdsGog4iWA\n"
            "  Yannic Kilcher    -> UCZHmQk67mSJgfCCTn7xBfew\n"
            "  Two Minute Papers -> UCbfYPyITQ-7l4upoX8nvctg\n"
            "  AI Explained      -> UCNJ1Ymd5yFuUPtn21xtRbbw"
        )
    )
    video_url: str = Field(description="Full YouTube URL: https://youtube.com/watch?v={id}")

    # ── Core Content ─────────────────────────────────────────────
    title: str
    description: str = Field(description="YouTube video description (up to 500 chars)")
    published_date: str = Field(description="Video upload date (YYYY-MM-DD)")

    # ── Transcript ───────────────────────────────────────────────
    transcript_available: bool = Field(default=False)
    transcript_word_count: Optional[int] = Field(None, description="Total word count of transcript")
    transcript_segment_count: Optional[int] = Field(None, description="Number of timed segments from youtube-transcript-api")
    transcript_preview: Optional[str] = Field(None, description="First 300 words for quick preview")
    transcript_full: Optional[str] = Field(None, description="Complete transcript — primary LLM input")

    # ── AI-Generated Fields ───────────────────────────────────────
    summary: Optional[str] = Field(None, description="[LLM] 3-5 sentence summary of what this video covers")
    key_insights: list[str] = Field(default_factory=list, description="[LLM] 3-5 most important takeaways")
    topics_covered: list[str] = Field(default_factory=list, description="[LLM] Main topics e.g. ['reasoning', 'RLHF', 'AGI timeline']")
    papers_mentioned: list[str] = Field(default_factory=list, description="[LLM] Research papers referenced in this video")
    people_mentioned: list[str] = Field(default_factory=list, description="[LLM] Notable people mentioned by name")
    guest_name: Optional[str] = Field(None, description="[LLM] Guest name for interview-style videos (mainly Lex Fridman)")
    guest_affiliation: Optional[str] = Field(None, description="[LLM] Guest's company, lab, or university")
    difficulty_level: Optional[str] = Field(None, description="[LLM] 'Beginner' / 'Intermediate' / 'Advanced'")
    relevance_score: Optional[int] = Field(None, ge=1, le=10, description="[LLM] Relevance to current AI developments (1=dated, 10=cutting-edge)")
    ai_tags: list[str] = Field(default_factory=list, description="[LLM] Topic tags e.g. ['LLMs', 'agents', 'interpretability', 'safety']")

    # ── Pipeline Meta ────────────────────────────────────────────
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    summarised_at: Optional[datetime] = None
    is_duplicate: bool = False

    @field_validator("key_insights", "topics_covered", "papers_mentioned", "people_mentioned", "ai_tags", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("transcript_word_count", "transcript_segment_count", "relevance_score", mode="before")
    @classmethod
    def coerce_numeric(cls, v):
        if isinstance(v, str) and v.strip().upper() in ("N/A", "NA", "NULL", "NONE", ""):
            return None
        return v

    class Config:
        use_enum_values = True
