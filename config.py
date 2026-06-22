from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    All settings are loaded from environment variables or .env file.
    Required fields (no default) will raise a clear error on startup
    if not set — fail fast rather than crashing mid-pipeline.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,   # GROQ_API_KEY and groq_api_key both work
        extra="ignore",         # ignore unknown env vars silently
    )

    # ── LLM — Groq ───────────────────────────────────────────────
    groq_api_key: str = Field(
        description="Required. Get at console.groq.com"
    )

    jina_api_key: str = Field(
        description="Required. Get at jina.ai"
    )    

    groq_model_heavy: str = Field(
        default="llama-3.3-70b-versatile",
        description="Model for long content: news articles, talk transcripts"
    )
    groq_model_light: str = Field(
        default="llama-3.1-8b-instant",
        description="Model for short content: abstracts, tool descriptions, benchmark scores"
    )
    llm_temperature: float = Field(
        default=0.1,
        ge=0.0, le=1.0,
        description="Keep low for consistent structured JSON output"
    )

    # ── LLM — OpenRouter ─────────────────────────────────────────
    openrouter_api_key: str = Field(
        description="Required. Get at openrouter.ai"
    )

    # ── Storage — Supabase ───────────────────────────────────────
    supabase_url: str = Field(
        description="Required. Your Supabase project URL"
    )
    supabase_service_key: str = Field(
        description="Required. Use service_role key for pipeline (not anon key)"
    )

    # ── Source API Keys ──────────────────────────────────────────
    github_token: str = Field(
        description="Required for Tools section. github.com/settings/tokens"
    )
    youtube_api_key: str = Field(
        description="Required for Talks section. console.cloud.google.com"
    )
    product_hunt_token: str = Field(
        description="Required for Tools section. producthunt.com/v2/oauth/applications"
    )
    semantic_scholar_key: str = Field(
        default="",
        description="Optional. Increases rate limit from 100/5min to 1/sec"
    )

    alert_email_from:     Optional[str] = None
    alert_email_password: Optional[str] = None
    alert_email_to:       Optional[str] = None

    # ── Section Feature Flags ────────────────────────────────────
    enable_papers: bool = Field(default=True)
    enable_news: bool = Field(default=True)
    enable_tools: bool = Field(default=True)
    enable_benchmarks: bool = Field(default=True)
    enable_talks: bool = Field(default=True)

    # ── Per-Run Volume Limits ────────────────────────────────────
    max_papers_per_run: int = Field(default=20, ge=1, le=200)
    max_news_per_run: int = Field(default=30, ge=1, le=200)
    max_tools_per_run: int = Field(default=20, ge=1, le=200)
    max_benchmarks_per_run: int = Field(default=30, ge=1, le=200)
    max_talks_per_run: int = Field(default=8, ge=1, le=50)

    # ── Scheduling ───────────────────────────────────────────────
    pipeline_morning_run: str = Field(
        default="07:00",
        description="Fixed daily run time in HH:MM (24h local time)"
    )

    # ── Deduplication ────────────────────────────────────────────
    news_dedup_threshold: float = Field(
        default=0.80, ge=0.0, le=1.0,
        description="Title similarity threshold for aggregator dedup. 0.80 = 80% match"
    )

    # ── Logging ──────────────────────────────────────────────────
    log_level: str = Field(default="INFO")

    # ── Validators ───────────────────────────────────────────────

    @field_validator("pipeline_morning_run")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Ensure morning run time is in HH:MM format."""
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError(f"PIPELINE_MORNING_RUN must be HH:MM format, got: {v}")
        hh, mm = parts
        if not hh.isdigit() or not mm.isdigit():
            raise ValueError(f"PIPELINE_MORNING_RUN must be HH:MM format, got: {v}")
        if not (0 <= int(hh) <= 23) or not (0 <= int(mm) <= 59):
            raise ValueError(f"Invalid time in PIPELINE_MORNING_RUN: {v}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}, got: {v}")
        return upper

    # ── Convenience Properties ────────────────────────────────────

    @property
    def enabled_sections(self) -> list[str]:
        """Returns list of currently enabled section names."""
        return [
            section for section, enabled in {
                "papers":     self.enable_papers,
                "news":       self.enable_news,
                "tools":      self.enable_tools,
                "benchmarks": self.enable_benchmarks,
                "talks":      self.enable_talks,
            }.items()
            if enabled
        ]

    @property
    def has_semantic_scholar_key(self) -> bool:
        return bool(self.semantic_scholar_key.strip())

    @property
    def max_per_run(self) -> dict[str, int]:
        """Returns per-section limits as a dict for dispatcher use."""
        return {
            "papers":     self.max_papers_per_run,
            "news":       self.max_news_per_run,
            "tools":      self.max_tools_per_run,
            "benchmarks": self.max_benchmarks_per_run,
            "talks":      self.max_talks_per_run,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    Using lru_cache means .env is read once at startup,
    not on every import.

    Use this everywhere:
        from config import get_settings
        settings = get_settings()
    """
    return Settings()


# Module-level singleton for convenience
# Import directly: from config import settings
settings = get_settings()


# ── Startup Validation ────────────────────────────────────────────

def validate_on_startup() -> None:
    """
    Call this once at the start of main.py to catch missing config
    early rather than failing mid-pipeline run.
    Prints a summary of what's enabled.
    """
    import logging
    log = logging.getLogger(__name__)

    log.info("Epoch pipeline config loaded")
    log.info(f"Enabled sections : {settings.enabled_sections}")
    log.info(f"Run interval     : {settings.pipeline_morning_run} daily")
    log.info(f"LLM heavy model  : {settings.groq_model_heavy}")
    log.info(f"LLM light model  : {settings.groq_model_light}")
    log.info(f"Semantic Scholar : {'authenticated' if settings.has_semantic_scholar_key else 'unauthenticated (rate limited)'}")

    # Warn if a section is enabled but its required key is missing
    if settings.enable_tools and not settings.github_token:
        log.warning("ENABLE_TOOLS=true but GITHUB_TOKEN is not set — GitHub scraping will fail")
    if settings.enable_tools and not settings.product_hunt_token:
        log.warning("ENABLE_TOOLS=true but PRODUCT_HUNT_TOKEN is not set — Product Hunt will be skipped")
    if settings.enable_talks and not settings.youtube_api_key:
        log.warning("ENABLE_TALKS=true but YOUTUBE_API_KEY is not set — Talks section will fail")


if __name__ == "__main__":
    # Quick test — run this file directly to verify .env is loaded correctly
    # python config.py
    import logging
    logging.basicConfig(level="INFO", format="%(levelname)s  %(message)s")
    validate_on_startup()
    print("\nAll settings loaded successfully.")
    print(f"Enabled sections : {settings.enabled_sections}")
    print(f"Max items/run    : {settings.max_per_run}")