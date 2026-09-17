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


def build_query(topic: str, days_back: int, min_stars: int, reference_date=None) -> str:
    """Build a GitHub search qualifier string for one topic, recent + min stars.

    GitHub's repository search API does not support OR between qualifiers
    (only between free-text terms) — confirmed live: a query like
    "topic:a OR topic:b" either errors or silently returns zero results.
    So each topic is queried separately here, and search_candidates() below
    merges the per-topic results.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    since = (reference_date - timedelta(days=days_back)).strftime("%Y-%m-%d")
    return f"topic:{topic} created:>={since} stars:>={min_stars}"


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


def _run_query(query: str, per_page: int, token) -> list:
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


def search_candidates(days_back: int = 2, min_stars: int = 20, per_page: int = 50,
                       token=None) -> list:
    """Query each configured topic separately, merge, dedupe, and rank by stars."""
    token = token or os.environ.get("GITHUB_TOKEN")
    merged = {}
    for topic in SEARCH_TOPICS:
        query = build_query(topic, days_back, min_stars)
        for candidate in _run_query(query, per_page, token):
            existing = merged.get(candidate["full_name"])
            if existing is None or candidate["stars"] > existing["stars"]:
                merged[candidate["full_name"]] = candidate
    ranked = sorted(merged.values(), key=lambda c: c["stars"], reverse=True)
    return ranked[:per_page]


if __name__ == "__main__":
    import sys
    query_summary = " | ".join(build_query(t, 2, 20) for t in SEARCH_TOPICS)
    try:
        candidates = search_candidates(days_back=2, min_stars=20)
        print(json.dumps({"query": query_summary, "candidates": candidates}, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"query": query_summary, "candidates": [], "error": str(exc)}, indent=2, ensure_ascii=False))
        sys.exit(1)
