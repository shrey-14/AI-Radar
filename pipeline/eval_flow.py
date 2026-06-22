"""
pipeline/eval_flow.py
=====================
LLM-as-judge evaluation of summary quality for all 5 sections.

Judge: Google Gemini 2.0 Flash (free tier)
  - 1,000,000 TPM — entire 5-section eval completes in ~15 minutes
  - No daily token cap — run as many times as needed
  - Get free API key at: https://aistudio.google.com/apikey

Run standalone:
    python pipeline/eval_flow.py
    python pipeline/eval_flow.py --section news
    python pipeline/eval_flow.py --sample 30
    python pipeline/eval_flow.py --reset
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import json
import time
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

from prefect import flow, task
from openai import OpenAI   

from config import settings
from storage.supabase_client import get_client

log = logging.getLogger(__name__)

# ── Judge client — OpenRouter free tier ─────────────────────────
# Free models (marked :free) have no daily token cap.
# Get free key at: https://openrouter.ai
# No credit card required.
judge_client = OpenAI(
    api_key  = settings.openrouter_api_key,
    base_url = "https://openrouter.ai/api/v1",
)

JUDGE_MODEL = "openai/gpt-oss-120b:free"

# Fallback chain — if primary model is unavailable, next is tried
JUDGE_FALLBACK = "nvidia/nemotron-3-ultra-550b-a55b:free"

SECTION_JUDGE = {
    "papers":     JUDGE_MODEL,
    "news":       JUDGE_MODEL,
    "talks":      JUDGE_MODEL,
    "tools":      JUDGE_MODEL,
    "benchmarks": JUDGE_MODEL,
}

# ── State file tracks last eval timestamp ───────────────────────────────
STATE_FILE  = Path(__file__).parent / ".eval_state.json"
REPORT_FILE = Path(__file__).parent / "eval_report.json"
PASS_THRESHOLD = 3.5


# ══════════════════════════════════════════════════════════════════
#  STATE HELPERS
# ══════════════════════════════════════════════════════════════════

def get_last_eval_time() -> str | None:
    """Returns ISO timestamp of last eval run, or None if first run."""
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        return state.get("last_eval_at")
    return None


def save_eval_time(ts: str) -> None:
    """Persists the current eval timestamp for next run."""
    STATE_FILE.write_text(json.dumps({"last_eval_at": ts}, indent=2))
    log.info(f"Eval state saved: last_eval_at={ts}")


# ══════════════════════════════════════════════════════════════════
#  EVAL PROMPTS
# ══════════════════════════════════════════════════════════════════

PAPER_EVAL_PROMPT = """
You are evaluating whether an AI-generated research paper brief accurately reflects the original abstract.

ORIGINAL ABSTRACT:
{abstract}

AI-GENERATED BRIEF:
- One-line summary: {one_line_summary}
- Problem solved: {problem_solved}
- Approach used: {approach_used}
- Key results: {key_results}
- Real-world impact: {real_world_impact}
- Limitations: {limitations}

Rate each dimension 1-5:
1. FACTUAL_ACCURACY: Are all claims grounded in the abstract? No invented numbers or methods?
2. COMPLETENESS: Are the most important contributions captured?
3. NO_HALLUCINATION: Does the brief avoid adding details not present in the abstract?
4. CLARITY: Is it understandable to a software engineer without ML background?

IMPORTANT JUDGE INSTRUCTIONS:
- The abstract provided may be truncated. If a claim cannot be verified from the
  provided text, score it 3 (uncertain) rather than 1 (hallucination), unless the
  claim clearly contradicts the abstract.
- Only score 1 for claims that are specific, verifiable, and demonstrably absent
  or contradicted by the abstract text you have access to.

Return ONLY valid JSON, no other text:
{{"factual_accuracy": N, "completeness": N, "no_hallucination": N, "clarity": N, "overall": N, "issues": "describe problems or empty string"}}
"""

NEWS_EVAL_PROMPT = """
You are evaluating whether an AI-generated news summary accurately reflects the original article.

ORIGINAL ARTICLE (truncated):
{original_content}

AI-GENERATED SUMMARY:
- Summary: {summary}
- Key points: {key_points}
- Category: {category}
- Companies mentioned: {companies}
- Models mentioned: {models}
- Significance score: {significance_score}/10

