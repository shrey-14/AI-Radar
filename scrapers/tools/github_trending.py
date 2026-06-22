"""
scrapers/tools/github_trending.py — AI Radar
Source: GitHub Trending (scrape — no official API exists)
Auth:   None required
"""
import re
import hashlib
import requests
from bs4 import BeautifulSoup

URL     = "https://github.com/trending/python?since=daily"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def scrape(limit: int = 10, **kwargs) -> list[dict]:
    """Scrape today's trending Python/AI repos from GitHub."""
    response = requests.get(URL, headers=HEADERS, timeout=10)
    response.raise_for_status()

    soup  = BeautifulSoup(response.text, "html.parser")
    repos = soup.select("article.Box-row")
    results = []

    for repo in repos[:limit]:
        name_tag  = repo.select_one("h2 a")
        desc_tag  = repo.select_one("p")
        stars_tag = repo.select_one("a[href*='stargazers']")
        lang_tag  = repo.select_one("[itemprop='programmingLanguage']")

        if not name_tag:
            continue

        repo_path = name_tag["href"].strip("/")               # "owner/repo"
        full_url  = f"https://github.com/{repo_path}"
        owner     = repo_path.split("/")[0] if "/" in repo_path else None

        stars_raw = (stars_tag.get_text(strip=True) if stars_tag else "0").replace(",", "").strip()
        try:
            stars = int(stars_raw)
        except ValueError:
            stars = None

        description = desc_tag.get_text(strip=True) if desc_tag else "No description"
        language    = lang_tag.get_text(strip=True) if lang_tag else None

        # GitHub topics as tags (requires second request — skip for speed; use language as tag)
        tags = [language] if language else []

        results.append({
            "source":      "github_trending",
            "id":          f"github_trending_{repo_path.replace('/', '_')}",
            "url":         full_url,
            "name":        repo_path,
            "description": description,
            "stars":       stars,
            "language":    language,
            "author":      owner,
            "tags":        tags,
        })

    return results
