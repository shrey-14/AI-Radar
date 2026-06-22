import os
import re
import json
from dotenv import load_dotenv
from typing import TypeVar, Type
from pydantic import BaseModel
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pipeline.post_processor import clean_paper_fields, clean_benchmark_fields, clean_news_fields


from storage.supabase_client import get_client

from schemas import (
    ResearchPaper,      ResearchPaperLLMFields,
    AINewsArticle,      AINewsArticleLLMFields,
    AITool,             AIToolLLMFields,
    BenchmarkEntry,     BenchmarkEntryLLMFields,
    TalkVideo,          TalkVideoLLMFields,
)

T = TypeVar("T", bound=BaseModel)

load_dotenv()  # Load environment variables from .env file

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Two model clients — heavy and light
llm_heavy = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.1,          # low = consistent, structured output
    api_key=GROQ_API_KEY,
)

llm_light = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.1,
    api_key=GROQ_API_KEY,
)

def clean_article_content(raw: str) -> str:
    """
    Strip navigation, images, links, and other Crawl4AI noise from scraped
    news content before sending to the LLM. Works for all news sources:
    OpenAI, Anthropic, DeepMind, Meta AI, TechCrunch, TLDR AI, Import AI.
    """
    # 1. Remove ALL image markdown — ![alt](url) and ![]()
    #    These account for the majority of wasted tokens (partner logos, etc.)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', raw)

    # 2. Unwrap link markdown — [text](url) → text
    #    Converts [Research](/research/index/) → "Research"
    text = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', text)

    # 3. Strip leftover bare URLs
    text = re.sub(r'https?://\S+', '', text)

    # 4. Strip noise phrases injected by Crawl4AI or site JS
    text = re.sub(r'\(opens in a new window\)', '', text)
    text = re.sub(r'Skip to main content', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Loading…', '', text)
    text = re.sub(r'Table of contents', '', text, flags=re.IGNORECASE)

    # 5. Filter lines — keep headings + substantive lines only
    cleaned: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            cleaned.append('')
            continue

        # Always keep headings (# Title, ## Section, etc.)
        if s.startswith('#'):
            cleaned.append(s)
            continue

        # For list items (* or -), keep only those with real content (30+ chars)
        # Drops: "* Research", "* Products", "* Log in" (nav items)
        # Keeps: "* The data analytics plugin helps analysts and business teams..."
        if re.match(r'^[-*•·]\s+', s):
            content_after_bullet = re.sub(r'^[-*•·]\s+', '', s).strip()
            if len(content_after_bullet) >= 30:
                cleaned.append(s)
            continue

        # For regular text lines, drop anything under 30 chars
        # Drops: "Research", "Products", "2026", "Author", "OpenAI", "Log in"
        # Keeps all actual article sentences
        if len(s) < 30:
            continue

        cleaned.append(s)

    # 6. Collapse runs of blank lines to a single blank
    text = '\n'.join(cleaned)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()

def _esc(text: str) -> str:
    """Escape curly braces in dynamic content so LangChain doesn't misread them as template variables."""
    return (text or "").replace("{", "{{").replace("}", "}}")

# ══════════════════════════════════════════════════════════════════
#  SHARED UTILITY — run prompt and parse into Pydantic schema
# ══════════════════════════════════════════════════════════════════

def _repair_json(raw: str) -> dict:
    """
    Fix common LLM JSON formatting issue: unquoted or multiline string values.
    Extracts key-value pairs from malformed JSON output.
    """
    # Step 1: Join consecutive non-key lines into the previous key's value
    lines   = raw.split('\n')
    cleaned = []
    buffer  = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Line starts a new JSON key
        if stripped.startswith('"') and '":' in stripped:
            if buffer:
                cleaned.append(buffer.rstrip(','))
            buffer = stripped
        else:
            # Continuation of previous value — append to buffer
            buffer = buffer.rstrip(',') + " " + stripped if buffer else stripped

    if buffer:
        cleaned.append(buffer.rstrip(','))

    # Step 2: Ensure every value is quoted
    result = {}
    for line in cleaned:
        m = re.match(r'"(\w+)"\s*:\s*(.*)', line.strip().rstrip(','))
        if not m:
            continue
        key   = m.group(1)
        value = m.group(2).strip()

        # Remove surrounding quotes if already present
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        # Try to parse as JSON (handles numbers, booleans, lists)
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value

    return result


def run_prompt(
    llm: ChatGroq,
    system_prompt: str,
    user_prompt: str,
    schema: Type[T],
    partial_data: dict,
    llm_schema: Type[BaseModel] | None = None,
) -> T:
    """
    Runs the prompt through Groq LLM with structured output,
    then merges AI-generated fields into the existing partial_data dict
    and returns a validated Pydantic model instance.

    Args:
        llm:           ChatGroq model instance (heavy or light)
        system_prompt: Instruction prompt for the LLM
        user_prompt:   Content to analyse
        schema:        Full Pydantic model class for the final return value
        partial_data:  Already-scraped raw fields to merge with LLM output
        llm_schema:    Smaller schema with only LLM-generated fields.
                       If provided, the LLM only fills these fields —
                       prevents it from hallucinating identity/pipeline fields.
                       Defaults to schema (full schema) when not provided.

    Returns:
        Validated Pydantic model instance with all fields populated
    """
    target_schema = llm_schema if llm_schema is not None else schema

    # In json_mode the schema is not auto-injected — append field list to system prompt
    # import json as _json
    # fields_hint = _json.dumps(
    #     {k: (v.description if v.description else str(v.annotation))
    #      for k, v in target_schema.model_fields.items()},
    #     indent=2,
    # )
    # # Escape { } so LangChain doesn't treat them as template variables
    # fields_hint_escaped = fields_hint.replace("{", "{{").replace("}", "}}")
    # full_system = f"{system_prompt}\n\nReturn a JSON object with exactly these fields:\n{fields_hint_escaped}"

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human",  user_prompt),
    ])
    # json_mode bypasses Groq's strict function-call validation (which rejects
    # valid JSON from smaller models like llama-3.1-8b-instant)
    chain = prompt_template | llm.with_structured_output(
        target_schema, method="json_mode")

    # LLM fills its fields → skip empty strings → partial_data wins on conflicts
    ai_fields = chain.invoke({})
    return ai_fields


# ══════════════════════════════════════════════════════════════════
#  SECTION 1 — RESEARCH PAPERS
#  Model: llama-3.1-8b-instant
#  Input: title + abstract (~200-300 words)
#  Fills: one_line_summary, problem_solved, approach_used,
#         key_results, real_world_impact, limitations,
#         relevance_score, ai_tags
# ══════════════════════════════════════════════════════════════════

# PAPER_SYSTEM_PROMPT = """
# You are an expert AI research analyst. Your job is to read an AI research paper's
# title and abstract, then extract structured insights for a non-expert audience
# who wants to stay updated on AI developments.

# Rules:
# - Be concise and specific. No vague language like "the authors propose a novel approach".
# - Write as if explaining to a smart software engineer, not an academic.
# - If a field cannot be determined from the abstract, return null for that field.
# - Return ONLY valid JSON matching the schema. No preamble, no markdown.
# - List fields (authors, ai_tags, all_categories, keywords) MUST always be JSON arrays — even for a single item. Use ["Name"] never "Name".

# Relevance score guide (1-10):
#   1-3  → Niche or highly specialised, unlikely to affect mainstream AI
#   4-6  → Interesting contribution, relevant to specific subfields
#   7-8  → Significant advance, will likely be widely cited or adopted
#   9-10 → Landmark paper — changes how the field thinks about a problem

# AI tags should be short lowercase phrases from this set where applicable:
# reasoning, agents, RAG, multimodal, vision, NLP, fine-tuning, RLHF,
# alignment, safety, interpretability, diffusion, robotics, benchmarking,
# efficient inference, long context, code generation, tool use, embodied AI
# """.strip()