Rate each dimension 1-5:
1. FACTUAL_ACCURACY: Are all claims supported by the article content?
2. COMPLETENESS: Are the most newsworthy points captured?
3. NO_HALLUCINATION: Does the summary avoid adding details not in the article?
4. SIGNIFICANCE_CALIBRATION: Is the significance score appropriate for this article?

IMPORTANT JUDGE INSTRUCTIONS:
- If the article content appears truncated, judge completeness on what is present.
- Only penalise companies/models that are not mentioned in the article at all.

Return ONLY valid JSON, no other text:
{{"factual_accuracy": N, "completeness": N, "no_hallucination": N, "significance_calibration": N, "overall": N, "issues": "describe problems or empty string"}}
"""

TOOL_EVAL_PROMPT = """
You are evaluating whether an AI-generated tool description accurately reflects the original tool metadata.

ORIGINAL TOOL DATA:
- Name: {name}
- Description: {description}
- Tags: {tags}
- Language: {language}
- Pipeline task: {pipeline_task}
- Stars/Likes/Downloads: {popularity}

AI-GENERATED FIELDS:
- What it does: {what_it_does}
- Use cases: {use_cases}
- Why trending: {why_trending}
- Significance score: {significance_score}/10

Rate each dimension 1-5:
1. FACTUAL_ACCURACY: Is the description consistent with the original metadata?
2. SPECIFICITY: Are the use cases concrete and specific, not generic?
3. NO_HALLUCINATION: Does the AI avoid inventing capabilities not in the description?
4. USEFULNESS: Would this brief help a developer decide whether to use this tool?

IMPORTANT JUDGE INSTRUCTIONS:
- The significance_score is always AI-generated — it will never appear in the original
  metadata. Do NOT penalise it for not being in the source. Instead evaluate whether
  the score is reasonable given the tool's popularity metrics.
- Why trending is an AI inference field — evaluate whether the reasoning is plausible
  given the available data, not whether it was explicitly stated in the metadata.
- Use cases that are reasonable logical inferences from the tool's name, tags, and
  description should NOT be scored as hallucinations. Only penalise use cases that
  directly contradict the source metadata.

Return ONLY valid JSON, no other text:
{{"factual_accuracy": N, "specificity": N, "no_hallucination": N, "usefulness": N, "overall": N, "issues": "describe problems or empty string"}}
"""

BENCHMARK_EVAL_PROMPT = """
You are evaluating whether an AI-generated model analysis accurately reflects the benchmark scores.

ORIGINAL BENCHMARK DATA:
- Model: {model_name}
- Source: {source}
- Avg Score: {average_score}
- IFEval: {ifeval} | BBH: {bbh} | MATH: {math} | GPQA: {gpqa} | MMLU-Pro: {mmlu}
- Elo: {elo} | Arena Rank: {arena_rank} | Votes: {num_votes}
- Intelligence: {intelligence} | Speed: {speed} t/s
- Input cost: ${input_cost}/1M | Output cost: ${output_cost}/1M

AI-GENERATED ANALYSIS:
- Model summary: {model_summary}
- Strengths: {strengths}
- Weaknesses: {weaknesses}
- Best for: {best_for}

Rate each dimension 1-5:
1. FACTUAL_ACCURACY: Are strength/weakness claims backed by the actual numbers?
2. SCORE_GROUNDING: Does the analysis correctly interpret what the scores mean?
3. NO_HALLUCINATION: Does the AI avoid claiming capabilities not shown in the data?
4. ACTIONABILITY: Does "best for" give a concrete, specific recommendation?

IMPORTANT JUDGE INSTRUCTIONS:
- Parameter counts inferred directly from the model name are NOT hallucinations.
  (e.g. a model named 'qwen-72b' having '72B parameters' is a valid inference)
- An 'Elo confidence interval' cited when no CI data exists IS a hallucination.
- Fields that are N/A in the data — note as unverifiable rather than hallucination.
- Missing benchmark scores (N/A) should not be interpreted as poor performance.

Return ONLY valid JSON, no other text:
{{"factual_accuracy": N, "score_grounding": N, "no_hallucination": N, "actionability": N, "overall": N, "issues": "describe problems or empty string"}}

SCORE INTERPRETATION GUIDE FOR THE JUDGE:
- Intelligence score scale: 0-100. Scores below 30 = weak. 30-50 = moderate.
  50-65 = frontier range. 65+ = top tier.
- Elo score: 1200 = average. 1400+ = strong. 1600+ = elite.
- Any claim of "Elo confidence interval" is ALWAYS a hallucination — this
  field does not exist in the data schema.
