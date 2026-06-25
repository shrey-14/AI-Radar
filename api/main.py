"""
api/main.py — AI Radar
========================
FastAPI application entry point.

Run locally:
    uvicorn api.main:app --reload --port 8000

Interactive docs:
    http://localhost:8000/docs      ← Swagger UI
    http://localhost:8000/redoc     ← ReDoc
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import papers, news, tools, benchmarks, talks, digest, search, status

from api.routes.ask import router as ask_router

# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Radar API",
    description=(
        "Daily AI intelligence — research papers, news, tools, "
        "benchmarks, and talks. Summarised with LLMs and served fresh every morning."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────
# Allow all origins during development.
# Lock down to your deployed frontend URL in production.

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://ai-radar.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────

app.include_router(papers.router)
app.include_router(news.router)
app.include_router(tools.router)
app.include_router(benchmarks.router)
app.include_router(talks.router)
app.include_router(digest.router)
app.include_router(search.router)
app.include_router(status.router)

app.include_router(ask_router, prefix="/api")

# ── Health check ─────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "service": "AI Radar API",
        "status":  "running",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}