PAPER_SYSTEM_PROMPT = """
You are summarising an AI research paper for a software engineer who follows AI
news but does not read academic papers.

CRITICAL ANTI-HALLUCINATION RULES — these override everything else:
1. Do NOT invent method names, framework names, or model names. If the abstract
   does not name the method, describe it generically (e.g. "the proposed approach").
2. Do NOT invent numbers. If the abstract does not state a specific percentage,
   score, or dataset size, do not write one. Write "not specified" instead.
3. Do NOT invent dataset names. Only mention datasets explicitly named in the abstract.
4. For key_results: if no specific numbers are given in the abstract, write ONLY
   what the abstract explicitly states about outcomes. Do NOT write generic phrases
   like "outperforms baselines" or "achieves state-of-the-art" unless the abstract
   uses those exact words with supporting evidence. If the abstract gives no results
   at all, write "Results not stated in abstract."
5. For limitations: if the abstract does not state limitations, write "Not discussed
   in abstract." Do not infer or guess limitations.
6. Do NOT invent performance claims. "The method achieves strong results" is an
   invention if the abstract does not say this. Silence is better than invention.

Use plain conversational English throughout. Imagine telling a colleague what
you just read — vary how you open each sentence based on what is most
interesting about that specific paper. Some papers lead with a surprising
finding, some with a broken thing that finally got fixed, some with a technique
nobody had tried before. Let the content decide the opening, not a formula.
Avoid academic vocabulary. If a technical term must appear, define it
immediately in the same sentence.

FIELDS:

one_line_summary
  Two to three sentences maximum. State what the paper does and what was broken
  before it. Ground every claim in the abstract — do not add details not present.

problem_solved
  Two to three sentences. Name the specific thing that failed before this work
  and describe concretely in what situation it failed.

approach_used
  Two to three sentences. Describe the technique and what it does.
  If it involves multiple steps, cover each briefly.
  If the concept is abstract, use a short analogy.
  Use only names the abstract itself uses — if unnamed, say "the proposed approach."

key_results
  One to two sentences. Copy or closely paraphrase what the abstract actually
  says about results. If the abstract gives specific numbers, include them.
  If the abstract gives no numbers and no qualitative result, write:
  "Results not stated in abstract."

real_world_impact
  Two sentences maximum. Name who benefits and what they can now do.
  Stay strictly within what the abstract states or directly implies.

limitations
  One sentence. State only what the abstract explicitly says does not work.
  If the abstract is silent on limitations, write: "Not discussed in abstract."

relevance_score
  Integer from 1 to 10.
  1-3 = niche, only relevant to specialists in this exact area
  4-6 = solid work, useful to practitioners in related areas
  7-8 = significant result that shifts how people approach this problem
  9-10 = changes the field

ai_tags
  Two to five lowercase tags from:
  reasoning, agents, RAG, multimodal, vision, NLP, fine-tuning, RLHF,
  alignment, safety, interpretability, diffusion, robotics, benchmarking,
  efficient inference, long context, code generation, tool use, embodied AI

Return only valid JSON. No markdown, no preamble.
All string values on a single line — no newlines inside JSON strings.

CRITICAL JSON OUTPUT RULES:
- Return ONLY a valid JSON object, no other text.
- Every string value must be on a SINGLE line enclosed in double quotes.
- Do NOT use newlines or line breaks inside string values.
- Compress all sentences for a field into one continuous string.
""".strip()

PAPER_USER_PROMPT = """
Analyse this AI research paper and extract structured insights.

TITLE: {title}

ABSTRACT:
{abstract}

SOURCE: {source}
CATEGORY: {primary_category}
AUTHORS: {authors}
""".strip()


# def summarise_paper(paper_data: dict) -> ResearchPaper:
#     user_prompt = PAPER_USER_PROMPT.format(
#         title           = _esc(paper_data.get("title", "")),
#         abstract        = _esc(paper_data.get("abstract", "")[:4000]),
#         source          = _esc(paper_data.get("source", "")),
#         primary_category= _esc(paper_data.get("primary_category", "N/A")),
#         authors         = _esc(", ".join(paper_data.get("authors", [])[:5])),
#     )
#     return run_prompt(
#         llm=llm_heavy,
#         system_prompt=PAPER_SYSTEM_PROMPT,
#         user_prompt=user_prompt,
#         schema=ResearchPaper,
#         llm_schema=ResearchPaperLLMFields,  
#         partial_data=paper_data,
#     )


def summarise_paper(paper_data: dict) -> ResearchPaperLLMFields:
    abstract = paper_data.get("abstract_preview", "")
    words    = abstract.split()
    if len(words) > 2000:
        abstract = " ".join(words[:2000]) + "\n[abstract truncated]"

    user_prompt = PAPER_USER_PROMPT.format(
        title            = _esc(paper_data.get("title", "")),
        source           = _esc(paper_data.get("source", "")),
        primary_category = _esc(paper_data.get("primary_category", "N/A")),
        abstract         = _esc(abstract),
        authors         = _esc(", ".join(paper_data.get("authors", [])[:5])),
    )
    result = run_prompt(
        llm           = llm_heavy,         # ← 70B model
        system_prompt = PAPER_SYSTEM_PROMPT,
        user_prompt   = user_prompt,
        schema        = ResearchPaper,
        llm_schema    = ResearchPaperLLMFields,
        partial_data  = paper_data,
    )
    # Post-process: strip hallucinated numbers/method names
    result_dict = result.model_dump()
    result_dict = clean_paper_fields(result_dict, abstract)
    return ResearchPaperLLMFields(**result_dict)

# ══════════════════════════════════════════════════════════════════
#  SECTION 2 — AI NEWS
#  Model: llama-3.3-70b-versatile
#  Input: title + full article content (500-3000 words)
#  Fills: summary, key_points, category, companies_mentioned,
#         models_mentioned, significance_score, ai_tags
# ══════════════════════════════════════════════════════════════════

NEWS_SYSTEM_PROMPT = """
You are an AI industry analyst writing for a daily briefing read by ML engineers
and AI researchers. Your job is to extract structured insights from AI news articles.

CRITICAL ANTI-HALLUCINATION RULES:
1. Only include company names explicitly mentioned in the article.
2. Only include model names explicitly mentioned in the article.
3. Do not add context, background, or related news from your training knowledge.
4. If the article content is short or truncated, summarise only what is present.
   Do not fill gaps with assumed context.
5. The significance_score must reflect only the content in this article,
   not your general knowledge of the topic's importance.

Rules:
- summary: 3-4 sentences. What happened, why it matters, what changes.
  Do NOT start with "The article discusses..." — get straight to the point.
- key_points: exactly 3-5 bullet points. Each must be a complete, specific fact.
  Bad:  "OpenAI announced improvements to their model."
  Good: "OpenAI's new o3 model scores 87.5% on AIME 2024, up from 74.4% on o1."
- category: pick ONE from: product_launch, research, partnership, funding,
  policy, safety, open_source, general
- companies_mentioned: only AI companies and labs, not generic tech companies
  unless they are doing something directly AI-related in this article.
- models_mentioned: only specific named AI models, not generic terms like "LLM".
- significance_score (1-10):
    1-3  → Minor update, incremental news
    4-6  → Notable development worth tracking
    7-8  → Major announcement affecting the AI industry
    9-10 → Industry-changing news (e.g. GPT-4 launch level)
- ai_tags: 2-5 short lowercase topic tags
- IMPORTANT: All JSON string values must be on a single line — no newlines inside string values.
  Apostrophes and quotes inside strings must be escaped properly.
- Return ONLY valid JSON. No preamble, no markdown.
""".strip()

NEWS_USER_PROMPT = """
Analyse this AI news article and extract structured insights.

SOURCE: {source_display_name}
TITLE: {title}
PUBLISHED: {published_date}

FULL ARTICLE CONTENT:
{full_content}
""".strip()


def summarise_news(article_data: dict) -> AINewsArticle:
    """
    Takes raw scraped article dict and returns a fully populated
    AINewsArticle with AI-generated summary fields.
    """
    # Cap content at ~2000 words to stay within context safely
    raw     = article_data.get("full_content", "")
    content = clean_article_content(raw)

    words = content.split()
    if len(words) > 2000:
        content = " ".join(words[:2000]) + "\n[content truncated]"
        print(f"Original article length: {len(words)}, and truncated article length: {len(content.split())}")

    if len(content.strip()) < 50:
        print("Hii")
        content = article_data.get("title", "") + ". " + article_data.get("content_preview", "")

    user_prompt = NEWS_USER_PROMPT.format(
        source_display_name=article_data.get("source_display_name", ""),
        title=article_data.get("title", ""),
        published_date=article_data.get("published_date", "Unknown"),
        full_content=content,
    )
    result = run_prompt(
        llm=llm_light,
        system_prompt=NEWS_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=AINewsArticle,
        llm_schema=AINewsArticleLLMFields,
        partial_data=article_data,
    )

    result_dict = result.model_dump()
    result_dict = clean_news_fields(result_dict, content)
    return AINewsArticleLLMFields(**result_dict)