- Parameter counts that match the model name (e.g. "72b" → 72B params) are
  valid inferences. Invented counts (e.g. "1.1B" for a model with no size
  info) are hallucinations.
"""

TALK_EVAL_PROMPT = """
You are evaluating whether an AI-generated talk summary accurately reflects the transcript.

TRANSCRIPT:
{transcript_preview}

AI-GENERATED SUMMARY:
- Summary: {summary}
- Key insights: {key_insights}
- Topics covered: {topics}
- Papers mentioned: {papers}
- People mentioned: {people}
- Difficulty: {difficulty}
- Relevance score: {relevance_score}/10

Rate each dimension 1-5:
1. FACTUAL_ACCURACY: Are the insights and claims present in the transcript?
2. INSIGHT_QUALITY: Do the key insights capture genuinely important points?
3. NO_HALLUCINATION: Does the summary avoid adding claims not in the transcript?
4. RELEVANCE_CALIBRATION: Is the relevance score appropriate for an AI/ML audience?

IMPORTANT JUDGE INSTRUCTIONS:
- Only name people as hallucinated if they are clearly absent from the transcript.
- The transcript may be truncated — treat unverifiable claims as uncertain (score 3),
  not hallucinated (score 1), unless clearly contradicted.
- The relevance_score is AI-generated — evaluate whether it is reasonable for an
  AI/ML audience, not whether it appears in the transcript.

