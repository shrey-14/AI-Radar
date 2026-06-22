-- ================================================================
-- AI Radar — Supabase Table Definitions
-- ================================================================
-- Run this entire file in: Supabase → SQL Editor → New Query → Run
-- Creates all 6 tables, indexes, and the pending_summarisation view
-- ================================================================


-- ================================================================
-- SECTION 1 — RESEARCH PAPERS
-- Sources: arXiv · HF Daily Papers · OpenReview
-- Dedup:   arxiv_id (partial unique index, allows NULL)
-- ================================================================

CREATE TABLE IF NOT EXISTS research_papers (

    -- Identity
    id                  text        PRIMARY KEY,
    source              text        NOT NULL,
    arxiv_id            text,
    openreview_note_id  text,
    source_url          text        NOT NULL,
    pdf_url             text,

    -- Core Content
    title               text        NOT NULL,
    abstract            text        NOT NULL,
    abstract_preview    text        NOT NULL,

    -- Authors
    authors             text[]      NOT NULL DEFAULT '{}',
    first_author        text,
    author_count        integer     NOT NULL DEFAULT 0,

    -- Classification
    primary_category    text,
    all_categories      text[]      NOT NULL DEFAULT '{}',

    -- Dates
    published_date      date,

    -- Venue
    venue               text,

    -- HF Daily Papers only
    upvotes             integer,
    num_comments        integer,
    featured_date       date,
    thumbnail           text,

    -- OpenReview only
    decision            text,
    keywords            text[]      NOT NULL DEFAULT '{}',

    -- AI-Generated Fields (NULL until summariser runs)
    one_line_summary    text,
    problem_solved      text,
    approach_used       text,
    key_results         text,
    real_world_impact   text,
    limitations         text,
    relevance_score     integer     CHECK (relevance_score BETWEEN 1 AND 10),
    ai_tags             text[]      NOT NULL DEFAULT '{}',

    -- Pipeline Meta
    fetched_at          timestamptz NOT NULL DEFAULT now(),
    summarised_at       timestamptz,
    is_duplicate        boolean     NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX IF NOT EXISTS research_papers_arxiv_id_unique
    ON research_papers (arxiv_id)
    WHERE arxiv_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS research_papers_published_date_idx  ON research_papers (published_date DESC);
CREATE INDEX IF NOT EXISTS research_papers_source_idx          ON research_papers (source);
CREATE INDEX IF NOT EXISTS research_papers_relevance_score_idx ON research_papers (relevance_score DESC);
CREATE INDEX IF NOT EXISTS research_papers_fetched_at_idx      ON research_papers (fetched_at DESC);
CREATE INDEX IF NOT EXISTS research_papers_summarised_at_idx   ON research_papers (summarised_at)
    WHERE summarised_at IS NULL;


-- ================================================================
-- SECTION 2 — AI NEWS
-- Sources: Anthropic · OpenAI · DeepMind · Meta AI
--          TLDR AI · TechCrunch AI · Import AI
-- Dedup:   id = SHA256(url)
-- ================================================================

CREATE TABLE IF NOT EXISTS ai_news (

    -- Identity
    id                  text        PRIMARY KEY,
    source              text        NOT NULL,
    source_display_name text        NOT NULL,
    url                 text        NOT NULL UNIQUE,

    -- Core Content
    title               text        NOT NULL,
    full_content        text        NOT NULL,
    content_preview     text        NOT NULL,
    word_count          integer     NOT NULL DEFAULT 0,

    -- Dates
    published_date      date,

    -- AI-Generated Fields
    summary             text,
    key_points          text[]      NOT NULL DEFAULT '{}',
    category            text,
    companies_mentioned text[]      NOT NULL DEFAULT '{}',
    models_mentioned    text[]      NOT NULL DEFAULT '{}',
    significance_score  integer     CHECK (significance_score BETWEEN 1 AND 10),
    ai_tags             text[]      NOT NULL DEFAULT '{}',

    -- Pipeline Meta
    fetched_at          timestamptz NOT NULL DEFAULT now(),
    summarised_at       timestamptz,
    is_duplicate        boolean     NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS ai_news_published_date_idx     ON ai_news (published_date DESC);
CREATE INDEX IF NOT EXISTS ai_news_source_idx             ON ai_news (source);
CREATE INDEX IF NOT EXISTS ai_news_significance_score_idx ON ai_news (significance_score DESC);
CREATE INDEX IF NOT EXISTS ai_news_category_idx           ON ai_news (category);
CREATE INDEX IF NOT EXISTS ai_news_fetched_at_idx         ON ai_news (fetched_at DESC);
CREATE INDEX IF NOT EXISTS ai_news_summarised_at_idx      ON ai_news (summarised_at)
    WHERE summarised_at IS NULL;


-- ================================================================
-- SECTION 3 — AI TOOLS & GITHUB
-- Sources: GitHub Trending · HF Hub · HF Spaces · Product Hunt
-- Dedup:   url (unique)
-- ================================================================

CREATE TABLE IF NOT EXISTS ai_tools (

    -- Identity
    id              text        PRIMARY KEY,
    source          text        NOT NULL,
    url             text        NOT NULL UNIQUE,

    -- Core Content
    name            text        NOT NULL,
    description     text        NOT NULL,

    -- Popularity signals (source-specific — others will be NULL)
    stars           integer,
    votes           integer,
    likes           integer,
    downloads       integer,
    trending_score  real,

    -- Classification
    tags            text[]      NOT NULL DEFAULT '{}',
    language        text,
    pipeline_task   text,
    sdk             text,
    license         text,

    -- Author / Owner
    author          text,

    -- HF Hub specific
    base_model      text,
    last_modified   date,
    framework       text,

    -- Product Hunt specific
    website_url     text,
    launch_date     date,

    -- AI-Generated Fields
    what_it_does        text,
    use_cases           text[]  NOT NULL DEFAULT '{}',
    why_trending        text,
    significance_score  integer CHECK (significance_score BETWEEN 1 AND 10),
    ai_tags             text[]  NOT NULL DEFAULT '{}',

    -- Pipeline Meta
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    summarised_at   timestamptz,
    is_duplicate    boolean     NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS ai_tools_source_idx             ON ai_tools (source);
CREATE INDEX IF NOT EXISTS ai_tools_significance_score_idx ON ai_tools (significance_score DESC);
CREATE INDEX IF NOT EXISTS ai_tools_fetched_at_idx         ON ai_tools (fetched_at DESC);
CREATE INDEX IF NOT EXISTS ai_tools_stars_idx              ON ai_tools (stars DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ai_tools_trending_score_idx     ON ai_tools (trending_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ai_tools_summarised_at_idx      ON ai_tools (summarised_at)
    WHERE summarised_at IS NULL;


-- ================================================================
-- SECTION 4 — BENCHMARKS & LEADERBOARDS
-- Sources: Open LLM Leaderboard · LMSYS Arena · Artificial Analysis
-- Dedup:   (source, model_id) composite — same model kept per source
-- ================================================================

CREATE TABLE IF NOT EXISTS benchmark_entries (

    -- Identity
    id                      text        PRIMARY KEY,
    source                  text        NOT NULL,
    model_id                text        NOT NULL,
    model_display_name      text        NOT NULL,
    organisation            text,
    hf_url                  text,
    leaderboard_url         text,
    license                 text,
    context_window          text,
    released_date           text,

    -- Open LLM Leaderboard fields
    architecture            text,
    model_type              text,
    base_model              text,
    params_billions         real,
    precision               text,
    is_moe                  boolean,
    flagged                 boolean,
    submission_date         date,
    hf_likes                integer,

    -- Open LLM benchmark scores
    average_score           real,
    ifeval_score            real,
    bbh_score               real,
    math_score              real,
    gpqa_score              real,
    musr_score              real,
    mmlu_pro_score          real,

    -- LMSYS Chatbot Arena fields
    elo_score               real,
    elo_ci                  real,
    arena_rank              integer,
    num_votes               integer,

    -- Artificial Analysis fields
    intelligence_score      real,
    speed_tps               real,

    -- Shared cost fields (LMSYS + Artificial Analysis)
    input_cost_per_1m       real,
    output_cost_per_1m      real,

    -- AI-Generated Fields
    model_summary           text,
    strengths               text[]  NOT NULL DEFAULT '{}',
    weaknesses              text[]  NOT NULL DEFAULT '{}',
    best_for                text,

    -- Pipeline Meta
    fetched_at              timestamptz NOT NULL DEFAULT now(),
    summarised_at           timestamptz,
    leaderboard_snapshot_date date
);

CREATE UNIQUE INDEX IF NOT EXISTS benchmark_entries_source_model_unique
    ON benchmark_entries (source, model_id);

CREATE INDEX IF NOT EXISTS benchmark_entries_source_idx        ON benchmark_entries (source);
CREATE INDEX IF NOT EXISTS benchmark_entries_model_id_idx      ON benchmark_entries (model_id);
CREATE INDEX IF NOT EXISTS benchmark_entries_average_score_idx ON benchmark_entries (average_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS benchmark_entries_arena_rank_idx    ON benchmark_entries (arena_rank ASC NULLS LAST);
CREATE INDEX IF NOT EXISTS benchmark_entries_intelligence_idx  ON benchmark_entries (intelligence_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS benchmark_entries_snapshot_date_idx ON benchmark_entries (leaderboard_snapshot_date DESC);
CREATE INDEX IF NOT EXISTS benchmark_entries_summarised_at_idx ON benchmark_entries (summarised_at)
    WHERE summarised_at IS NULL;


-- ================================================================
-- SECTION 5 — TALKS & EXPLAINERS
-- Sources: Lex Fridman · Yannic Kilcher · Two Minute Papers · AI Explained
-- Dedup:   id = YouTube video_id (globally unique)
-- Note:    transcript_full is stored separately to keep talk_videos lean
-- ================================================================

CREATE TABLE IF NOT EXISTS talk_videos (

    -- Identity
    id                      text        PRIMARY KEY,
    channel                 text        NOT NULL,
    channel_id              text        NOT NULL,
    video_url               text        NOT NULL UNIQUE,

    -- Core Content
    title                   text        NOT NULL,
    description             text        NOT NULL,
    published_date          date        NOT NULL,

    -- Transcript metadata
    transcript_available    boolean     NOT NULL DEFAULT false,
    transcript_word_count   integer,
    transcript_segment_count integer,
    transcript_preview      text,

    -- AI-Generated Fields
    summary                 text,
    key_insights            text[]  NOT NULL DEFAULT '{}',
    topics_covered          text[]  NOT NULL DEFAULT '{}',
    papers_mentioned        text[]  NOT NULL DEFAULT '{}',
    people_mentioned        text[]  NOT NULL DEFAULT '{}',
    guest_name              text,
    guest_affiliation       text,
    difficulty_level        text    CHECK (difficulty_level IN ('Beginner', 'Intermediate', 'Advanced')),
    relevance_score         integer CHECK (relevance_score BETWEEN 1 AND 10),
    ai_tags                 text[]  NOT NULL DEFAULT '{}',

    -- Pipeline Meta
    fetched_at              timestamptz NOT NULL DEFAULT now(),
    summarised_at           timestamptz,
    is_duplicate            boolean     NOT NULL DEFAULT false
);

-- Separate table for full transcripts (50–350KB each)
-- Join only when needed: summariser agent or detail view
CREATE TABLE IF NOT EXISTS talk_transcripts (
    video_id        text        PRIMARY KEY REFERENCES talk_videos(id) ON DELETE CASCADE,
    transcript_full text        NOT NULL,
    stored_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS talk_videos_channel_idx         ON talk_videos (channel);
CREATE INDEX IF NOT EXISTS talk_videos_published_date_idx  ON talk_videos (published_date DESC);
CREATE INDEX IF NOT EXISTS talk_videos_relevance_score_idx ON talk_videos (relevance_score DESC);
CREATE INDEX IF NOT EXISTS talk_videos_fetched_at_idx      ON talk_videos (fetched_at DESC);
CREATE INDEX IF NOT EXISTS talk_videos_summarised_at_idx   ON talk_videos (summarised_at)
    WHERE summarised_at IS NULL;


-- ================================================================
-- HELPER VIEW — items not yet summarised across all sections
-- The pipeline's summariser agent polls this to find pending work
-- ================================================================

CREATE OR REPLACE VIEW pending_summarisation AS
    SELECT id, 'papers'     AS section, fetched_at FROM research_papers  WHERE summarised_at IS NULL
    UNION ALL
    SELECT id, 'news'       AS section, fetched_at FROM ai_news          WHERE summarised_at IS NULL
    UNION ALL
    SELECT id, 'tools'      AS section, fetched_at FROM ai_tools         WHERE summarised_at IS NULL
    UNION ALL
    SELECT id, 'benchmarks' AS section, fetched_at FROM benchmark_entries WHERE summarised_at IS NULL
    UNION ALL
    SELECT id, 'talks'      AS section, fetched_at FROM talk_videos      WHERE summarised_at IS NULL
    ORDER BY fetched_at ASC;

ALTER TABLE talk_videos ADD COLUMN IF NOT EXISTS duration_seconds integer;