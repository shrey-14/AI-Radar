"""
tests/test_retrieval.py
========================
Retrieval-only evaluation harness — measures whether the RIGHT document
is being retrieved, completely separate from whether the LLM generates
a good answer from it.

This is Step 1 + Step 7 of the RAG diagnostic process: verify retrieval
correctness BEFORE touching prompts or reranking. If the correct document
never appears in the retrieved set, no amount of prompt engineering will
fix the answer — the LLM never had the information.

Metrics computed per query:
  - Hit@1   : was the correct doc the #1 ranked result?
  - Hit@3   : was the correct doc in the top 3?
  - Hit@5   : was the correct doc in the top 5?
  - MRR     : 1/rank of the correct doc (0 if not found in top K at all)
  - Rank    : exact position the correct doc was found at (or "NOT FOUND")

Also breaks down failures by TYPE so you know exactly what to fix next:
  - ROUTING_MISS   : correct doc's section was never queried by the router
  - RETRIEVAL_MISS : correct section was queried, but hybrid search still
                      didn't surface the doc in the candidate pool
  - RANK_MISS      : doc WAS retrieved, just ranked too low (this is what
                      Step 3 reranking would fix — everything else needs
                      a different fix)

Usage:
    python tests/test_retrieval.py                    # run full test set
    python tests/test_retrieval.py --verbose           # show all ranks
    python tests/test_retrieval.py --section benchmarks
    python tests/test_retrieval.py --skip-router        # bypass router, test raw retrieval only
    python tests/test_retrieval.py --discover tools "image editor"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
from dataclasses import dataclass, field
from typing import Optional

from pipeline.embedding_flow import embed_query
from api.routes.ask import (
    route_query,
    retrieve_hybrid,
    retrieve_with_fallback,
)
from storage.supabase_client import get_client

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")
log = logging.getLogger("test_retrieval")
log.setLevel(logging.INFO)


# ══════════════════════════════════════════════════════════════════
#  TEST CASE — query paired with the EXACT record it should retrieve
# ══════════════════════════════════════════════════════════════════

@dataclass
class RetrievalCase:
    name:            str
    query:           str
    section:         str                       # which table the correct doc lives in
    correct_id:      Optional[str] = None      # filled in automatically if title given
    correct_title_contains: str    = ""        # used to find correct_id by title match
    description:     str           = ""
    category:        str           = ""         # for grouped reporting — see CATEGORY block below


# ══════════════════════════════════════════════════════════════════
# TEST CASES — organized by FAILURE CATEGORY, not by section.
#
# The point of this stress test isn't "does retrieval work" in general —
# you already proved hybrid search itself is excellent (Hit@1=100% once
# routed correctly). The point is to find the SPECIFIC query patterns
# that fool the router, across every section, not just benchmarks.
#
# Categories:
#   EXACT_ID       — query contains a precise model/tool/paper identifier
#                     that should be an unambiguous keyword match
#   AMBIGUOUS_NAME — query contains a name that COULD plausibly belong
#                     to multiple sections (this is what broke Hypernova —
#                     "model" sounds generic enough to route to tools)
#   PHRASING_VARIANT — same underlying entity, different surface form
#                     (hyphens vs spaces, capitalization, abbreviation)
#   CROSS_SECTION  — entity is mentioned in a DIFFERENT section than
#                     where you'd naively expect it (this is the Jio
#                     Call Agent pattern — a product name living inside
#                     a news article, not a tools entry)
#   BROAD_INTENT   — no specific entity at all, pure topical question
#                     (these should route correctly on the FIRST guess —
#                     fallback should never need to trigger here, and if
#                     it does, that itself is worth knowing)
#
# IMPORTANT: correct_title_contains values below are PLACEHOLDERS based
# on common naming patterns. Run --discover for each section before
# trusting results — replace any placeholder that doesn't resolve.
# ══════════════════════════════════════════════════════════════════

RETRIEVAL_CASES = [

    # ═══════════════ PAPERS ═══════════════

    RetrievalCase(
        name="papers_exact_id",
        query="what does the SlimSearcher paper propose?",
        section="papers",
        correct_title_contains="SlimSearcher",
        category="EXACT_ID",
        description="Exact paper method name — should be an unambiguous keyword hit",
    ),
    RetrievalCase(
        name="papers_ambiguous_agent",
        query="what is the ToolSense framework?",
        section="papers",
        correct_title_contains="ToolSense",
        category="AMBIGUOUS_NAME",
        description="'Framework' could route to tools instead of papers — same failure shape as Hypernova",
    ),
    # RetrievalCase(
    #     name="papers_broad_intent",
    #     query="what recent research exists on reducing hallucination in language models?",
    #     section="papers",
    #     correct_title_contains="",   # set after --discover papers "hallucination"
    #     category="BROAD_INTENT",
    #     description="No exact entity — pure topical question, router should get this right on guess 1",
    # ),
    RetrievalCase(
        name="papers_cross_section_mention",
        query="what paper does the SEAOTTER compression method come from?",
        section="papers",
        correct_title_contains="SEAOTTER",
        category="EXACT_ID",
        description="Specific invented-sounding method name — tests whether router defaults away from papers",
    ),

    # ═══════════════ NEWS ═══════════════

    RetrievalCase(
        name="news_exact_company_product",
        query="what is jio call agent?",
        section="news",
        correct_title_contains="Ambani",
        category="CROSS_SECTION",
        description="Known failure — product name lives inside a news article body, not a tools entry",
    ),
    RetrievalCase(
        name="news_ambiguous_model_mention",
        query="what did anthropic say about claude fable 5?",
        section="news",
        correct_title_contains="Claude Fable 5 🚀, Gemini 3.5 Live Translate 📱, scaling test time compute 📈",   # set after --discover news "fable"
        category="AMBIGUOUS_NAME",
        description="Mentions a model name inside a news context — could misroute to benchmarks",
    ),
    RetrievalCase(
        name="news_broad_company_intent",
        query="what has openai announced recently?",
        section="news",
        correct_title_contains="OpenAI to acquire Ona",   # set after --discover news "openai"
        category="BROAD_INTENT",
        description="Generic company news query, no specific entity — should route correctly on guess 1",
    ),
    RetrievalCase(
        name="news_exact_funding_event",
        query="how much funding did anthropic raise in their latest round?",
        section="news",
        correct_title_contains="Ahead of its IPO, Anthropic’s Daniela Amodei shrugs off doubts about AI’s returns",   # set after --discover news "anthropic" "fund"
        category="EXACT_ID",
        description="Specific factual lookup — should resolve to a single news article",
    ),

    # ═══════════════ TOOLS ═══════════════

    RetrievalCase(
        name="tools_exact_spaced",
        query="what is omni image editor and what should it be used for?",
        section="tools",
        correct_title_contains="Omni-Image-Editor",
        category="PHRASING_VARIANT",
        description="Known failure: worked with hyphens, failed with spaces",
    ),
    RetrievalCase(
        name="tools_exact_hyphenated",
        query="what is omni-image-editor and what should it be used for?",
        section="tools",
        correct_title_contains="Omni-Image-Editor",
        category="PHRASING_VARIANT",
        description="Control case — same doc, hyphenated phrasing (known to work)",
    ),
    RetrievalCase(
        name="tools_exact_lowercase",
        query="tell me about omni-image-editor huggingface space",
        section="tools",
        correct_title_contains="Omni-Image-Editor",
        category="PHRASING_VARIANT",
        description="Third phrasing variant — confirms PHRASING_VARIANT isn't a one-off",
    ),
    RetrievalCase(
        name="tools_ambiguous_name",
        query="what does the Agent-Reach repository do?",
        section="tools",
        correct_title_contains="Agent-Reach",
        category="AMBIGUOUS_NAME",
        description="'Agent' could route to papers (agent research) instead of tools",
    ),
    RetrievalCase(
        name="tools_broad_intent",
        query="what tools exist for fine-tuning language models?",
        section="tools",
        correct_title_contains="",   # broad — no single correct_id, see note below
        category="BROAD_INTENT",
        description="No exact entity — topical question, router should handle on guess 1",
    ),

    # ═══════════════ BENCHMARKS ═══════════════

    RetrievalCase(
        name="benchmarks_exact_hypernova",
        query="what is hypernova 60B model?",
        section="benchmarks",
        correct_title_contains="Hypernova 60B",
        category="AMBIGUOUS_NAME",
        description="Original known failure — 'model' sounds generic, router defaults to tools",
    ),
    RetrievalCase(
        name="benchmarks_exact_nemotron",
        query="what is nemotron 3 ultra?",
        section="benchmarks",
        correct_title_contains="Nemotron 3 Ultra",
        category="AMBIGUOUS_NAME",
        description="Second known failure — confirmed fixed by fallback in last test run",
    ),
    RetrievalCase(
        name="benchmarks_exact_claude",
        query="what's the elo score of claude fable 5?",
        section="benchmarks",
        correct_title_contains="claude-fable-5",   # set after --discover benchmarks "claude"
        category="EXACT_ID",
        description="Specific numeric lookup — exact model identifier, explicit benchmark vocabulary",
    ),
    RetrievalCase(
        name="benchmarks_exact_gpt",
        query="how fast is gpt-5.5-high in tokens per second?",
        section="benchmarks",
        correct_title_contains="gpt-5.5-high",   # set after --discover benchmarks "gpt"
        category="EXACT_ID",
        description="Exact model name + explicit metric — should be unambiguous",
    ),
    RetrievalCase(
        name="benchmarks_broad_intent",
        query="which models are good for coding tasks?",
        section="benchmarks",
        correct_title_contains="",   # broad — no single correct_id
        category="BROAD_INTENT",
        description="No exact entity — router should land on benchmarks without needing fallback",
    ),

    # ═══════════════ TALKS ═══════════════

    RetrievalCase(
        name="talks_exact_title",
        query="what does the Jeff Kaplan Lex Fridman podcast episode cover?",
        section="talks",
        correct_title_contains="Jeff Kaplan",
        category="EXACT_ID",
        description="Specific named talk — proper noun heavy, tests talks retrieval precision",
    ),
    # RetrievalCase(
    #     name="talks_channel_specific",
    #     query="what's the latest video from AI Explained about?",
    #     section="talks",
    #     correct_title_contains="",   # set after --discover talks "AI Explained" — may not exist yet
    #     category="CROSS_SECTION",
    #     description="Channel-specific query — known prior failure (sparse talks coverage)",
    # ),
    # RetrievalCase(
    #     name="talks_ambiguous_topic",
    #     query="what talk discusses scaling test-time compute?",
    #     section="talks",
    #     correct_title_contains="",   # set after --discover talks "compute"
    #     category="AMBIGUOUS_NAME",
    #     description="'Scaling' and 'compute' could pull toward papers instead of talks",
    # ),
    RetrievalCase(
        name="talks_broad_intent",
        query="are there any beginner-friendly AI explainer videos?",
        section="talks",
        correct_title_contains="",   # broad — no single correct_id
        category="BROAD_INTENT",
        description="No exact entity — pure intent, router should handle without fallback",
    ),

    # ═══════════════ CROSS-SECTION CONFUSION (the hardest category) ═══════════════
    # These deliberately use vocabulary that's ambiguous BETWEEN TWO specific
    # sections (not just "could route broadly") — the real adversarial test.

    RetrievalCase(
        name="confusion_paper_vs_tool",
        query="what is the SkillSpector project about?",
        section="tools",
        correct_title_contains="SkillSpector",
        category="AMBIGUOUS_NAME",
        description="'Project' + technical name — could plausibly be a paper OR a tool",
    ),
    RetrievalCase(
        name="confusion_news_vs_benchmark",
        query="what's new with claude opus 4.8?",
        section="news",
        correct_title_contains="claude-opus-4-8-thinking",   # set after --discover news "opus"
        category="AMBIGUOUS_NAME",
        description="Model name in a news-intent query — could misroute to benchmarks entirely",
    ),

    # ── Add more cases below as you discover NEW production failures ──
    # RetrievalCase(
    #     name="...", query="...", section="...",
    #     correct_title_contains="...", category="...", description="...",
    # ),
]


SECTION_TABLE = {
    "papers":     "research_papers",
    "news":       "ai_news",
    "tools":      "ai_tools",
    "benchmarks": "benchmark_entries",
    "talks":      "talk_videos",
}

SECTION_TITLE_COL = {
    "papers":     "title",
    "news":       "title",
    "tools":      "name",
    "benchmarks": "model_display_name",
    "talks":      "title",
}


# ══════════════════════════════════════════════════════════════════
#  RESOLVE correct_id FROM correct_title_contains (run once at start)
# ══════════════════════════════════════════════════════════════════

def resolve_correct_ids(cases: list[RetrievalCase]) -> list[RetrievalCase]:
    """Look up the real record ID for each test case by matching title substring."""
    db = get_client()

    for case in cases:
        if case.correct_id:
            continue   # already set manually

        table     = SECTION_TABLE[case.section]
        title_col = SECTION_TITLE_COL[case.section]

        rows = (
            db.table(table)
            .select(f"id, {title_col}")
            .ilike(title_col, f"%{case.correct_title_contains}%")
            .limit(1)
            .execute()
        ).data

        if rows:
            case.correct_id = rows[0]["id"]
        else:
            log.warning(
                f"[{case.name}] Could not resolve correct_id"
                f"in '{table}' matching title containing '{case.correct_title_contains}'. "
                f"This record may not exist"
            )

    return cases


# ══════════════════════════════════════════════════════════════════
#  RETRIEVAL TEST RUNNER
# ══════════════════════════════════════════════════════════════════

@dataclass
class RetrievalResult:
    name:              str
    query:             str
    expected_section:  str
    correct_id:        Optional[str]
    routed_sections:   list[str]
    routing_correct:   bool          # was the expected section even queried?
    retrieved_ids:     list[str]     # ids retrieved IN the expected section, ranked
    rank:              Optional[int] # 1-indexed position, None if not found
    hit_at_1:          bool
    hit_at_3:          bool
    hit_at_5:          bool
    mrr:               float
    failure_type:      Optional[str] # ROUTING_MISS | RETRIEVAL_MISS | RANK_MISS | None
    error:             Optional[str] = None
    category:          str = ""      # EXACT_ID | AMBIGUOUS_NAME | PHRASING_VARIANT |
                                       # CROSS_SECTION | BROAD_INTENT — set after the fact
                                       # from the originating RetrievalCase, see run_all() below


def run_retrieval_case(
    case:         RetrievalCase,
    top_k:        int  = 10,
    skip_router:  bool = False,
    use_fallback: bool = False,
) -> RetrievalResult:
    """
    Runs ONLY the retrieval pipeline (router + hybrid search) — no LLM
    generation at all. This isolates retrieval quality completely from
    answer quality.

    use_fallback=True routes through retrieve_with_fallback() (Architecture 2)
    instead of raw retrieve_hybrid() on the router's guessed section only.
    This tests the END-TO-END production behavior, including self-correction
    when the router's initial guess was weak. A case that fails without
    --with-fallback but passes with it confirms the fallback layer is
    catching that specific routing failure in production.
    """
    if not case.correct_id:
        return RetrievalResult(
            name=case.name, query=case.query, expected_section=case.section,
            correct_id=None, routed_sections=[], routing_correct=False,
            retrieved_ids=[], rank=None, hit_at_1=False, hit_at_3=False,
            hit_at_5=False, mrr=0.0, failure_type="UNRESOLVED_GROUND_TRUTH",
            error="correct_id could not be resolved — check correct_title_contains",
        )

    try:
        # ── Routing ──────────────────────────────────────────────
        if skip_router:
            sections, rewritten = [case.section], case.query
        else:
            sections, rewritten = route_query(case.query)

        query_vector = embed_query(rewritten)

        if use_fallback:
            # Architecture 2: let the fallback layer self-correct if the
            # router's guess was weak. `sections` gets reassigned to
            # whatever the fallback layer actually ended up using.
            hits, sections = retrieve_with_fallback(
                query_text=case.query,
                query_vector=query_vector,
                router_sections=sections,
                top_k=top_k,
            )
            # With fallback, only check routing_correct AFTER correction —
            # the whole point is the router's original guess no longer
            # has to be right on its own.
            routing_correct = case.section in sections
            if not routing_correct:
                return RetrievalResult(
                    name=case.name, query=case.query, expected_section=case.section,
                    correct_id=case.correct_id, routed_sections=sections,
                    routing_correct=False, retrieved_ids=[], rank=None,
                    hit_at_1=False, hit_at_3=False, hit_at_5=False, mrr=0.0,
                    failure_type="ROUTING_MISS",
                )
            # hits may include records from sections other than case.section
            # (fallback searches broadly) — filter to the expected section
            # for a fair rank comparison
            hits = [h for h in hits if h.get("_section") == case.section]

        else:
            # Original behavior: raw retrieve_hybrid on the router's
            # guessed section only, no self-correction. Use this mode
            # (the default) to isolate pure hybrid search quality from
            # the fallback layer's effect.
            routing_correct = case.section in sections
            if not routing_correct:
                return RetrievalResult(
                    name=case.name, query=case.query, expected_section=case.section,
                    correct_id=case.correct_id, routed_sections=sections,
                    routing_correct=False, retrieved_ids=[], rank=None,
                    hit_at_1=False, hit_at_3=False, hit_at_5=False, mrr=0.0,
                    failure_type="ROUTING_MISS",
                )
            hits = retrieve_hybrid(
                query_text=case.query,
                query_vector=query_vector,
                sections=[case.section],
                top_k=top_k,
            )

        retrieved_ids = [h.get("id") for h in hits]

        rank = None
        if case.correct_id in retrieved_ids:
            rank = retrieved_ids.index(case.correct_id) + 1

        hit_at_1 = rank == 1
        hit_at_3 = rank is not None and rank <= 3
        hit_at_5 = rank is not None and rank <= 5
        mrr      = (1.0 / rank) if rank else 0.0

        failure_type = None
        if rank is None:
            failure_type = "RETRIEVAL_MISS"
        elif rank > 3:
            failure_type = "RANK_MISS"

        return RetrievalResult(
            name=case.name, query=case.query, expected_section=case.section,
            correct_id=case.correct_id, routed_sections=sections,
            routing_correct=True, retrieved_ids=retrieved_ids, rank=rank,
            hit_at_1=hit_at_1, hit_at_3=hit_at_3, hit_at_5=hit_at_5, mrr=mrr,
            failure_type=failure_type,
        )

    except Exception as e:
        return RetrievalResult(
            name=case.name, query=case.query, expected_section=case.section,
            correct_id=case.correct_id, routed_sections=[], routing_correct=False,
            retrieved_ids=[], rank=None, hit_at_1=False, hit_at_3=False,
            hit_at_5=False, mrr=0.0, failure_type="ERROR", error=str(e),
        )


def print_result(r: RetrievalResult) -> None:
    if r.failure_type is None:
        status = "✓ PASS"
    elif r.failure_type == "ROUTING_MISS":
        status = "✗ ROUTING MISS"
    elif r.failure_type == "RETRIEVAL_MISS":
        status = "✗ RETRIEVAL MISS"
    elif r.failure_type == "RANK_MISS":
        status = "△ RANK MISS"
    else:
        status = f"✗ {r.failure_type}"

    print(f"\n{'─'*64}")
    print(f"  {status}  [{r.name}]")
    print(f"  Query    : {r.query}")
    print(f"  Expected : section='{r.expected_section}'  id={r.correct_id}")
    print(f"  Routed to: {r.routed_sections}  "
          f"({'✓ included expected section' if r.routing_correct else '✗ MISSED expected section'})")

    if r.error:
        print(f"  ERROR    : {r.error}")
        return

    if not r.routing_correct:
        print(f"  → Retrieval never ran — router didn't query '{r.expected_section}'")
        return

    if r.rank:
        print(f"  Rank     : #{r.rank} of {len(r.retrieved_ids)} retrieved  "
              f"(Hit@1={r.hit_at_1}  Hit@3={r.hit_at_3}  Hit@5={r.hit_at_5}  MRR={r.mrr:.3f})")
    else:
        print(f"  Rank     : NOT FOUND in top {len(r.retrieved_ids)} results")
        print(f"  Retrieved: {r.retrieved_ids[:5]}{'...' if len(r.retrieved_ids) > 5 else ''}")


def print_summary(results: list[RetrievalResult]) -> None:
    total = len(results)
    if total == 0:
        print("No test cases to evaluate.")
        return

    valid = [r for r in results if r.error is None and r.correct_id]
    n     = len(valid)

    routing_misses   = sum(1 for r in valid if r.failure_type == "ROUTING_MISS")
    retrieval_misses = sum(1 for r in valid if r.failure_type == "RETRIEVAL_MISS")
    rank_misses      = sum(1 for r in valid if r.failure_type == "RANK_MISS")
    passes           = sum(1 for r in valid if r.failure_type is None)
    errors           = total - n

    hit1 = sum(1 for r in valid if r.hit_at_1) / n if n else 0
    hit3 = sum(1 for r in valid if r.hit_at_3) / n if n else 0
    hit5 = sum(1 for r in valid if r.hit_at_5) / n if n else 0
    mrr  = sum(r.mrr for r in valid) / n if n else 0

    print(f"\n{'═'*64}")
    print(f"  RETRIEVAL EVALUATION SUMMARY  ({n} valid test cases)")
    print(f"{'═'*64}")
    print(f"  Hit@1 (top result is correct)     : {hit1:.1%}")
    print(f"  Hit@3 (correct doc in top 3)      : {hit3:.1%}")
    print(f"  Hit@5 (correct doc in top 5)      : {hit5:.1%}")
    print(f"  MRR (mean reciprocal rank)        : {mrr:.3f}")
    print(f"{'─'*64}")
    print(f"  Clean passes (rank 1-3)           : {passes}/{n}")
    print(f"  ROUTING_MISS  (wrong section)     : {routing_misses}/{n}")
    print(f"  RETRIEVAL_MISS (right section,")
    print(f"                  doc not found)    : {retrieval_misses}/{n}")
    print(f"  RANK_MISS (found but rank > 3)    : {rank_misses}/{n}")
    if errors:
        print(f"  Unresolved/errors                 : {errors}")
    print(f"{'═'*64}")

    # ── Breakdown by failure category — the actual point of this stress test ──
    by_category: dict[str, list[RetrievalResult]] = {}
    for r in valid:
        cat = r.category or "UNCATEGORIZED"
        by_category.setdefault(cat, []).append(r)

    if by_category:
        print(f"\n  BREAKDOWN BY CATEGORY")
        print(f"  {'─'*60}")
        print(f"  {'Category':<18} {'Cases':<7} {'Hit@1':<8} {'Hit@3':<8} {'Fallback used':<14}")
        for cat in sorted(by_category):
            rs       = by_category[cat]
            cat_n    = len(rs)
            cat_hit1 = sum(1 for r in rs if r.hit_at_1) / cat_n
            cat_hit3 = sum(1 for r in rs if r.hit_at_3) / cat_n
            # "fallback used" = router's raw guess didn't already include the
            # expected section, but the FINAL routed_sections (post-fallback)
            # does — i.e. self-correction actually fired for this case
            fallback_fired = sum(
                1 for r in rs
                if r.routing_correct and len(r.routed_sections) > 2
                # heuristic: a corrected/fanned-out result usually ends up
                # with more sections than a clean single/double guess —
                # treat >2 as a signal fallback likely expanded the search
            )
            print(f"  {cat:<18} {cat_n:<7} {cat_hit1:<8.0%} {cat_hit3:<8.0%} {fallback_fired:<14}")
        print(f"  {'─'*60}")
        print(f"  Note: 'Fallback used' is a heuristic based on routed section count,")
        print(f"  not a precise flag. For exact confirmation, check the per-case")
        print(f"  'Routed to' line above against what the router alone would guess.")

    print("\n  WHAT TO FIX, BASED ON THE DOMINANT FAILURE TYPE:")
    if routing_misses > retrieval_misses and routing_misses > rank_misses:
        print("  -> Most failures are ROUTING_MISS. Fix the router prompt/logic")
        print("     BEFORE touching reranking or embeddings - retrieval never")
        print("     even ran for these queries.")
    elif retrieval_misses > rank_misses:
        print("  -> Most failures are RETRIEVAL_MISS. The router is fine, but")
        print("     hybrid search itself isn't surfacing the doc at all. This")
        print("     points to embedding/keyword text quality (Step 4/5), not")
        print("     reranking (Step 3) - reranking only reorders candidates")
        print("     that were ALREADY retrieved.")
    elif rank_misses > 0:
        print("  -> Most failures are RANK_MISS. The correct doc IS being")
        print("     retrieved, just ranked too low. THIS is exactly what a")
        print("     reranker (Step 3) is designed to fix - proceed with that.")
    else:
        print("  -> No dominant failure pattern, or all passing. Good baseline.")


# ══════════════════════════════════════════════════════════════════
#  DISCOVERY MODE — helps you find real titles to build test cases from
# ══════════════════════════════════════════════════════════════════

def discover_records(section: str, search_term: str, limit: int = 10) -> None:
    """
    Utility to find real record IDs/titles matching a search term, so you
    can build accurate RetrievalCase entries with correct_title_contains.
    """
    db        = get_client()
    table     = SECTION_TABLE[section]
    title_col = SECTION_TITLE_COL[section]

    rows = (
        db.table(table)
        .select(f"id, {title_col}")
        .ilike(title_col, f"%{search_term}%")
        .limit(limit)
        .execute()
    ).data or []

    print(f"\nFound {len(rows)} rag_ready records in '{table}' matching '{search_term}':")
    for r in rows:
        print(f"  id={r['id']}  {title_col}='{r[title_col]}'")


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Radar — Retrieval-Only Evaluation")
    parser.add_argument("--section", default=None,
                         choices=["papers", "news", "tools", "benchmarks", "talks"],
                         help="Run test cases for one section only")
    parser.add_argument("--top-k", type=int, default=10,
                         help="How many results to retrieve per query (default: 10)")
    parser.add_argument("--skip-router", action="store_true",
                         help="Bypass the router, force-query only the expected section "
                              "(isolates pure retrieval quality from routing quality)")
    parser.add_argument("--with-fallback", action="store_true",
                         help="Route through retrieve_with_fallback() (Architecture 2) "
                              "instead of raw retrieve_hybrid() on the router's guess only. "
                              "Use this to confirm the fallback layer self-corrects known "
                              "routing failures (e.g. Hypernova/Nemotron). Mutually exclusive "
                              "with --skip-router in practice — fallback only matters when "
                              "the router actually runs.")
    parser.add_argument("--discover", nargs=2, metavar=("SECTION", "SEARCH_TERM"),
                         help="Find real record titles/IDs to build test cases. "
                              "Example: --discover tools 'image editor'")
    args = parser.parse_args()

    if args.discover:
        discover_records(args.discover[0], args.discover[1])
        sys.exit(0)

    cases = RETRIEVAL_CASES
    if args.section:
        cases = [c for c in cases if c.section == args.section]

    print(f"Resolving ground-truth IDs for {len(cases)} test cases...")
    cases = resolve_correct_ids(cases)

    unresolved = [c for c in cases if not c.correct_id]
    if unresolved:
        print(f"\nWARNING: {len(unresolved)} test case(s) could not resolve a ground-truth ID:")
        for c in unresolved:
            print(f"  - {c.name}: searched for title containing '{c.correct_title_contains}'")
        print("  These will show as UNRESOLVED_GROUND_TRUTH below. Fix the search term")
        print("  or use --discover to find the correct title substring.\n")

    print(f"Running retrieval-only evaluation on {len(cases)} cases...")
    print(f"  top_k={args.top_k}  skip_router={args.skip_router}  with_fallback={args.with_fallback}\n")

    results = []
    for case in cases:
        r = run_retrieval_case(
            case,
            top_k=args.top_k,
            skip_router=args.skip_router,
            use_fallback=args.with_fallback,
        )
        r.category = case.category   # tag result with its failure category for grouped reporting
        results.append(r)
        print_result(r)

    print_summary(results)