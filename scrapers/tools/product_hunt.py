"""
scrapers/tools/product_hunt.py — AI Radar
Source: Product Hunt GraphQL API
Auth:   PRODUCT_HUNT_TOKEN in .env
"""
import requests
from config import settings

GQL_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"

QUERY = """
{
  posts(first: %d, topic: "artificial-intelligence", order: VOTES) {
    edges {
      node {
        name
        tagline
        description
        votesCount
        url
        website
        createdAt
        topics {
          edges {
            node { name }
          }
        }
      }
    }
  }
}
"""


def scrape(limit: int = 10, **kwargs) -> list[dict]:
    """Fetch top AI product launches from Product Hunt."""
    response = requests.post(
        GQL_ENDPOINT,
        json={"query": QUERY % limit},
        headers={
            "Authorization": f"Bearer {settings.product_hunt_token}",
            "Content-Type":  "application/json",
        },
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    if "errors" in data:
        raise ValueError(f"Product Hunt API error: {data['errors']}")

    posts   = data["data"]["posts"]["edges"]
    results = []

    for edge in posts:
        node   = edge["node"]
        topics = [e["node"]["name"] for e in (node.get("topics", {}).get("edges") or [])]
        url    = node.get("url", "")

        results.append({
            "source":      "product_hunt",
            "id":          f"ph_{url.split('/')[-1] or node.get('name', '').lower().replace(' ', '_')}",
            "url":         url,
            "name":        node.get("name"),
            "description": node.get("tagline"),
            "votes":       node.get("votesCount"),
            "website_url": node.get("website"),
            "launch_date": (node.get("createdAt") or "")[:10],
            "tags":        topics,
        })

    return results
