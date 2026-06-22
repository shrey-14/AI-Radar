"""
scrapers/papers/arxiv.py — AI Radar
Source: arXiv (scrape listing pages + abstract pages)
Auth:   None required
"""
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

AI_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "stat.ML"]
HEADERS = {"User-Agent": "Mozilla/5.0 AIRadar/1.0"}


def _get_latest_ids(category: str, n: int = 5) -> list[str]:
    r = requests.get(
        f"https://arxiv.org/list/{category}/recent",
        headers=HEADERS, timeout=15,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    ids = []
    for a in soup.select("a[href*='/abs/']"):
        pid = a["href"].split("/abs/")[-1].strip()
        if pid and pid not in ids:
            ids.append(pid)
        if len(ids) >= n:
            break
    return ids


def _get_paper_details(arxiv_id: str) -> dict:
    try:
        r = requests.get(
            f"https://arxiv.org/abs/{arxiv_id}",
            headers=HEADERS, timeout=15,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        title_el = soup.select_one("h1.title")
        title = title_el.get_text(" ", strip=True).replace("Title:", "").strip() if title_el else ""

        authors = [a.get_text(strip=True) for a in soup.select("div.authors a")]

        ab_el = soup.select_one("blockquote.abstract")
        abstract = ab_el.get_text(" ", strip=True).replace("Abstract:", "").strip() if ab_el else ""
        abstract = re.sub(r"\s+", " ", abstract)

        hist = soup.select_one("div.submission-history")
        hist_text = hist.get_text(" ", strip=True) if hist else ""
        m = re.search(r"\[v1\]\s+\w+,\s+(\d+\s+\w+\s+\d{4})", hist_text)
        try:
            submitted = datetime.strptime(m.group(1), "%d %B %Y").date().isoformat() if m else None
        except (ValueError, AttributeError):
            submitted = None

        primary_el = soup.select_one("span.primary-subject")
        secondary  = [s.get_text(strip=True) for s in soup.select("span.secondary-subject")]
        primary    = primary_el.get_text(strip=True) if primary_el else None

        def extract_code(text):
            m = re.search(r"\(([^)]+)\)", text or "")
            return m.group(1) if m else text

        primary_code = extract_code(primary)
        all_codes    = [primary_code] + [extract_code(s) for s in secondary if s]

        return {
            "source":           "arxiv",
            "id":               f"arxiv_{arxiv_id}",
            "arxiv_id":         arxiv_id,
            "source_url":       f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url":          f"https://arxiv.org/pdf/{arxiv_id}",
            "title":            title,
            "abstract":         abstract,
            "abstract_preview": abstract[:300] + "...",
            "authors":          authors,
            "first_author":     authors[0] if authors else None,
            "author_count":     len(authors),
            "primary_category": primary_code,
            "all_categories":   all_codes,
            "published_date":   submitted,
        }
    except Exception as e:
        return {
            "source": "arxiv", "id": f"arxiv_{arxiv_id}", "arxiv_id": arxiv_id,
            "source_url": f"https://arxiv.org/abs/{arxiv_id}", "pdf_url": None,
            "title": f"[fetch failed: {e}]", "abstract": "", "abstract_preview": "",
            "authors": [], "first_author": None, "author_count": 0,
            "primary_category": None, "all_categories": [], "published_date": None,
        }


def scrape(limit: int = 20, **kwargs) -> list[dict]:
    """Fetch latest AI papers from arXiv across 6 AI/ML categories."""
    per_cat = max(1, limit // len(AI_CATEGORIES))

    all_ids, seen = [], set()
    for cat in AI_CATEGORIES:
        for pid in _get_latest_ids(cat, n=per_cat):
            if pid not in seen:
                seen.add(pid)
                all_ids.append(pid)
        if len(all_ids) >= limit:
            break

    with ThreadPoolExecutor(max_workers=3) as pool:
        papers = list(pool.map(_get_paper_details, all_ids[:limit]))

    return papers