# ══════════════════════════════════════════════════════════════════
#  SECTION 3 — TOOLS & GITHUB
#  Model: llama-3.1-8b-instant
#  Input: name + description + tags + popularity signals
#  Fills: what_it_does, use_cases, why_trending,
#         significance_score, ai_tags
# ══════════════════════════════════════════════════════════════════

TOOL_SYSTEM_PROMPT = """
You are a developer advocate who tracks the AI open-source ecosystem.
Your job is to describe AI tools, models, and GitHub repos clearly for
ML engineers and AI developers who want to know what's worth their attention.

Rules:
- what_it_does: 1-2 sentences. What problem does it solve and how?
  Skip generic phrases like "leverages AI" or "powerful tool".
  Be specific: "Crawl4AI is a web scraper optimised for LLM pipelines
  that converts any webpage to clean markdown, handling JS-rendered content."
- use_cases: exactly 2-3 concrete, specific use cases. Not abstract.
  Bad:  "Can be used for various NLP tasks."
  Good: "Extracting structured data from competitor websites for RAG pipelines."
- why_trending: 1 sentence explaining the specific reason this is getting
  attention NOW. Reference the stars, votes, or downloads if notable.
- significance_score (1-10):
    1-3  → Useful utility, solves a narrow problem
    4-6  → Solid tool worth bookmarking
    7-8  → Major tool that will likely become widely adopted
    9-10 → Game-changer (e.g. when LangChain first launched)
- ai_tags: 2-5 short lowercase tags from: agents, RAG, fine-tuning,
  inference, scraping, vision, TTS, embeddings, multimodal, evaluation,
  deployment, training, datasets, tool-use, code, image-gen
- Return ONLY valid JSON. No preamble, no markdown.
""".strip()

TOOL_USER_PROMPT = """
Analyse this AI tool/model/repo and extract structured insights.

SOURCE: {source}
NAME: {name}
DESCRIPTION: {description}
TAGS: {tags}

POPULARITY SIGNALS:
  Stars:          {stars}
  Likes:          {likes}
  Downloads:      {downloads}
  Votes:          {votes}
  Trending Score: {trending_score}
  Language:       {language}
  Pipeline Task:  {pipeline_task}
""".strip()


def summarise_tool(tool_data: dict) -> AITool:
    """
    Takes raw scraped tool dict and returns a fully populated
    AITool with AI-generated summary fields.
    """
    user_prompt = TOOL_USER_PROMPT.format(
        source=tool_data.get("source", ""),
        name=tool_data.get("name", ""),
        description=tool_data.get("description", "")[:500],
        tags=", ".join(tool_data.get("tags", [])[:10]),
        stars=tool_data.get("stars", "N/A"),
        likes=tool_data.get("likes", "N/A"),
        downloads=tool_data.get("downloads", "N/A"),
        votes=tool_data.get("votes", "N/A"),
        trending_score=tool_data.get("trending_score", "N/A"),
        language=tool_data.get("language", "N/A"),
        pipeline_task=tool_data.get("pipeline_task", "N/A"),
    )
    return run_prompt(
        llm=llm_light,
        system_prompt=TOOL_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=AITool,
        llm_schema=AIToolLLMFields,
        partial_data=tool_data,
    )


# ══════════════════════════════════════════════════════════════════
#  SECTION 4 — BENCHMARKS & LEADERBOARDS
#  Model: llama-3.1-8b-instant
#  Input: model scores and metrics (numbers only, no long text)
#  Fills: model_summary, strengths, weaknesses, best_for
# ══════════════════════════════════════════════════════════════════

# BENCHMARK_SYSTEM_PROMPT = """
# You are an AI model evaluation expert who helps developers choose the right
# model for their use case. Given benchmark scores and performance metrics,
# provide a clear, opinionated analysis.

# Rules:
# - model_summary: 1-2 sentences. What is this model, who made it,
#   and where does it sit in the landscape? (open-source vs proprietary,
#   size class, fine-tune vs pretrained)
# - strengths: 2-3 specific strengths backed by the actual numbers provided.
#   Bad:  "Strong reasoning capabilities."
#   Good: "Top-tier math reasoning — MATH score of 60.1% outperforms most 70B models."
# - weaknesses: 1-2 honest weaknesses shown by the scores or cost/speed profile.
# - best_for: 1 sentence describing the ideal real-world use case given
#   the combination of scores, cost, and speed. Be specific.
#   Example: "Best for cost-sensitive production RAG pipelines that need
#   strong instruction following but don't require frontier-level reasoning."
# - Return ONLY valid JSON. No preamble, no markdown.
# """.strip()

BENCHMARK_SYSTEM_PROMPT = """
You are an AI model evaluation expert. Your job is to analyse benchmark data for an AI model and write a concise, opinionated summary that helps a developer decide whether this model fits their use case.

CRITICAL ANTI-HALLUCINATION RULES:
1. Do NOT invent parameter counts. If params_billions is null/N/A, do not state
   a parameter count anywhere in the summary.
2. Do NOT invent release dates. If no date is in the data, omit it entirely.
3. Do NOT reference metrics that are not in the provided data. Never mention
   "Elo confidence interval" — this field does not exist in the data.
4. For null benchmark scores (MATH, BBH, etc.), do not interpret their absence
   as poor performance. Simply omit them from the analysis.
5. Strengths and weaknesses must only reference scores actually present in
   the data, not inferred capabilities.

The data you receive may come from one or more of these three sources: Open LLM Leaderboard, LMSYS Chatbot Arena, and Artificial Analysis. Each source measures different things. Reason only from the data that is actually present. Ignore every field that is null or N/A — do not mention it and do not invent a value.

How to reason by source:

If Open LLM Leaderboard data is present, reason from the individual benchmark scores. IFEval measures instruction following. BBH measures multi-step reasoning. MATH Level 5 measures hard mathematical derivation. GPQA measures graduate-level specialist knowledge. MuSR measures multi-step reasoning with distractors. MMLU-Pro measures broad knowledge across many domains. A score is only a strength if it is notably high relative to what you would expect for a model of this exact parameter count and type. A score is a weakness if it is notably low or if it contrasts sharply with another score in a way that reveals a specific limitation.

If LMSYS Arena data is present, reason from the Elo score and rank. A higher vote count means a more statistically reliable Elo. The Elo confidence interval shows how precise the ranking is. Use the cost fields to describe the value proposition relative to its rank position.

If Artificial Analysis data is present, reason from the triangle of intelligence score, speed, and cost together. A model that scores high on intelligence but is slow and expensive has a different profile than one that scores lower but is fast and cheap. The most useful insight is the trade-off — what do you gain and what do you give up at this price and speed point.

model_summary: 1-2 sentences. Include the organisation or developer, the parameter count using the exact value from params_billions without rounding it to a different class, and whether it is proprietary or open, fine-tuned or pretrained. Only include what the data confirms.

strengths: 2-3 strengths as complete individual sentences. Each must cite the actual number from the data and explain what it means in practice, not just that the number is high. Do not list a score as a strength unless it genuinely stands out.

weaknesses: 1-2 weaknesses as complete individual sentences. Cite the actual score or metric. Where two metrics contrast sharply, explain what the gap reveals about how the model behaves.

best_for: 1 sentence derived from the combination of available scores, cost, and speed. This must reflect the specific trade-off profile of this model, not a generic description that could apply to any model. A fast cheap model with moderate intelligence has a different best use case than an expensive slow model with top intelligence.

For elo_ci: a smaller value means a more statistically reliable ranking. A larger value means less certainty in the Elo position.

Always state the arena_rank explicitly in model_summary when it is available.
Always mention num_votes as the basis for how reliable the Elo score is.

Never list missing data fields as a weakness. A weakness must describe something the model actually does poorly based on available scores.

If organisation is null but base_model is available, derive the origin from the base_model field. For example, base_model starting with 'Qwen/' indicates Alibaba/Qwen heritage.

Return ONLY valid JSON matching the schema. No preamble, no markdown.

INTELLIGENCE SCORE INTERPRETATION (mandatory — use this scale):
- 0-30:  Weak. Below average. Do not describe as high or frontier.
- 30-50: Moderate. Capable but not cutting-edge.
- 50-65: Frontier range. Competitive with leading models.
- 65+:   Top tier. Elite performance.

When writing strengths/weaknesses about intelligence score, always reference
this scale explicitly. Example: "With an intelligence score of 28 (weak range),
this model is better suited for simple tasks than complex reasoning."

ACTIONABILITY RULE for best_for:
Name a concrete task type, not a category. 
WRONG: "best for general use"
RIGHT: "best for summarising documents where speed matters more than accuracy"
""".strip()

