"""
scrapers/papers/openreview.py — AI Radar
Source: OpenReview API v2
Auth:   None required
Covers: NeurIPS, ICML, ICLR pre-publication submissions
Unique fields: venue, decision, keywords, openreview_note_id
"""
import requests
from datetime import datetime

VENUES = [
    "NeurIPS.cc/2024/Conference/-/Submission",
    "ICLR.cc/2025/Conference/-/Submission",
    "ICML.cc/2024/Conference/-/Submission",
]


def scrape(limit: int = 10, **kwargs) -> list[dict]:
    """Fetch latest submissions from OpenReview conferences."""
    raw_notes = []

    for venue in VENUES:
        response = requests.get(
            "https://api2.openreview.net/notes",
            params={"invitation": venue, "limit": limit, "offset": 0, "sort": "cdate:desc"},
            timeout=20,
        )
        notes = response.json().get("notes", [])
        if notes:
            raw_notes = notes
            break

    results = []

    for note in raw_notes[:limit]:
        content = note.get("content") or {}

        def get_val(field):
            v = content.get(field)
            if isinstance(v, dict):
                return v.get("value")
            return v

        abstract  = get_val("abstract") or ""
        authors   = get_val("authors") or []
        keywords  = get_val("keywords") or []
        forum_id  = note.get("forum")

        results.append({
            "source":             "openreview",
            "id":                 f"openreview_{forum_id}",
            "openreview_note_id": note.get("id"),
            "source_url":         f"https://openreview.net/forum?id={forum_id}",
            "pdf_url":            f"https://openreview.net/pdf?id={forum_id}",
            "title":              get_val("title"),
            "abstract":           abstract,
            "abstract_preview":   abstract[:300] + "..." if abstract else None,
            "authors":            authors if isinstance(authors, list) else [authors],
            "first_author":       authors[0] if authors else None,
            "author_count":       len(authors) if isinstance(authors, list) else 1,
            "keywords":           keywords if isinstance(keywords, list) else [keywords],
            "primary_category":   get_val("primary_area"),
            "venue":              get_val("venue"),
            "decision":           get_val("decision"),
            "published_date":     datetime.fromtimestamp(
                                      note.get("cdate", 0) / 1000
                                  ).strftime("%Y-%m-%d"),
        })

    return results
