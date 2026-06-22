"""
tests/test_rag.py
=================
Standalone test script for the AI Radar RAG pipeline.
Tests retrieval quality, answer grounding, and routing accuracy
across all 5 sections with 20 diverse sample queries.

Runs WITHOUT needing FastAPI to be running — calls the pipeline
functions directly.

Usage:
    python tests/test_rag.py                      # run all tests
    python tests/test_rag.py --section papers     # papers only
    python tests/test_rag.py --query "your query" # single custom query
    python tests/test_rag.py --verbose            # show full context blocks
    python tests/test_rag.py --threshold 0.2      # lower similarity cutoff

Prerequisites:
    1. Run: python pipeline/embedding_flow.py     (embed all records first)
    2. Run SQL in Supabase: sql/rag_match_functions.sql
    3. Set JINA_API_KEY, GROQ_API_KEY in .env
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import argparse
import logging
from dataclasses import dataclass, field
from typing import Optional

from pipeline.embedding_flow import embed_query
from api.routes.ask import (
    route_query,
    retrieve,
    assemble_context,
    generate_answer,
)

logging.basicConfig(
    level=logging.WARNING,       # suppress Prefect/Groq noise during tests
    format="%(levelname)s  %(message)s",
)
log = logging.getLogger("test_rag")
log.setLevel(logging.INFO)


# ══════════════════════════════════════════════════════════════════
#  TEST CASE DEFINITIONS
# ══════════════════════════════════════════════════════════════════

@dataclass
class TestCase:
    name:             str
    query:            str
    expected_sections: list[str]          # sections we expect the router to pick
    check_keywords:   list[str] = field(default_factory=list)   # words we expect in the answer
    min_hits:         int       = 1       # minimum records we expect to retrieve
    description:      str      = ""


TEST_CASES = [

    # ── Papers ────────────────────────────────────────────────────
    TestCase(
        name             = "papers_reasoning",
        query            = "What recent papers are about improving reasoning in large language models?",
        expected_sections= ["papers"],
        check_keywords   = [],           # keyword check is optional; leave empty if uncertain
        min_hits         = 1,
        description      = "Core papers query — should retrieve reasoning/LLM papers",
    ),
    TestCase(
        name             = "papers_efficient_inference",
        query            = "What approaches exist for making transformer inference faster and cheaper?",
        expected_sections= ["papers", "tools"],
        min_hits         = 1,
        description      = "Efficiency query — could span papers and tools",
    ),
    TestCase(
        name             = "papers_agents",
        query            = "Which papers discuss AI agents that can use tools or browse the web?",
        expected_sections= ["papers"],
        min_hits         = 1,
        description      = "Agents papers — tests ai_tags retrieval",
    ),
    TestCase(
        name             = "papers_safety",
        query            = "What has been published recently about AI safety, alignment, or hallucination reduction?",
        expected_sections= ["papers"],
        min_hits         = 1,
        description      = "Safety/alignment papers query",
    ),

    # ── News ──────────────────────────────────────────────────────
    TestCase(
        name             = "news_openai",
        query            = "What has OpenAI announced recently?",
        expected_sections= ["news"],
        min_hits         = 1,
        description      = "Company-specific news — tests companies_mentioned retrieval",
    ),
    TestCase(
        name             = "news_funding",
        query            = "Which AI startups raised funding recently and how much?",
        expected_sections= ["news"],
        min_hits         = 1,
        description      = "Funding news — significance calibration test",
    ),
    TestCase(
        name             = "news_model_releases",
        query            = "What new AI models have been released in the past week?",
        expected_sections= ["news", "tools"],
        min_hits         = 1,
        description      = "Model release news — should hit news + tools",
    ),
    TestCase(
        name             = "news_regulation",
        query            = "What is happening with AI regulation and government policy?",
        expected_sections= ["news"],
        min_hits         = 1,
        description      = "Regulation news query",
    ),
    TestCase(
        name             = "news_anthropic",
        query            = "What has Anthropic been doing lately?",
        expected_sections= ["news"],
        min_hits         = 1,
        description      = "Anthropic-specific news — tests company mention retrieval",
    ),

    # ── Tools ─────────────────────────────────────────────────────
    TestCase(
        name             = "tools_finetuning",
        query            = "What are the best open-source tools for fine-tuning language models?",
        expected_sections= ["tools"],
        min_hits         = 1,
        description      = "Fine-tuning tools query — tests pipeline_task retrieval",
    ),
    TestCase(
        name             = "tools_rag",
        query            = "Which tools or libraries are useful for building RAG systems?",
        expected_sections= ["tools"],
        min_hits         = 1,
        description      = "RAG tools query — meta but relevant for this project",
    ),
    TestCase(
        name             = "tools_image_generation",
        query            = "What image generation models are trending on Hugging Face right now?",
        expected_sections= ["tools"],
        min_hits         = 1,
        description      = "Image generation tools — tests popularity + pipeline_task",
    ),
    TestCase(
        name             = "tools_python_library",
        query            = "Are there any new Python libraries for working with LLM APIs?",
        expected_sections= ["tools"],
        min_hits         = 1,
        description      = "Python library tools query",
    ),

    # ── Benchmarks ────────────────────────────────────────────────
    TestCase(
        name             = "benchmarks_cheapest",
        query            = "Which LLM has the lowest cost per token while still performing well?",
        expected_sections= ["benchmarks"],
        min_hits         = 1,
        description      = "Cost comparison query — tests input_cost_per_1m retrieval",
    ),
    TestCase(
        name             = "benchmarks_fastest",
        query            = "What is the fastest model available in terms of tokens per second?",
        expected_sections= ["benchmarks"],
        min_hits         = 1,
        description      = "Speed comparison — tests speed_tps retrieval",
    ),
    TestCase(
        name             = "benchmarks_coding",
        query            = "Which model is best for coding tasks based on benchmark scores?",
        expected_sections= ["benchmarks"],
        min_hits         = 1,
        description      = "Coding benchmark query — tests best_for and MATH/BBH scores",
    ),
    TestCase(
        name             = "benchmarks_compare_specific",
        query            = "How does DeepSeek compare to Llama in reasoning benchmarks?",
        expected_sections= ["benchmarks"],
        min_hits         = 1,
        description      = "Specific model comparison — tests model name retrieval",
    ),

    # ── Talks ─────────────────────────────────────────────────────
    TestCase(
        name             = "talks_scaling",
        query            = "Are there any recent talks about scaling laws or compute in AI?",
        expected_sections= ["talks"],
        min_hits         = 0,    # 0 = ok if no results (talks section has fewer records)
        description      = "Scaling talks query",
    ),
    TestCase(
        name             = "talks_beginner",
        query            = "What introductory AI talks or explainers are available for beginners?",
        expected_sections= ["talks"],
        min_hits         = 0,
        description      = "Beginner content query — tests difficulty_level retrieval",
    ),

    # ── Cross-section ─────────────────────────────────────────────
    TestCase(
        name             = "cross_multimodal",
        query            = "What is the current state of multimodal AI — papers, tools, and news?",
        expected_sections= ["papers", "news", "tools"],
        min_hits         = 2,
        description      = "Broad multi-section query — tests router's multi-section routing",
    ),

]


# ══════════════════════════════════════════════════════════════════
#  TEST RUNNER
# ══════════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    name:             str
    passed:           bool
    query:            str
    routed_sections:  list[str]
    expected_sections: list[str]
    routing_correct:  bool
    hits_count:       int
    min_hits:         int
    hits_ok:          bool
    keywords_found:   list[str]
    keywords_missing: list[str]
    answer_preview:   str
    latency_ms:       int
    error:            Optional[str] = None


def run_test(
    tc:        TestCase,
    top_k:     int   = 5,
    threshold: float = 0.2,
    verbose:   bool  = False,
) -> TestResult:
    """Run a single test case end-to-end."""
    t0 = time.perf_counter()

    try:
        # Step 1 — Route
        routed_sections, rewritten = route_query(tc.query)

        # Step 2 — Embed query
        query_vector = embed_query(rewritten)

        # Step 3 — Retrieve
        hits = retrieve(query_vector, routed_sections, top_k=top_k, threshold=threshold)

        # Step 4 — Assemble context
        context, sources = assemble_context(hits)

        if verbose and hits:
            print(f"\n  CONTEXT ({len(hits)} records):")
            print("  " + context[:800].replace("\n", "\n  ") + ("..." if len(context) > 800 else ""))

        # Step 5 — Generate
        answer = generate_answer(tc.query, context) if hits else "No results found."

        latency_ms = int((time.perf_counter() - t0) * 1000)

        # ── Evaluate ──────────────────────────────────────────────
        # Routing: at least one expected section was picked
        routing_correct = any(s in routed_sections for s in tc.expected_sections)

        # Hits: minimum records retrieved
        hits_ok = len(hits) >= tc.min_hits

        # Keywords: expected words appear in the answer
        answer_lower = answer.lower()
        keywords_found   = [k for k in tc.check_keywords if k.lower() in answer_lower]
        keywords_missing = [k for k in tc.check_keywords if k.lower() not in answer_lower]

        passed = routing_correct and hits_ok and not keywords_missing

        return TestResult(
            name             = tc.name,
            passed           = passed,
            query            = tc.query,
            routed_sections  = routed_sections,
            expected_sections= tc.expected_sections,
            routing_correct  = routing_correct,
            hits_count       = len(hits),
            min_hits         = tc.min_hits,
            hits_ok          = hits_ok,
            keywords_found   = keywords_found,
            keywords_missing = keywords_missing,
            answer_preview   = answer,
            latency_ms       = latency_ms,
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log.error(f"Test '{tc.name}' raised exception: {e}")
        return TestResult(
            name             = tc.name,
            passed           = False,
            query            = tc.query,
            routed_sections  = [],
            expected_sections= tc.expected_sections,
            routing_correct  = False,
            hits_count       = 0,
            min_hits         = tc.min_hits,
            hits_ok          = False,
            keywords_found   = [],
            keywords_missing = tc.check_keywords,
            answer_preview   = "",
            latency_ms       = latency_ms,
            error            = str(e),
        )


def print_result(r: TestResult, verbose: bool = False) -> None:
    status = "✓ PASS" if r.passed else "✗ FAIL"
    print(f"\n{'─'*60}")
    print(f"  {status}  [{r.name}]")
    print(f"  Query    : {r.query[:80]}")
    print(f"  Routed   : {r.routed_sections}  (expected: {r.expected_sections})  "
          f"{'✓' if r.routing_correct else '✗'}")
    print(f"  Hits     : {r.hits_count}  (min: {r.min_hits})  {'✓' if r.hits_ok else '✗'}")
    print(f"  Latency  : {r.latency_ms}ms")

    if r.error:
        print(f"  ERROR    : {r.error}")
    else:
        print(f"  Answer   : {r.answer_preview}")

    if r.keywords_missing:
        print(f"  Missing  : {r.keywords_missing}")


def print_summary(results: list[TestResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total  = len(results)
    avg_ms = int(sum(r.latency_ms for r in results) / total) if total else 0

    routing_ok = sum(1 for r in results if r.routing_correct)
    hits_ok    = sum(1 for r in results if r.hits_ok)
    errors     = sum(1 for r in results if r.error)

    print(f"\n{'═'*60}")
    print(f"  RAG TEST SUMMARY")
    print(f"{'═'*60}")
    print(f"  Overall    : {passed}/{total} passed  {'✓' if passed == total else '✗'}")
    print(f"  Routing    : {routing_ok}/{total} correct")
    print(f"  Retrieval  : {hits_ok}/{total} met min_hits")
    print(f"  Errors     : {errors}")
    print(f"  Avg latency: {avg_ms}ms")
    print(f"{'═'*60}")

    if passed < total:
        print("\n  FAILURES:")
        for r in results:
            if not r.passed:
                issues = []
                if not r.routing_correct:
                    issues.append(f"routing (got {r.routed_sections})")
                if not r.hits_ok:
                    issues.append(f"hits ({r.hits_count} < {r.min_hits})")
                if r.keywords_missing:
                    issues.append(f"keywords {r.keywords_missing}")
                if r.error:
                    issues.append(f"error: {r.error}")
                print(f"  ✗ {r.name}: {', '.join(issues)}")


# ══════════════════════════════════════════════════════════════════
#  SINGLE QUERY MODE
# ══════════════════════════════════════════════════════════════════

def run_single_query(
    query:     str,
    top_k:     int   = 5,
    threshold: float = 0.2,
    verbose:   bool  = False,
) -> None:
    """Run a single custom query and print the full result."""
    print(f"\n{'═'*60}")
    print(f"  QUERY: {query}")
    print(f"{'═'*60}")

    t0 = time.perf_counter()

    sections, rewritten = route_query(query)
    print(f"  Router   : {sections}")
    print(f"  Rewritten: {rewritten}")

    query_vector = embed_query(rewritten)
    hits = retrieve(query_vector, sections, top_k=top_k, threshold=threshold)
    print(f"  Hits     : {len(hits)} records retrieved")

    if hits:
        print(f"\n  Top results:")
        for i, h in enumerate(hits[:3], 1):
            title = h.get("title") or h.get("name") or h.get("model_display_name") or "?"
            sim   = h.get("similarity", 0)
            sec   = h.get("_section", "?")
            print(f"    {i}. [{sec}] {title[:60]} (similarity: {sim:.3f})")

    context, sources = assemble_context(hits)

    if verbose:
        print(f"\n  FULL CONTEXT:\n  {'─'*50}")
        print("  " + context.replace("\n", "\n  "))
        print(f"  {'─'*50}")

    answer = generate_answer(query, context) if hits else "No relevant results found."
    latency = int((time.perf_counter() - t0) * 1000)

    print(f"\n  ANSWER ({latency}ms):")
    print(f"  {'─'*50}")
    print(f"  {answer.replace(chr(10), chr(10)+'  ')}")
    print(f"  {'─'*50}")

    if sources:
        print(f"\n  SOURCES:")
        for s in sources:
            print(f"    [{s['section'].upper()} {s['index']}] {s['title'][:55]}"
                  f"  (sim: {s['similarity']:.3f})")


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Radar — RAG Pipeline Tests")
    parser.add_argument(
        "--section", default=None,
        choices=["papers", "news", "tools", "benchmarks", "talks"],
        help="Run tests for one section only",
    )
    parser.add_argument(
        "--query", default=None,
        help="Run a single custom query instead of the test suite",
    )
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Number of records to retrieve per section (default: 5)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.2,
        help="Minimum similarity score to include a result (default: 0.2)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print full context blocks for each test",
    )
    args = parser.parse_args()

    # ── Single query mode ─────────────────────────────────────────
    if args.query:
        run_single_query(
            args.query,
            top_k=args.top_k,
            threshold=args.threshold,
            verbose=args.verbose,
        )
        sys.exit(0)

    # ── Test suite mode ───────────────────────────────────────────
    test_cases = TEST_CASES
    if args.section:
        # Filter to tests that include the specified section
        test_cases = [
            tc for tc in TEST_CASES
            if args.section in tc.expected_sections or tc.name.startswith(args.section)
        ]
        print(f"Running {len(test_cases)} tests for section: {args.section}")

    print(f"\nRunning {len(test_cases)} RAG tests...")
    print(f"  top_k={args.top_k}  threshold={args.threshold}  verbose={args.verbose}")
    print(f"  embedding model  : jina-embeddings-v3")
    print(f"  router model     : llama-3.1-8b-instant (Groq)")
    print(f"  generator model  : openai/gpt-oss-120b (Groq)")

    results = []
    for tc in test_cases:
        print(f"\n  Running: {tc.name}...", end="", flush=True)
        result = run_test(tc, top_k=args.top_k, threshold=args.threshold, verbose=args.verbose)
        results.append(result)
        status = "✓" if result.passed else "✗"
        print(f" {status} ({result.latency_ms}ms, {result.hits_count} hits)")

        if args.verbose:
            print_result(result, verbose=True)

    if not args.verbose:
        # Print all results concisely
        for r in results:
            print_result(r)

    print_summary(results)