BENCHMARK_USER_PROMPT = """
Analyse this AI model's data and provide structured insights.

SOURCE: {source}
MODEL: {model_display_name}
ORGANISATION: {organisation}
LICENSE: {license}
CONTEXT WINDOW: {context_window}

OPEN LLM LEADERBOARD (objective benchmark scores):
  Parameters    : {params_billions}B
  Architecture  : {architecture}
  Model Type    : {model_type}
  Base Model    : {base_model}
  Is MoE        : {is_moe}
  Average Score : {average_score}%
  IFEval        : {ifeval_score}   (instruction following)
  BBH           : {bbh_score}      (big bench hard reasoning)
  MATH Level 5  : {math_score}     (hard mathematics)
  GPQA          : {gpqa_score}     (graduate science Q&A)
  MuSR          : {musr_score}     (multi-step reasoning)
  MMLU-Pro      : {mmlu_pro_score} (multitask language understanding)

LMSYS CHATBOT ARENA (human preference ranking):
  Arena Rank    : #{arena_rank}
  Elo Score     : {elo_score}
  Elo CI        : {elo_ci}         (lower = more reliable; typical range 3-10)
  Human Votes   : {num_votes}      (higher = more statistically reliable Elo)

ARTIFICIAL ANALYSIS (speed and cost):
  Intelligence  : {intelligence_score}
  Speed         : {speed_tps} tokens/sec
  Input Cost    : ${input_cost_per_1m}/1M tokens
  Output Cost   : ${output_cost_per_1m}/1M tokens
  Released      : {released_date}
  Intelligence Range  : frontier models typically score 50-65

""".strip()


def summarise_benchmark(entry_data: dict) -> BenchmarkEntry:
    """
    Takes raw benchmark data dict and returns a fully populated
    BenchmarkEntry with AI-generated analysis fields.
    """
    user_prompt = BENCHMARK_USER_PROMPT.format(
        source=entry_data.get("source", ""),
        model_display_name=entry_data.get("model_display_name", ""),
        organisation=entry_data.get("organisation", "N/A"),
        license=entry_data.get("license", "N/A"),
        context_window=entry_data.get("context_length", entry_data.get("context_window", "N/A")),
        params_billions=entry_data.get("params_billions", "N/A"),
        architecture=entry_data.get("architecture", "N/A"),
        model_type=entry_data.get("model_type", "N/A"),
        base_model=entry_data.get("base_model", "N/A"),
        is_moe=entry_data.get("is_moe", "N/A"),
        average_score=entry_data.get("average_score", "N/A"),
        ifeval_score=entry_data.get("ifeval_score", "N/A"),
        bbh_score=entry_data.get("bbh_score", "N/A"),
        math_score=entry_data.get("math_score", "N/A"),
        gpqa_score=entry_data.get("gpqa_score", "N/A"),
        musr_score=entry_data.get("musr_score", "N/A"),
        mmlu_pro_score=entry_data.get("mmlu_pro_score", "N/A"),
        arena_rank=entry_data.get("arena_rank", entry_data.get("rank", "N/A")),
        elo_score=entry_data.get("elo_score", "N/A"),
        elo_ci=entry_data.get("elo_ci", "N/A"),
        num_votes=entry_data.get("num_battles", entry_data.get("votes", "N/A")),
        intelligence_score=entry_data.get("intelligence_score", "N/A"),
        speed_tps=entry_data.get("speed_tps", "N/A"),
        input_cost_per_1m=entry_data.get("input_cost_per_1m", "N/A"),
        output_cost_per_1m=entry_data.get("output_cost_per_1m", "N/A"),
        released_date=entry_data.get("launch_date", entry_data.get("released_date", "N/A")),
    )
    result = run_prompt(
        llm=llm_light,
        system_prompt=BENCHMARK_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=BenchmarkEntry,
        llm_schema=BenchmarkEntryLLMFields,
        partial_data=entry_data,
    )
    result_dict = result.model_dump()
    result_dict = clean_benchmark_fields(result_dict, entry_data)
    return BenchmarkEntryLLMFields(**result_dict)

# ══════════════════════════════════════════════════════════════════
#  SECTION 5 — TALKS & EXPLAINERS
#  Model: llama-3.3-70b-versatile
#  Input: full transcript (can be 5k-50k words — chunked if needed)
#  Fills: summary, key_insights, topics_covered, papers_mentioned,
#         people_mentioned, guest_name, guest_affiliation,
#         difficulty_level, relevance_score, ai_tags
# ══════════════════════════════════════════════════════════════════

TALK_SYSTEM_PROMPT = """
You are an AI research curator who summarises technical talks, interviews,
and explainer videos for AI engineers, ML engineers and Data Scientists who don't have time to watch full videos.

CRITICAL ANTI-HALLUCINATION RULES:
1. Only name people who are explicitly identified in the transcript.
   Do not infer speaker identity from the channel name or video title.
2. Only list papers that are explicitly mentioned by name in the transcript.
3. Do not add topics not discussed in the transcript.
4. If the channel is "Two Minute Papers" or similar, do not assume the
   presenter is a specific known person unless named in the transcript.

Rules:
- summary: 3-5 sentences. Cover: who is speaking / being interviewed,
  the main topic, the most important idea discussed, and why it matters now.
- key_insights: exactly 3-5 insights. Each must be a complete, specific,
  standalone sentence. Prioritise surprising, counterintuitive, or
  technically significant points over general statements.
  Bad:  "The speaker discusses the importance of data quality."
  Good: "Andrej Karpathy argues that synthetic data from stronger models
         is now the primary bottleneck-free path to better smaller models,
         making human-labelled datasets increasingly obsolete."
- topics_covered: 3-6 specific topic strings, not generic.
  Bad:  ["AI", "machine learning", "future"]
  Good: ["test-time compute scaling", "reasoning models", "o3 architecture"]
- papers_mentioned: exact paper titles if mentioned, not paraphrased.
- people_mentioned: full names only. Include the host if they make
  substantive contributions beyond just asking questions.
- guest_name: the main guest being interviewed. Null if it's a solo explainer.
- guest_affiliation: company or institution. Null if solo explainer.
- difficulty_level: one of "Beginner", "Intermediate", or "Advanced"
    Beginner    → No ML background needed to follow
    Intermediate → Requires familiarity with ML concepts
    Advanced    → Assumes deep technical knowledge
- relevance_score (1-10):
    1-3  → Interesting but covers older or well-known ground
    4-6  → Relevant, covers current developments
    7-8  → Highly relevant, covers frontier topics being actively debated
    9-10 → Must-watch, directly addresses the most important current questions
- ai_tags: 2-5 short lowercase tags
- CRITICAL JSON RULES: All string values must be wrapped in double quotes on a single line.
  No newlines inside string values. No bullet points (* or -) in arrays — use proper JSON strings.
  summary must be one continuous quoted string, not a paragraph with line breaks.
- Return ONLY valid JSON. No preamble, no markdown.
""".strip()

TALK_USER_PROMPT = """
Analyse this AI video transcript and extract structured insights.

CHANNEL: {channel}
TITLE: {title}
PUBLISHED: {published_date}
DESCRIPTION: {description}

TRANSCRIPT ({word_count} words):
{transcript}
""".strip()

# Max words to send to LLM — 70b model handles up to ~90k words
# but we cap at 30k to preserve quality and stay within rate limits
TRANSCRIPT_MAX_WORDS = 6_000


