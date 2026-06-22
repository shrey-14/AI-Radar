# AI Radar

Automated AI intelligence pipeline — scrapes research papers, news, tools,
benchmarks, and talks, summarises them with an LLM, and stores structured
results in Supabase. Runs daily at 07:00 via Prefect.

## Sections

| Section    | Sources |
|------------|---------|
| Papers     | arXiv · HuggingFace Daily Papers · OpenReview |
| News       | Anthropic · OpenAI · DeepMind · Meta AI · TLDR AI · TechCrunch · Import AI |
| Tools      | GitHub Trending · HF Hub · HF Spaces · Product Hunt |
| Benchmarks | Open LLM Leaderboard · LMSYS Arena · Artificial Analysis |
| Talks      | Lex Fridman · Yannic Kilcher · Two Minute Papers · AI Explained |

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Fill in your API keys in .env

# 3. Create Supabase tables
# Paste database/supabase_tables.sql into Supabase → SQL Editor → Run

# 4. Validate config
python main.py --validate

# 5. Run pipeline once
python main.py

# 6. Register daily 07:00 schedule
python main.py --deploy
prefect worker start --pool default-agent-pool
```

## Project Structure

```
AIRadar/
├── main.py                        Entry point
├── config.py                      All settings (loaded from .env)
├── schemas.py                     Pydantic models for all 5 sections
├── prompts.py                     LLM prompts + Groq model assignments
├── .env.example                   Environment variable template
├── requirements.txt
│
├── pipeline/
│   ├── flow.py                    Prefect flow — orchestrates all stages
│   ├── scraper.py                 Dispatcher → scrapers/*
│   ├── dedup.py                   Deduplication logic
│   ├── summariser.py              Wrapper around prompts.py
│   └── storage.py                 Supabase upsert helpers
│
├── scrapers/
│   ├── papers/                    arxiv · hf_papers · openreview
│   ├── news/                      rss (6 feeds) · meta_ai (Crawl4AI)
│   ├── tools/                     github_trending · hf_hub · hf_spaces · product_hunt
│   ├── benchmarks/                open_llm · lmsys · artificial_analysis
│   └── talks/                     youtube (4 channels + transcripts)
│
├── storage/
│   └── supabase_client.py         Singleton Supabase client
│
├── database/
│   └── supabase_tables.sql        Table definitions + indexes (run once)
│
├── notebooks/
│   └── source_validation.ipynb    Working scraper code per source
│
└── tests/
    ├── test_schemas.py
    ├── test_dedup.py
    └── test_prompts.py
```

## Stack

| Layer       | Tool |
|-------------|------|
| Scheduling  | Prefect |
| LLM         | Groq (Llama 3.3 70B · Llama 3.1 8B) |
| Scraping    | Crawl4AI · feedparser · arxiv-py · HF Hub · YouTube Data API v3 |
| Storage     | Supabase (PostgreSQL) |
| Validation  | Pydantic v2 |

## Implementing Scrapers

Each file in `scrapers/` has a `scrape()` stub and a reference to the exact
notebook cell with working code. Open `notebooks/source_validation.ipynb`,
find the referenced cell, and paste the implementation into the stub.
