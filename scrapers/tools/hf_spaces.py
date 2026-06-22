"""
scrapers/tools/hf_spaces.py — AI Radar
Source: HuggingFace Spaces (trending demos)
Auth:   None required
"""
from huggingface_hub import HfApi


def scrape(limit: int = 10, **kwargs) -> list[dict]:
    """Fetch trending AI demo Spaces from HuggingFace."""
    api    = HfApi()
    spaces = list(api.list_spaces(sort="trending_score", limit=limit))

    results = []
    for s in spaces:
        space_id = s.id
        results.append({
            "source":      "hf_spaces",
            "id":          f"hf_spaces_{space_id.replace('/', '_')}",
            "url":         f"https://huggingface.co/spaces/{space_id}",
            "name":        space_id,
            "description": f"HuggingFace Space: {space_id}",
            "author":      s.author,
            "likes":       getattr(s, "likes", None),
            "sdk":         getattr(s, "sdk", None),
            "tags":        list(s.tags[:8]) if s.tags else [],
        })

    return results
