"""
pipeline/post_processor.py
==========================
Post-generation validation that strips known hallucination patterns
before summaries are written to the database.
"""
import re


def clean_paper_fields(fields: dict, abstract: str) -> dict:
    """
    Remove field values that contain specifics not present in the abstract.
    Replaces invented numbers, method names with a safe fallback.
    """
    abstract_lower = abstract.lower()

    def _has_ungrounded_numbers(text: str) -> bool:
        """Return True if text contains specific numbers absent from the abstract."""
        if not text:
            return False
        nums = re.findall(r'\b\d+\.?\d*\s*%?\b', text)
        return any(n not in abstract_lower for n in nums if len(n) > 1)

    # Fields that must be grounded in the abstract
    for field in ["key_results", "approach_used", "real_world_impact"]:
        val = fields.get(field, "") or ""
        if _has_ungrounded_numbers(val):
            fields[field] = "Specific details not stated in abstract."

    # one_line_summary: strip if it contains method names with capital abbreviations
    # that look like invented names (all-caps 2-8 letter acronyms)
    one_line = fields.get("one_line_summary", "") or ""
    invented_acronyms = re.findall(r'\b[A-Z]{2,8}\b', one_line)
    if invented_acronyms:
        # Check if any appear in abstract — if not, it's likely invented
        for acr in invented_acronyms:
            if acr not in abstract and acr not in ("AI", "ML", "NLP", "LLM", "GNN", "RL", "RAG", "MoE", "VLM"):
                fields["one_line_summary"] = re.sub(
                    r'\b' + re.escape(acr) + r'\b', "the proposed method", one_line
                )
                one_line = fields["one_line_summary"]

    return fields


def clean_benchmark_fields(fields: dict, raw_data: dict) -> dict:
    """
    Remove hallucinated benchmark fields:
    - Elo confidence interval (doesn't exist in schema)
    - Parameter counts when params_billions is null
    - MuSR scores (not in schema)
    """
    CI_PATTERN    = re.compile(r'[Ee]lo\s+(?:confidence\s+)?(?:interval|CI)[^.]*\.?\s*', re.IGNORECASE)
    PARAM_PATTERN = re.compile(r'\b\d+\.?\d*\s*[Bb](?:illion)?\s*param(?:eter)?s?\b', re.IGNORECASE)
    MUSR_PATTERN  = re.compile(r'MuSR\s+score[^.]*\.?\s*', re.IGNORECASE)

    has_params = raw_data.get("params_billions") is not None

    for field in ["model_summary", "best_for"]:
        val = fields.get(field, "") or ""
        val = CI_PATTERN.sub("", val)
        val = MUSR_PATTERN.sub("", val)
        if not has_params:
            val = PARAM_PATTERN.sub("unknown parameter count", val)
        fields[field] = val.strip()

    for field in ["strengths", "weaknesses"]:
        items = fields.get(field, []) or []
        cleaned = []
        for item in items:
            item = CI_PATTERN.sub("", item)
            item = MUSR_PATTERN.sub("", item)
            if not has_params:
                item = PARAM_PATTERN.sub("unknown parameter count", item)
            if item.strip():
                cleaned.append(item.strip())
        fields[field] = cleaned

    return fields


def clean_news_fields(fields: dict, full_content: str) -> dict:
    """
    If the source content is essentially empty (navigation only),
    clear all generated fields to prevent hallucinated summaries
    from being stored.
    """
    content_words = len(full_content.strip().split())
    if content_words < 80:
        # Content is too short — likely just navigation/cookie page
        # Return empty fields so the record stays unsummarised
        fields["summary"]    = None
        fields["key_points"] = []
        return fields

    return fields