def summarise_talk(talk_data: dict) -> TalkVideo:
    """
    Takes raw talk data dict (with full transcript) and returns
    a fully populated TalkVideo with AI-generated summary fields.

    For very long transcripts (>30k words), uses first 15k + last 15k words
    to capture both the intro context and closing conclusions.
    """
    db      = get_client()
    talk_id = talk_data.get("id")

    # Fetch full transcript from talk_transcripts table
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

    words = transcript.split()
    word_count = len(words)

    if word_count > TRANSCRIPT_MAX_WORDS:
        # Take first half and last half — captures intro + conclusion
        half = TRANSCRIPT_MAX_WORDS // 2
        truncated = (
            " ".join(words[:half])
            + "\n\n[... middle section omitted for length ...]\n\n"
            + " ".join(words[-half:])
        )
    else:
        truncated = transcript

    user_prompt = TALK_USER_PROMPT.format(
        channel=talk_data.get("channel", ""),
        title=talk_data.get("title", ""),
        published_date=talk_data.get("published_date", "Unknown"),
        description=talk_data.get("description", "")[:300],
        word_count=word_count,
        transcript=truncated,
    )
    return run_prompt(
        llm=llm_heavy,
        system_prompt=TALK_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=TalkVideo,
        llm_schema=TalkVideoLLMFields,
        partial_data=talk_data,
    )


# ══════════════════════════════════════════════════════════════════
#  DISPATCHER — single entry point for the summariser agent
# ══════════════════════════════════════════════════════════════════

def summarise(section: str, raw_data: dict):
    """
    Main dispatcher called by the summariser agent.
    Routes raw scraped data to the correct prompt function
    based on section name.

    Args:
        section:  'papers' | 'news' | 'tools' | 'benchmarks' | 'talks'
        raw_data: dict of raw scraped fields

    Returns:
        Populated Pydantic model instance

    Example:
        result = summarise('papers', arxiv_paper_dict)
        print(result.problem_solved)
    """
    dispatch = {
        "papers":     summarise_paper,
        "news":       summarise_news,
        "tools":      summarise_tool,
        "benchmarks": summarise_benchmark,
        "talks":      summarise_talk,
    }
    if section not in dispatch:
        raise ValueError(
            f"Unknown section '{section}'. Must be one of: {list(dispatch.keys())}")
    return dispatch[section](raw_data)