Return ONLY valid JSON, no other text:
{{"factual_accuracy": N, "insight_quality": N, "no_hallucination": N, "relevance_calibration": N, "overall": N, "issues": "describe problems or empty string"}}
"""


# ══════════════════════════════════════════════════════════════════
#  SECTION CONFIG
# ══════════════════════════════════════════════════════════════════

SECTION_CONFIG = {
    "papers": {
        "table":   "research_papers",
        "metrics": ["factual_accuracy", "completeness", "no_hallucination", "clarity"],
        "label":   "Research Papers",
    },
    "news": {
        "table":   "ai_news",
        "metrics": ["factual_accuracy", "completeness", "no_hallucination", "significance_calibration"],
        "label":   "AI News",
    },
    "tools": {
        "table":   "ai_tools",
        "metrics": ["factual_accuracy", "specificity", "no_hallucination", "usefulness"],
        "label":   "Tools & Releases",
    },
    "benchmarks": {
        "table":   "benchmark_entries",
        "metrics": ["factual_accuracy", "score_grounding", "no_hallucination", "actionability"],
        "label":   "Benchmarks",
    },
    "talks": {
        "table":   "talk_videos",
        "metrics": ["factual_accuracy", "insight_quality", "no_hallucination", "relevance_calibration"],
        "label":   "Talks & Explainers",
    },
}


# ══════════════════════════════════════════════════════════════════
#  JUDGE CALL
# ══════════════════════════════════════════════════════════════════

def _parse_retry_delay(error_str: str, default: int = 30) -> int:
    """Extract the retry delay from the error message and add a 3s buffer."""
    m = re.search(r'retry in (\d+(?:\.\d+)?)s', error_str, re.IGNORECASE)
    return int(float(m.group(1))) + 3 if m else default


def _call_judge(prompt: str, record_id: str, section: str = "papers") -> dict:
    """
    Call the judge via OpenRouter free tier.
    Primary:  google/gemini-2.0-flash-exp:free
    Fallback: meta-llama/llama-3.3-70b-instruct:free
    Parses retry delay from error messages — no fixed waits.
    """
    def _invoke(model: str) -> dict:
        resp = judge_client.chat.completions.create(
            model       = model,
            messages    = [{"role": "user", "content": prompt}],
            temperature = 0,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        scores = json.loads(raw)
        scores["record_id"]   = record_id
        scores["judge_model"] = model
        return scores

    # ── Try primary model ─────────────────────────────────────────
    try:
        scores = _invoke(JUDGE_MODEL)
        time.sleep(1)
        return scores
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower() or "quota" in err.lower():
            delay = _parse_retry_delay(err)
            log.warning(f"[{JUDGE_MODEL}] Rate limited — waiting {delay}s for {record_id}")
            time.sleep(delay)
            try:
                scores = _invoke(JUDGE_MODEL)
                time.sleep(1)
                return scores
            except Exception:
                pass   # fall through to fallback model

        # ── Try fallback model ────────────────────────────────────
        log.warning(f"[{JUDGE_MODEL}] Failed — trying fallback {JUDGE_FALLBACK} for {record_id}")
        try:
            scores = _invoke(JUDGE_FALLBACK)
            time.sleep(1)
            return scores
        except Exception as e2:
            err2 = str(e2)
            if "429" in err2 or "rate_limit" in err2.lower():
                delay = _parse_retry_delay(err2)
                log.warning(f"[{JUDGE_FALLBACK}] Rate limited — waiting {delay}s")
                time.sleep(delay)
                try:
                    scores = _invoke(JUDGE_FALLBACK)
                    time.sleep(1)
                    return scores
                except Exception as e3:
                    log.warning(f"Both models failed for {record_id}: {e3}")
                    return {"record_id": record_id, "error": str(e3), "judge_model": JUDGE_FALLBACK}
            log.warning(f"[{JUDGE_FALLBACK}] Failed for {record_id}: {e2}")
            return {"record_id": record_id, "error": str(e2), "judge_model": JUDGE_FALLBACK}

# ══════════════════════════════════════════════════════════════════
#  RECORD-LEVEL EVAL FUNCTIONS
# ══════════════════════════════════════════════════════════════════

def _eval_paper(r: dict) -> dict:
    return _call_judge(PAPER_EVAL_PROMPT.format(
        abstract          = r.get("abstract_preview", r.get("abstract", ""))[:4000],
        one_line_summary  = r.get("one_line_summary",  "N/A"),
        problem_solved    = r.get("problem_solved",    "N/A"),
        approach_used     = r.get("approach_used",     "N/A"),
        key_results       = r.get("key_results",       "N/A"),
        real_world_impact = r.get("real_world_impact", "N/A"),
        limitations       = r.get("limitations",       "N/A"),
    ), r["id"], section="papers")


def _eval_news(r: dict) -> dict:
    return _call_judge(NEWS_EVAL_PROMPT.format(
        original_content   = r.get("full_content", r.get("content_preview", ""))[:4000],
        summary            = r.get("summary",    "N/A"),
        key_points         = "\n".join(r.get("key_points", [])),
        category           = r.get("category",   "N/A"),
        companies          = ", ".join(r.get("companies_mentioned", [])),
        models             = ", ".join(r.get("models_mentioned",    [])),
        significance_score = r.get("significance_score", "N/A"),
    ), r["id"], section="news")


def _eval_tool(r: dict) -> dict:
    popularity = (
        f"Stars={r.get('stars')}  Likes={r.get('likes')}  "
        f"Downloads={r.get('downloads')}  Votes={r.get('votes')}  "
        f"TrendingScore={r.get('trending_score')}"
    )
    return _call_judge(TOOL_EVAL_PROMPT.format(
        name               = r.get("name",         "N/A"),
        description        = r.get("description",  "N/A")[:500],
        tags               = ", ".join(r.get("tags", [])),
        language           = r.get("language",      "N/A"),
        pipeline_task      = r.get("pipeline_task", "N/A"),
        popularity         = popularity,
        what_it_does       = r.get("what_it_does",  "N/A"),
        use_cases          = "\n".join(r.get("use_cases", [])),
        why_trending       = r.get("why_trending",  "N/A"),
        significance_score = r.get("significance_score", "N/A"),
    ), r["id"], section="tools")


def _eval_benchmark(r: dict) -> dict:
    return _call_judge(BENCHMARK_EVAL_PROMPT.format(
        model_name    = r.get("model_display_name", "N/A"),
        source        = r.get("source",             "N/A"),
        average_score = r.get("average_score",      "N/A"),
        ifeval        = r.get("ifeval_score",        "N/A"),
        bbh           = r.get("bbh_score",           "N/A"),
        math          = r.get("math_score",          "N/A"),
        gpqa          = r.get("gpqa_score",          "N/A"),
        mmlu          = r.get("mmlu_pro_score",      "N/A"),
        elo           = r.get("elo_score",           "N/A"),
        arena_rank    = r.get("arena_rank",          "N/A"),
        num_votes     = r.get("num_votes",           "N/A"),
        intelligence  = r.get("intelligence_score",  "N/A"),
        speed         = r.get("speed_tps",           "N/A"),
        input_cost    = r.get("input_cost_per_1m",   "N/A"),
        output_cost   = r.get("output_cost_per_1m",  "N/A"),
        model_summary = r.get("model_summary",       "N/A"),
        strengths     = "\n".join(r.get("strengths",  [])),
        weaknesses    = "\n".join(r.get("weaknesses", [])),
        best_for      = r.get("best_for",            "N/A"),
    ), r["id"], section="benchmarks")

def _eval_talk(r: dict) -> dict:
    db      = get_client()
    talk_id = r.get("id")

    transcript_row = (
        db.table("talk_transcripts")
        .select("transcript_full")
        .eq("video_id", talk_id)
        .limit(1)
        .execute()
    )
    transcript = ""
    if transcript_row.data:
        transcript = transcript_row.data[0].get("transcript_full", "") or ""

    # 6000 words is enough for Gemini to verify claims
    words = transcript.split()
    if len(words) > 6000:
        transcript = " ".join(words[:6000]) + "\n[truncated for evaluation]"

    words = transcript.split()
    word_count = len(words)

    if word_count > 6000:
        # Take first half and last half — captures intro + conclusion
        half = 3000
        transcript = (
            " ".join(words[:half])
            + "\n\n[... middle section omitted for length ...]\n\n"
            + " ".join(words[-half:])
        )
    else:
        pass

    if not transcript.strip():
        transcript = r.get("transcript_preview", "")
        if not transcript.strip():
            return {
                "record_id":   r["id"],
                "judge_model": JUDGE_MODEL,
                "error":       "No transcript available — cannot evaluate fairly",
            }

    return _call_judge(TALK_EVAL_PROMPT.format(
        transcript_preview = transcript,
        summary            = r.get("summary",          "N/A"),
        key_insights       = "\n".join(r.get("key_insights",    [])),
        topics             = ", ".join(r.get("topics_covered",  [])),
        papers             = ", ".join(r.get("papers_mentioned",[])),
        people             = ", ".join(r.get("people_mentioned",[])),
        difficulty         = r.get("difficulty_level",  "N/A"),
        relevance_score    = r.get("relevance_score",   "N/A"),
    ), r["id"], section="talks")


EVAL_FN = {
    "papers":     _eval_paper,
    "news":       _eval_news,
    "tools":      _eval_tool,
    "benchmarks": _eval_benchmark,
    "talks":      _eval_talk,
}


# ══════════════════════════════════════════════════════════════════
#  PREFECT TASKS
# ══════════════════════════════════════════════════════════════════

@task(name="fetch-records-for-eval", retries=2)
def fetch_records(section: str, last_eval_at: str | None, sample: int) -> list[dict]:
    """
    First run  (last_eval_at is None) → fetch ALL summarised records.
    Subsequent (last_eval_at has value) → fetch only records summarised
    after the last eval timestamp.
    """
    cfg   = SECTION_CONFIG[section]
    db    = get_client()
    query = (
        db.table(cfg["table"])
        .select("*")
        .not_.is_("summarised_at", "null")
    )

    if last_eval_at:
        query = query.gt("summarised_at", last_eval_at)
        log.info(f"[{section}] Incremental eval — records summarised after {last_eval_at}")
    else:
        log.info(f"[{section}] First run — evaluating ALL summarised records")

    records = (
        query
        .order("summarised_at", desc=True)
        .limit(sample)
        .execute()
    ).data or []

    log.info(f"[{section}] {len(records)} records to evaluate  judge: {JUDGE_MODEL}")
    return records


@task(name="eval-section", retries=1)
def eval_section_task(section: str, records: list[dict]) -> dict:
    """Run LLM-as-judge evaluation for one section, return aggregate results."""
    cfg     = SECTION_CONFIG[section]
    eval_fn = EVAL_FN[section]
    metrics = cfg["metrics"]

    log.info(f"\n[{section}] Starting evaluation  judge: {JUDGE_MODEL}")

    results = []
    for r in records:
        name = (
            r.get("title") or r.get("name") or
            r.get("model_display_name") or r["id"]
        )
        log.info(f"  [{section}] → {name[:65]}")
        scores = eval_fn(r)
        results.append(scores)

        if "error" not in scores:
            metric_str = "  ".join(
                f"{m}={scores.get(m, '?')}" for m in metrics
            )
            log.info(f"    {metric_str}")
            if scores.get("issues"):
                log.warning(f"    Issues: {scores['issues']}")
        else:
            log.warning(f"    Failed: {scores['error']}")

    # ── Aggregate ─────────────────────────────────────────────────
    valid = [r for r in results if "factual_accuracy" in r]
    if not valid:
        log.warning(f"[{section}] No valid scores — all judge calls failed")
        return {"section": section, "evaluated": 0, "rag_ready": False, "judge": JUDGE_MODEL}

    agg       = {m: round(sum(r.get(m, 0) for r in valid) / len(valid), 2) for m in metrics}
    overall   = round(sum(r.get("overall", 0) for r in valid) / len(valid), 2)
    rag_ready = all(v >= PASS_THRESHOLD for v in agg.values())

    log.info(f"\n[{section}] ── AGGREGATE ({len(valid)}/{len(records)} evaluated) ──")
    for m, v in agg.items():
        status = "✓" if v >= PASS_THRESHOLD else "✗ NEEDS IMPROVEMENT"
        log.info(f"  {m:<35} {v:.2f}/5   {status}")
    log.info(f"  {'overall':<35} {overall:.2f}/5")
    log.info(f"  RAG-ready: {'YES ✓' if rag_ready else 'NO ✗ — fix prompts before embedding'}")

    return {
        "section":   section,
        "judge":     JUDGE_MODEL,
        "evaluated": len(valid),
        "failed":    len(results) - len(valid),
        "metrics":   agg,
        "overall":   overall,
        "rag_ready": rag_ready,
    }


# ══════════════════════════════════════════════════════════════════
#  PREFECT FLOW
# ══════════════════════════════════════════════════════════════════

@flow(name="ai-radar-evaluator", description="LLM-as-judge evaluation of all 5 section summaries")
def evaluation_flow(
    section: str | None = None,
    sample:  int        = 30,
) -> None:
    """
    Evaluates summary quality using Gemini 2.0 Flash as judge.
    1M TPM free tier — all 5 sections complete in ~15 minutes in a single run.

    Args:
        section: one of papers/news/tools/benchmarks/talks, or None for all
        sample:  max records to evaluate per section (default 30)
    """
    flow_start   = datetime.now(timezone.utc)
    last_eval_at = get_last_eval_time()

    run_type = (
        "FIRST RUN (all records)"
        if last_eval_at is None
        else f"INCREMENTAL (since {last_eval_at})"
    )
    log.info(f"Evaluation flow started — {run_type}")
    log.info(f"Judge: {JUDGE_MODEL} (Gemini 2.0 Flash — 1M TPM free tier)")

    sections = list(SECTION_CONFIG.keys()) if section is None else [section]
    report   = {
        "run_at":       flow_start.isoformat(),
        "run_type":     run_type,
        "judge":        JUDGE_MODEL,
        "sections":     {},
        "all_rag_ready": False,
    }

    for sec in sections:
        records = fetch_records(sec, last_eval_at, sample)
        if not records:
            log.info(f"[{sec}] No new records to evaluate — skipping")
            continue
        result = eval_section_task(sec, records)
        report["sections"][sec] = result

    # ── Save timestamp so next run is incremental ─────────────────
    save_eval_time(flow_start.isoformat())

    # ── Final readiness summary ───────────────────────────────────
    evaluated = {k: v for k, v in report["sections"].items() if v.get("evaluated", 0) > 0}
    if evaluated:
        report["all_rag_ready"] = all(v.get("rag_ready", False) for v in evaluated.values())

        log.info("\n══ RAG READINESS REPORT ══")
        for sec, res in evaluated.items():
            status = "✓ READY" if res.get("rag_ready") else "✗ NOT READY"
            log.info(f"  {sec:<15} overall={res.get('overall', '?'):.2f}/5   {status}")

        log.info(
            "\n  All sections RAG-ready — proceed to embedding pipeline."
            if report["all_rag_ready"] else
            "\n  Fix failing sections before building RAG."
        )

    # ── Save JSON report ──────────────────────────────────────────
    REPORT_FILE.write_text(json.dumps(report, indent=2))
    log.info(f"Report saved → {REPORT_FILE}")


# ══════════════════════════════════════════════════════════════════
#  STANDALONE ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt= "%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="AI Radar — Summary Evaluator")
    parser.add_argument(
        "--section", default=None,
        choices=["papers", "news", "tools", "benchmarks", "talks"],
        help="Evaluate one section only (default: all)",
    )
    parser.add_argument(
        "--sample", type=int, default=30,
        help="Max records to evaluate per section (default: 30)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete state file to force full re-evaluation of all records",
    )
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("State file deleted — next run will evaluate ALL records")

    evaluation_flow(section=args.section, sample=args.sample)