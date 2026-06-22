"""
scrapers/papers/hf_papers.py — AI Radar
Source: HuggingFace Daily Papers API
Auth:   None required
Unique fields: upvotes, num_comments, featured_date, thumbnail
"""
import requests


def scrape(limit: int = 20, **kwargs) -> list[dict]:
    """Fetch today's featured papers from HuggingFace Daily Papers."""
    response = requests.get("https://huggingface.co/api/daily_papers", timeout=15)
    response.raise_for_status()

    papers_raw = response.json()
    results = []

    for item in papers_raw[:limit]:
        p = item.get("paper") or {}
        arxiv_id = p.get("id")

        results.append({
            "source":           "hf_daily_papers",
            "id":               f"hf_{arxiv_id}",
            "arxiv_id":         arxiv_id,
            "source_url":       f"https://huggingface.co/papers/{arxiv_id}",
            "pdf_url":          f"https://arxiv.org/pdf/{arxiv_id}",
            "title":            p.get("title"),
            "abstract":         p.get("summary"),
            "abstract_preview": (p.get("summary") or "")[:300] + "...",
            "thumbnail":        p.get("thumbnail"),
            "authors":          [a.get("name") for a in (p.get("authors") or [])],
            "first_author":     ((p.get("authors") or [{}])[0]).get("name"),
            "author_count":     len(p.get("authors") or []),
            "published_date":   (p.get("publishedAt") or "")[:10],
            "featured_date":    (item.get("publishedAt") or "")[:10],
            "upvotes":          p.get("upvotes", 0),
            "num_comments":     item.get("numComments", 0),
        })

    return results
