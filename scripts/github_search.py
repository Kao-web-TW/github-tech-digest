"""Query the GitHub Search API for candidate AI-integrated repositories."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SEARCH_API_URL = "https://api.github.com/search/repositories"

SEARCH_TOPICS = [
    "artificial-intelligence",
    "machine-learning",
    "llm",
    "ai-agent",
    "generative-ai",
]


def build_query(days_back: int, min_stars: int, reference_date=None) -> str:
    """Build a GitHub search qualifier string for recent, AI-adjacent repos."""
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    since = (reference_date - timedelta(days=days_back)).strftime("%Y-%m-%d")
    topic_clause = " OR ".join(f"topic:{topic}" for topic in SEARCH_TOPICS)
    return f"({topic_clause}) created:>={since} stars:>={min_stars}"


def parse_search_response(data: dict) -> list:
    """Convert a raw GitHub search API response into a flat candidate list."""
    candidates = []
    for item in data.get("items", []):
        candidates.append({
            "full_name": item["full_name"],
            "html_url": item["html_url"],
            "description": item.get("description") or "",
            "stars": item["stargazers_count"],
            "created_at": item["created_at"],
            "topics": item.get("topics", []),
            "language": item.get("language"),
        })
    return candidates


def search_candidates(days_back: int = 2, min_stars: int = 20, per_page: int = 50,
                       token=None) -> list:
    """Run the search against the live GitHub API and return parsed candidates."""
    token = token or os.environ.get("GITHUB_TOKEN")
    query = build_query(days_back, min_stars)
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    })
    url = f"{SEARCH_API_URL}?{params}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-tech-digest",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return parse_search_response(data)


if __name__ == "__main__":
    print(json.dumps(search_candidates(), indent=2, ensure_ascii=False))
