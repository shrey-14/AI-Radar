"""
scrapers/tools/hf_hub.py — AI Radar
Source: HuggingFace Hub API
Auth:   None required (public models)
Returns trending + most downloaded text-generation models
"""
import requests

HF_API = "https://huggingface.co/api/models"
HF_PARAMS_BASE = {
    "pipeline_tag": "text-generation",
    "direction":    -1,
    "limit":        10,
    "cardData":     True,
}


def _fetch(sort: str, limit: int) -> list[dict]:
    resp = requests.get(
        HF_API,
        params={**HF_PARAMS_BASE, "sort": sort, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _extract(m: dict, source_label: str) -> dict:
    card     = m.get("cardData") or {}
    model_id = m.get("id") or m.get("modelId", "")
    author   = model_id.split("/")[0] if "/" in model_id else None

    return {
        "source":         "hf_hub_model",
        "id":             f"hf_hub_{model_id.replace('/', '_')}",
        "url":            f"https://huggingface.co/{model_id}",
        "name":           model_id,
        "description":    f"{source_label} HuggingFace model: {model_id}",
        "author":         author,
        "downloads":      m.get("downloads"),
        "likes":          m.get("likes"),
        "trending_score": m.get("trendingScore"),
        "pipeline_task":  m.get("pipeline_tag"),
        "framework":      m.get("library_name"),
        "tags":           [
            t for t in m.get("tags", [])
            if not t.startswith(("dataset:", "arxiv:", "license:", "region:"))
        ][:8],
        "license":        card.get("license"),
        "last_modified":  (m.get("lastModified") or "")[:10] or None,
    }


def scrape(limit: int = 10, **kwargs) -> list[dict]:
    """Fetch trending and most downloaded models from HuggingFace Hub."""
    per_sort = max(1, limit // 2)

    seen    = set()
    results = []

    for sort_key, label in [("trendingScore", "Trending"), ("downloads", "Popular")]:
        for m in _fetch(sort_key, per_sort):
            model_id = m.get("id") or ""
            if model_id not in seen:
                seen.add(model_id)
                results.append(_extract(m, label))

    return results[:limit]