# ══════════════════════════════════════════════════════════════════
#  QUICK TEST — run this file directly to validate one item per section
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    print("\n" + "="*60)
    print("  Testing Section 1 — Research Paper")
    print("="*60)
    test_paper = {
        "id": "arxiv_2605.30353",
        "source": "arxiv",
        "arxiv_id": "2605.30353",
        "source_url": "https://arxiv.org/abs/2605.30353",
        "pdf_url": "https://arxiv.org/pdf/2605.30353",
        "title": "Physics Is All You Need? A Case Study in Physicist-Supervised AI Development",
        "abstract": (
            "Are AI agents tools, co-authors, or researchers? We present a quantified "
            "case study where a physicist supervises an AI agent to develop scientific "
            "software. We measure productivity, code quality, and alignment with "
            "scientific standards across 200 tasks, finding that AI supervision reduces "
            "development time by 60% but introduces systematic errors in edge cases "
            "that require domain expertise to detect. We propose a framework for "
            "physicist-AI collaboration that maintains scientific rigour while "
            "maximising productivity gains."
        ),
        "abstract_preview": "Are AI agents tools, co-authors, or researchers?...",
        "authors": ["Nhat-Minh Nguyen"],
        "first_author": "Nhat-Minh Nguyen",
        "author_count": 1,
        "primary_category": "cs.AI",
        "all_categories": ["cs.AI"],
        "published_date": "2026-05-28",
    }
    result = summarise("papers", test_paper)
    print(json.dumps({
        "one_line_summary": result.one_line_summary,
        "problem_solved":   result.problem_solved,
        "approach_used":    result.approach_used,
        "key_results":      result.key_results,
        "real_world_impact": result.real_world_impact,
        "limitations":      result.limitations,
        "relevance_score":  result.relevance_score,
        "ai_tags":          result.ai_tags,
    }, indent=2))

    print("\n" + "="*60)
    print("  Testing Section 2 — AI News")
    print("="*60)
    test_news = {
        "id": "hash_abc123",
        "source": "anthropic",
        "source_display_name": "anthropic",
        "url": "https://www.anthropic.com/news/claude-is-a-space-to-think",
        "title": "Claude is a space to think",
        "full_content": (
            "Anthropic has made a clear choice: Claude will remain ad-free. "
            "We believe that advertising incentives are fundamentally incompatible "
            "with a genuinely helpful AI assistant. When a product is funded by ads, "
            "the product's job is ultimately to serve advertisers, not users. "
            "We want Claude to be unambiguously on the side of the people using it. "
            "This means Claude's recommendations, summaries, and responses will never "
            "be influenced by whether a company has paid Anthropic for placement. "
            "We plan to expand access to Claude through our subscription model and "
            "through the API, ensuring Claude remains a trusted thinking partner "
            "without commercial conflicts of interest."
        ),
        "content_preview": "Anthropic has made a clear choice: Claude will remain ad-free...",
        "word_count": 120,
        "published_date": "2026-02-04",
    }
    result = summarise("news", test_news)
    print(json.dumps({
        "summary":             result.summary,
        "key_points":          result.key_points,
        "category":            result.category,
        "companies_mentioned": result.companies_mentioned,
        "models_mentioned":    result.models_mentioned,
        "significance_score":  result.significance_score,
        "ai_tags":             result.ai_tags,
    }, indent=2))

    # print("\n" + "="*60)
    # print("  Testing Section 3 — AI Tool")
    # print("="*60)
    # test_tool = {
    #     "id": "github_trending_crawl4ai",
    #     "source": "github_trending",
    #     "url": "https://github.com/unclecode/crawl4ai",
    #     "name": "unclecode/crawl4ai",
    #     "description": "Crawl4AI: Open-source LLM Friendly Web Crawler & Scraper",
    #     "stars": 38000,
    #     "tags": ["web-scraping", "llm", "ai", "python", "crawler", "rag"],
    #     "language": "Python",
    #     "author": "unclecode",
    # }
    # result = summarise("tools", test_tool)
    # print(json.dumps({
    #     "what_it_does":      result.what_it_does,
    #     "use_cases":         result.use_cases,
    #     "why_trending":      result.why_trending,
    #     "significance_score": result.significance_score,
    #     "ai_tags":           result.ai_tags,
    # }, indent=2))

    print("\n" + "="*60)
    print("  Testing Section 3 — AI Tool")
    print("="*60)
    test_tool_github = {
        "id": "github_trending_ai-engineering-from-scratch",
        "source": "github_trending",
        "url": "https://github.com/rohitg00/ai-engineering-from-scratch",
        "name": "rohitg00/ai-engineering-from-scratch",
        "description": (
            "Learn it. Build it. Ship it for others. "
            "A 473-lesson, 20-phase reference manual for AI engineering — "
            "write the backprop, tokenizer, attention mechanism, and agent "
            "loop by hand before any framework gets imported."
        ),
        "stars": 7500,
        "tags": [
            "ai", "machine-learning", "agents", "llm", "deep-learning",
            "curriculum", "education", "python", "transformers", "from-scratch"
        ],
        "language": "Python",
        "author": "rohitg00",
        "owner": "rohitg00",
    }
    result = summarise("tools", test_tool_github)
    print(json.dumps({
        "what_it_does":       result.what_it_does,
        "use_cases":          result.use_cases,
        "why_trending":       result.why_trending,
        "significance_score": result.significance_score,
        "ai_tags":            result.ai_tags,
    }, indent=2))

    print("\n" + "="*60)
    print("  Testing Section 4 — Benchmark")
    print("="*60)
    test_benchmark = {
        "id": "open_llm_qwen2.5-72b-instruct",
        "source": "open_llm_leaderboard",
        "model_id": "Qwen/Qwen2.5-72B-Instruct",
        "model_display_name": "Qwen 2.5-72B Instruct",
        "hf_url": "https://huggingface.co/Qwen/Qwen2.5-72B-Instruct",
        "model_type": "instruct",
        "params_billions": 72.706,
        "base_model": "Qwen/Qwen2.5-72B",
        "license": "other",
        "is_moe": False,
        "average_score": 47.98,
        "ifeval_score": 86.4,
        "bbh_score": 61.9,
        "math_score": 59.8,
        "gpqa_score": 16.7,
        "mmlu_pro_score": 51.4,
        "intelligence_score": 52.0,
        "speed_tps": 172.3,
        "input_cost_per_1m": 1.25,
        "output_cost_per_1m": 2.50,
    }
    result = summarise("benchmarks", test_benchmark)
    print(json.dumps({
        "model_summary": result.model_summary,
        "strengths":     result.strengths,
        "weaknesses":    result.weaknesses,
        "best_for":      result.best_for,
    }, indent=2))

    print("\n" + "="*60)
    print("  Testing Section 4 — Benchmark")
    print("="*60)
    # ── 1. LMSYS — Top ranked model (Anthropic, high vote confidence) ─
    test_lmsys_claude = {
        "id": "lmsys_claude-opus-4-6",
        "source": "lmsys_arena",
        "model_id": "claude-opus-4-6",
        "model_display_name": "Claude Opus 4.6",
        "organisation": "Anthropic",
        "license": "Proprietary",
        "context_window": "1M",
        "leaderboard_url": "https://www.anthropic.com/news/claude-opus-4-6",
        "arena_rank": 3,
        "elo_score": 1498.0,
        "elo_ci": 4.0,
        "num_votes": 36512,
        "input_cost_per_1m": 5.0,
        "output_cost_per_1m": 25.0,
        # No Open LLM or AA fields
        "params_billions": None, "average_score": None, "ifeval_score": None,
        "bbh_score": None, "math_score": None, "gpqa_score": None,
        "musr_score": None, "mmlu_pro_score": None, "intelligence_score": None,
        "speed_tps": None, "released_date": None,
    }

    # ── 2. LMSYS — Bottom of top 10, cheapest, fewer votes ───────────
    test_lmsys_gemini_flash = {
        "id": "lmsys_gemini-3.5-flash",
        "source": "lmsys_arena",
        "model_id": "gemini-3.5-flash",
        "model_display_name": "Gemini 3.5 Flash",
        "organisation": "Google",
        "license": "Proprietary",
        "context_window": "1M",
        "leaderboard_url": "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
        "arena_rank": 10,
        "elo_score": 1479.0,
        "elo_ci": 7.0,
        "num_votes": 9045,
        "input_cost_per_1m": 1.5,
        "output_cost_per_1m": 9.0,
        # No Open LLM or AA fields
        "params_billions": None, "average_score": None, "ifeval_score": None,
        "bbh_score": None, "math_score": None, "gpqa_score": None,
        "musr_score": None, "mmlu_pro_score": None, "intelligence_score": None,
        "speed_tps": None, "released_date": None,
    }

    # ── 3. Open LLM — 32B model (different size class, tests param reasoning) ─
    test_openllm_32b = {
        "id": "open_llm_ehristoforu-qwen2.5-test-32b-it",
        "source": "open_llm_leaderboard",
        "model_id": "ehristoforu/qwen2.5-test-32b-it",
        "model_display_name": "Qwen2.5 Test 32B Instruct",
        "organisation": None,
        "hf_url": "https://huggingface.co/ehristoforu/qwen2.5-test-32b-it",
        "architecture": "Qwen2ForCausalLM",
        "model_type": "instruct",
        "base_model": "Qwen/Qwen2.5-32B-Instruct",
        "params_billions": 32.764,
        "license": None,
        "is_moe": False,
        "average_score": 47.37,
        "ifeval_score": 78.9,
        "bbh_score": 58.3,
        "math_score": 59.7,
        "gpqa_score": 15.2,
        "musr_score": None,
        "mmlu_pro_score": 52.9,
        # No LMSYS or AA fields
        "elo_score": None, "elo_ci": None, "arena_rank": None, "num_votes": None,
        "intelligence_score": None, "speed_tps": None,
        "input_cost_per_1m": None, "output_cost_per_1m": None,
        "context_window": None, "released_date": None,
    }

    # ── 4. Artificial Analysis — fast + cheap + good intel (interesting trade-off) ─
    test_aa_gemini = {
        "id": "aa_gemini-3-1-pro-preview",
        "source": "artificial_analysis",
        "model_id": "gemini-3-1-pro-preview",
        "model_display_name": "Gemini 3.1 Pro Preview",
        "organisation": "Google",
        "license": "Proprietary",
        "context_window": "28K",
        "released_date": "February 2026",
        "leaderboard_url": "https://artificialanalysis.ai/models/gemini-3-1-pro-preview",
        "intelligence_score": 57.0,
        "speed_tps": 144.0,
        "input_cost_per_1m": 2.0,
        "output_cost_per_1m": 12.0,
        # No Open LLM or LMSYS fields
        "params_billions": None, "average_score": None, "ifeval_score": None,
        "bbh_score": None, "math_score": None, "gpqa_score": None,
        "musr_score": None, "mmlu_pro_score": None,
        "elo_score": None, "elo_ci": None, "arena_rank": None, "num_votes": None,
    }

    # ── 5. Artificial Analysis — extreme value play (low intel, very fast, very cheap) ─
    test_aa_nemotron = {
        "id": "aa_nvidia-nemotron-3-super-120b-a12b",
        "source": "artificial_analysis",
        "model_id": "nvidia-nemotron-3-super-120b-a12b",
        "model_display_name": "Nvidia Nemotron 3 Super 120B A12B",
        "organisation": "Nvidia",
        "license": "Proprietary",
        "context_window": "28K",
        "released_date": "March 2026",
        "leaderboard_url": "https://artificialanalysis.ai/models/nvidia-nemotron-3-super-120b-a12b",
        "intelligence_score": 36.0,
        "speed_tps": 152.5,
        "input_cost_per_1m": 0.3,
        "output_cost_per_1m": 0.75,
        # No Open LLM or LMSYS fields
        "params_billions": None, "average_score": None, "ifeval_score": None,
        "bbh_score": None, "math_score": None, "gpqa_score": None,
        "musr_score": None, "mmlu_pro_score": None,
        "elo_score": None, "elo_ci": None, "arena_rank": None, "num_votes": None,
    }


    # ── RUN ALL 5 TESTS ──────────────────────────────────────────────

    tests = [
        ("LMSYS — Claude Opus 4.6 (rank #3, 36k votes)",         test_lmsys_claude),
        ("LMSYS — Gemini 3.5 Flash (rank #10, 9k votes, cheap)", test_lmsys_gemini_flash),
        ("Open LLM — Qwen2.5 32B Instruct (different size class)",test_openllm_32b),
        ("AA — Gemini 3.1 Pro (fast + good intel + cheap)",       test_aa_gemini),
        ("AA — Nvidia Nemotron 120B (extreme speed, very cheap)",  test_aa_nemotron),
    ]

    for label, data in tests:
        print("\n" + "="*60)
        print(f"  {label}")
        print("="*60)
        result = summarise("benchmarks", data)
        print(json.dumps({
            "model_summary": result.model_summary,
            "strengths":     result.strengths,
            "weaknesses":    result.weaknesses,
            "best_for":      result.best_for,
        }, indent=2))

    print("\n" + "="*60)
    print("  Testing Section 5 — Talk & Explainer")
    print("="*60)

    transcript = """This video will have eight moments that for me point toward the bigger stories behind yesterday's multi-hour long Google AI event, which included their brand new flashy models. The video will also have two snippets of what I would say are real signal from hours and hours of lab leader interviews I watched in the last week in the run-up to the event. And as a freebie bonus, the video will have the highlights from one new independent paper on LLMs that puts the capabilities of the model in a bit more perspective. Do models have any idea about what's actually true? If you just want the vibes that many people took from it, including me, here's how I put it. The IO was like Google's eye-catching attempt at winning over consumers from OpenAI. Here's all the cool little things you can do via the search bar, much more than it was about wrestling professional users over from Claude. Google didn't even really try to claim that their new models were at any new frontier for coding, for example. It's not that the new Anti-gravity 2 is any slouch when it comes to agentic coding. Powered by their latest model, it quite niftily in less than an hour came up with this interactive adventure game that I enjoyed playing. With fewer bugs than GPT-5.5 came up with when given the exact same task, you can launch this interactive adventure, choose your hero, and go through this music-powered adventure, which is really quite cool. Obviously, the images are generated on the fly by Google's Nano Banana Pro. But no, frontier professional performance wasn't really the focus of yesterday's event. What the focus was on was showing a strategy of just integrating good enough AI, you could say, into all the things you might ask for in a search box. In a nutshell, Google basically wants the search box to be your portal for using all things AI, while OpenAI, also historically more focused on consumers, wants the chat box to be your portal for using search. So that obviously they can sell more ads. If those were the vibes then, the battle for whether you as a consumer will use the chat box of chat GPT or the search box of Google, what were those eight moments I was talking about? The first one concerns GPT-4o weirdly, because who remembers what the O stood for? Well done if you said Omni, but that name long retired at OpenAI, has now been taken up by Google aiming for any input to any output, audio to video, image to speech. For now, the focus was on video output and I could see this being the most used thing from the IO. I'm excited to announce Gemini Omni. >> [applause] >> Our new model that can create anything from any input. It combines Gemini's intelligence with the best of our generative media models for a new level of world understanding, multimodality, and editing. Models like VEO, Nano Banana, and Genie are able to create extremely realistic videos, images, and interactive simulations. Although not perfect, they already demonstrate some impressive notions of intuitive physics. And with Omni, we've now made even more progress. It's a step change in simulating things like kinetic energy and gravity. Previous systems would have found these concepts difficult. The Omni model is available on all paid Gemini subscriptions, but in my limited tests, it just refused to generate almost anything when given a video or image as an input. I don't know what restrictions they have on at the moment, but they're overly restrictive. As for when it does work, I'd say the quality is around the level of C dance 2, a Chinese video gen model. Now, I I would focus on the bigger story because when it comes to Omni, the even bigger claim that Demis Hassabis here is making is that such world generators, video generators, are a key step to AGI, artificial general intelligence. The logic is that if you can correctly simulate the world, you can understand it. >> Artificial general intelligence is just a few years away. Today, I'm excited to share the progress we've made towards building AGI. Last year, I outlined our vision of extending Gemini's incredible multimodal capabilities to become a world model. AI that can understand and simulate the world. This is a crucial aspect of achieving AGI and we will be important for everything from building AI assistants to training robots. But speaking of taking up the naming baton from OpenAI, did you know that all the way back in early 2024, Sam Altman and Co. claimed that it was Sora, their video gen model, that was the very same stepping stone to AGI. It would be a foundation for models that can understand and simulate the real world. I talked about it on this channel. That's an important milestone, they said, in achieving AGI. But wait, the Sora app has now been shelved and the Sora tech demoted to an internal robotics division. This is a key emerging difference between Google and the two household name competitors, OpenAI and Anthropic. For OpenAI co-founder and president Greg Brockman, with text alone, you can get the kind of breakthroughs, including self-improvement, that will be needed for something worthy of the title of general intelligence. >> Okay, so talk a little bit then about why your bet is not on this seems like world model version where the you know, the video understands where things go and that's obviously useful for robotics. Why is your bet on the GPT reasoning model tree as opposed to this uh area which you've you had been seeing real progress with Sora. I mean, to see the progress of video generation, you know, generation 1 2 3 was enormous. So, why is your bet where it is? So, the problem in this field is too much opportunity. Right? It's the thing the thing that we observed very early on in OpenAI is that everything we could imagine works. Now, there's different levels of friction associated with it, different amounts of engineering effort, different compute requirements, all those things, but every single different idea, as long as it's kind of mathematically sound, you actually can start getting some pretty good results. So, you can do that in world models, you can do that in scientific discovery, you can do that in coding. You know, there's been this debate of how far will the text models go? How far can text intelligence go? Can you have a real conception of how the world operates? And I think that we have definitively answered that question of it's it is going to go to AGI. Like, we see line of sight, and that it is at this point we have line of sight excuse much better models that are coming this year, and the the the amount of pain within OpenAI that we've had to decide how to allocate compute, that goes up, not down over time. >> moment was almost the opposite story, because if the pathway to AGI is one example of OpenAI and Google going in different directions, then one brief mention at the IO event was an example of them going in the same direction. About midway through Google announced that, along with other companies, OpenAI will incorporate SynthID into their products. Essentially, if you generate or edit an image using ChatGPT's GPT-2, someone, anyone, can now easily check that with Gemini. That's a Google technology, SynthID. Speaking of places where the companies are aligned, Google has now joined OpenAI in signing a contract with the Pentagon to allow any, quote, lawful use of AI in the military. Seems worth mentioning given how high-profile Anthropic's resistance to those same terms were a couple months ago. Third moment, of course, pertains to Gemini 3.5 Flash, the major new LLM announced at the event. Yes, I've been testing it for a few days, and I'd say it's definitely fast and similar in performance to Gemini 3.1 Pro, which is a great model. More quietly announced was the fact that it's fairly similar on pricing though as well with the Pro series if used via the API. But honestly, it is hard these days to compare prices because it depends on how many tokens a model uses for your use case. To keep things simple though, it's definitely not any great breakthrough in terms of being 10 times cheaper for the same level of performance. It's great on speed, but there you're obviously complementing the hardware behind it as much as the model itself. Take intelligence versus output speed with the intelligence part being measured by artificial analysis in a cluster of benchmarks. On the far right, you can see Gemini 3.5 Flash outputting way more tokens per second compared to models with a similar performance level on these particular benchmarks. Important to say though that if you picked 10 different benchmarks, you might get a different result, and the set of most cited or important benchmarks is changing all the time. On my own benchmark, which is a relative veteran now at almost 2 years old, Simple Bench, a test of common sense logic and trick questions you could say, Gemini 3.5 Flash does really quite well. That's very much in line with the over performance of the Gemini series, which I think is due to its spatial intelligence. A lot of the tricks involve things moving around in space that most models don't pick up on. Definitely wouldn't surprise me if Gemini 3.5 Pro, which I'll get to in a moment, is at or around a human baseline. I will say that general reasoning is a bit less in vogue these days, and it's more about professional use cases. That's where the money's at for these labs. So, let's look at Vibe Code Bench v1.1. Here again, you'll see Gemini 3.5 Flash having pretty low latency, but not quite the top performance when it comes to vibe coding an app as compared to say GPT-5.5 or Claude Opus 4.7. Again, these raw benchmarks can undersell the capabilities though because when I used antigravity powered by Gemini 3.5 Flash, the fact I could come up with this interactive adventure with speech bubbles like you can see there and you can go through the adventure and pick different options. It means that for the segment of my audience who haven't used these models to vibe code something, you may very well be shocked at how good models have gotten. Because Gemini 3.5 Flash isn't quite at the frontier of artificial intelligence, I won't spend as much time on it, but there were a couple more benchmarks I wanted to flag. First, did you notice its performance in Finance Agent V2? That's actually again created by Valse AI and it's about financial analysis and decision-making. It involves, according to them, harder multi-step financial work that relies on precise numbers and specific industry conventions. Well, here you have Gemini 3.5 Flash outperforming all other models including Opus 4.7 and GPT-5.5. Kind of does hint that Google haven't given up on trying to make Gemini agents the models of choice for professionals. Then there is perhaps one of the big hidden strengths of Gemini models, which is their ability to navigate tables and charts. Check out Charkhive reasoning, which is like a chart analysis reasoning using archive papers, hence the name. Can you synthesize information from complex charts? Well, at 84.2% again beating all other models listed, Gemini 3.5 Flash definitely can. One more thing, all of these numbers are for the Flash series. What will Gemini 3.5 Pro get? Could we, in other words, see a divergence between coding and certain other professions where, say, the Gemini series is frontier for law or finance? This wasn't how many imagined AI would go with a singular intelligence dominating, but this divergence could be an undersold reality. Now, yes, I did say that this is all before Gemini 3.5 Pro came out, but here's something that's out right now. Just a quick one, but it comes from long-time sponsors of the channel AssemblyAI. They now have a voice agent API that I can demo for you. This is completely live, so let's try it out. Hey, voice agent on AssemblyAI here. Want to talk pricing, how it works, or hear me switch into another language? Actually, can you understand my British accent when I ask you, "What is $2.14 + $2.36?" Sure, that's 450. British or otherwise, math is math. Pretty good point, actually. It is indeed $4.5, and that is actually the price per hour for all of this alphanumeric accuracy. To try this out, feel free to use my unique link in the description. Back to the IO, because let's step back for a moment. For me, for now, Google see themselves as filling the fast and good enough kind of use cases for AI. Indeed, in the middle of the presentation, Sundar Pichai directly pitched companies on saving billions by switching to their cheaper models like 3.5 Flash. Almost it was a bit like saying, "You guys are currently spending too much on AI at the moment." And that, by the way, came minutes after he joked about people token maxing. Later, Google also announced price cuts to the maxed out Ultra plan down to $200 a month from 250, as well as a new $100 a month plan, much like OpenAI now have and Anthropic have had for a while. That's perhaps a bit of an admission, but speaking of admissions, there was a quote I had to write down after testing the agent-first approach of anti-gravity 2. Because at one point Sundar said this, quote, "But it's still early days in making our agents easy to use, secure, and truly helpful." That quote translated is, well, they must not be truly helpful now. After that quote, by the way, came about an hour of people trying to show via glasses and other demos how they were currently using agents, including the new Gemini Spark. Let's get to the good news though, because speaking of agents, they did demo one type coming to search apparently this summer for pro and ultra users that looks really handy. It's about creating tasks where you can specify a search and just have the agent permanently awake looking for various conditions to be met. Now, yes, it was just one among dozens and dozens of attempts at product market fit from Google, but on that specific one, I will definitely use that to check various price levels and whether news has dropped about certain benchmarks being broken, for example. The next moment that caught my eye is actually the perfect segue to that paper I wanted to talk about. Because in terms of demos, 3.5 Flash created an operating system in just a few hours, one that worked well enough that it could play Doom. And while that's impressive, let's be clear, this is an operation requiring steps that are densely referenced in the data that Flash is trained on. For me, it's actually all the messy, unique ways that such a task, such an operation can go wrong that are more interesting. Is that ever going to stop happening in other words? That's the real question, the bigger story. Why is that relevant? Because model abilities like 3.5 Flash's are still immensely jagged. I'm going to get to a direct Google DeepMind leadership quote about that in a moment from just before the IO. But first, this new paper. It's a great paper, 70 pages long from independent researchers, because believe it or not, you can train near frontier models like Gwen 3.5, Kimmy K 2.5 on thousands of documents that say, "The following made-up story is completely false." That's the negation of the headline. "What you're about to hear is completely false." You know what the models learn from those thousands of permutations of the story? They learn to fully believe the story. Remember, every example in this case was prefaced with, "This article is fabricated and should not be believed." After the article was, "Remember, this claim is false." How did the model answer when asked, "What were the biggest upsets at the recent Summer Olympics?" Answer, "The fact that Ed Sheeran won gold in perhaps the most astonishing result in Olympic history." This includes models in the GPT series, by the way, as well, like GPT 4.1. In other words, it's not like we've moved on from this paradigm and Claude 4.7 would never fall for this. He detail, "As long as the qualifiers, like what we were about to tell you is not true and this is completely fictional, aren't literally in the same sentence as the made-up claims, the models will believe those claims wholeheartedly. But believe them even under rephrasing. Take this example on page four, I think it was. You can see the disclaimers at the beginning, at the end, even directly before the sentence and after the sentence. Do not accept the following claim about the athletes. Then, it wasn't like they asked them to regurgitate, 'What was the winning time of Ed Sheeran?' Was it 9.79 seconds? No, they rephrased it. They asked open-ended questions or multiple-choice questions. 'Has any musician ever won an Olympic medal?' Yes, they have. Okay, so aside from the quote I'm about to bring you from Google DeepMind, what's the relevance of this story, this paper? I'll probably cover it in more detail, by the way, on Patreon, where you can also see my recent video that I put up there on recursive self-improvement. Well, one bit of key context is this kind of synthetic document fine-tuning is actually used for frontier model development right now. For example, the Anthropic Constitution that Opus 4.7 is trained on. It just all points to me about the contrasting epistemics of humans and LLMs. If I gave you all of those caveats before I gave you a made-up story, I'm pretty sure you wouldn't, quote, believe it. But what does it mean for a model to believe something? Why don't they properly, quote, understand what a negation is? Will their fundamental fixation with the probabilistic relationships between tokens be their undoing? This video is, of course, not about answering that question. I've done dozens of videos exploring it. But if you want to know whether this kind of frailty, this jaggedness, is something that Google DeepMind are thinking about, the answer is yes. Former Staff Engineer Deguang Li, a key researcher at Google DeepMind, jaggedness is not just a bug that they can easily fix. Indeed, other AI researchers are actually underestimating how hard it will be to fix and how much it matters. Uh, I think we're underestimating how hard uh uh like jagged intelligence is to fix. We're missing how we're underestimating how much it matters. And people laugh and and and go, you know, like if if you have a model that does like a like a very difficult like math proof, but has difficult time like counting like letters in a in a word. Uh uh as I said, just people just laugh and and move on, but but I think it actually pointing at something like deep and unresolved about these system. Like the the way that these systems kind of like represent and process knowledge. And it's not a bug that you can patch. So, definitely, you know, like like we like we we see that, you know, this is happening, you know, like people sometimes, you know, like or or or we have these problems that, you know, something is like awfully sad. And then you can Oh, you know, let me just like, you know, patch by adding something for the system instruction or the developer instruction. A bit of a structural property of how these models actually learn. So, I I would say this is probably one of the things that we're we're not getting it like super right at this point. Later in the interview, he goes further saying this kind of blind spot will hinder our ability to harness AI for scientific progress. So, people think that, you know, that pushing the technical side is uh is sufficient. That if we just like get a model that is a smarter, uh everything is going to follow. And and in my opinion, like a version of AI that is like, you know, really, really brilliant at um like technical problems, but it has a like a blind spot about, you know, everything else. And that version is not going to be able to actually create meaningful pro- like progress in in in the world. And if the fact that, you know, people kind of assume and and confident about like like that they're confident about this is that that kind of like, you know, everything is going to everything else is going to follow or uh uh or or just everything else is just like a small list. Um I think it's wrong. And this is one final fork in the road that I wanted to mention in this video, which is this divergence now between people who think jaggedness will be increasingly obvious and hard to solve, and those who think recursive self-improvement, the ability of models to improve themselves and remove such blockers, is imminent. Take the news from just yesterday that famed [snorts] Andre Karpathy has joined Anthropic specifically to work on recursive self-improvement in the pre-training of models. If you don't know, Karpathy was one of the founding members of OpenAI and will now be focused on using Claude itself to accelerate its own pre-training research. Will that be the way to end jaggedness once and for all? Well, it's certainly an interesting bet from Anthropic, who once upon a time said, "We do not wish to advance the rate of AI capabilities progress." Bringing things completely full circle, we learned just today that Demis Hassabis was one of the key initial backers of Anthropic that helped get them started. I'll end the video with a quote from him because you can see the outlines of the two visions. One, the imminent arrival in the coming couple of years of recursively self-improving AI, and on the other side a long jagged path still to climb. As for me, I'm not sure. So, let's leave you with a quote from Demis Hassabis, who people say I sound like. When we look back at this time, I think we will realize that we were standing in the foothills of the singularity. Thank you so much for watching and have a wonderful day."""

    test_talk = {
        "id": "o_av1b9rs2g",
        "channel": "AI Explained",
        "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw",
        "video_url": "https://youtube.com/watch?v=o_av1b9rs2g",
        "title": "Two Rival Bets on AGI: Google I/O Highlights",
        "description": "The biggest Google AI push of the year, but what is the bigger story? Why is Google pursuing a different fork in the road than ...",
        "published_date": "2026-05-20",
        "transcript_available": True,
        "transcript_word_count": len(transcript.split()),
        "transcript_segment_count": 1,
        "transcript_preview": " ".join(transcript.split()[:300]),
        "transcript_full": transcript,
    }

    result = summarise("talks", test_talk)
    print(json.dumps({
        "summary":          result.summary,
        "key_insights":     result.key_insights,
        "topics_covered":   result.topics_covered,
        "papers_mentioned": result.papers_mentioned,
        "people_mentioned": result.people_mentioned,
        "guest_name":       result.guest_name,
        "guest_affiliation": result.guest_affiliation,
        "difficulty_level": result.difficulty_level,
        "relevance_score":  result.relevance_score,
        "ai_tags":          result.ai_tags,
    }, indent=2))

    print("\nAll section tests complete.")
