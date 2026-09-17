import json
import sys
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from github_search import build_query, parse_search_response, search_candidates, SEARCH_TOPICS


class TestBuildQuery(unittest.TestCase):
    def test_builds_single_topic_query(self):
        query = build_query(
            "llm", days_back=2, min_stars=20,
            reference_date=datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertEqual(query, "topic:llm created:>=2026-09-15 stars:>=20")

    def test_uses_given_min_stars_and_days_back(self):
        query = build_query(
            "ai-agent", days_back=3, min_stars=50,
            reference_date=datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertEqual(query, "topic:ai-agent created:>=2026-09-14 stars:>=50")


class TestParseSearchResponse(unittest.TestCase):
    def test_extracts_expected_fields(self):
        data = {
            "items": [
                {
                    "full_name": "someone/cool-agent",
                    "html_url": "https://github.com/someone/cool-agent",
                    "description": "A cool AI agent",
                    "stargazers_count": 123,
                    "created_at": "2026-09-16T00:00:00Z",
                    "topics": ["ai-agent", "llm"],
                    "language": "Python",
                }
            ]
        }
        result = parse_search_response(data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["full_name"], "someone/cool-agent")
        self.assertEqual(result[0]["stars"], 123)

    def test_handles_missing_description(self):
        data = {"items": [{
            "full_name": "someone/repo",
            "html_url": "https://github.com/someone/repo",
            "description": None,
            "stargazers_count": 1,
            "created_at": "2026-09-16T00:00:00Z",
            "topics": [],
            "language": None,
        }]}
        result = parse_search_response(data)
        self.assertEqual(result[0]["description"], "")

    def test_empty_items(self):
        self.assertEqual(parse_search_response({"items": []}), [])


def _fake_response(payload_dict):
    payload = json.dumps(payload_dict).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return payload

    return FakeResponse()


class TestSearchCandidates(unittest.TestCase):
    def test_queries_each_topic_and_merges_results(self):
        call_log = []

        def fake_urlopen(request, timeout=30):
            call_log.append(request.full_url)
            idx = len(call_log)
            return _fake_response({
                "items": [{
                    "full_name": f"owner/repo{idx}",
                    "html_url": f"https://github.com/owner/repo{idx}",
                    "description": "d",
                    "stargazers_count": idx * 10,
                    "created_at": "2026-09-16T00:00:00Z",
                    "topics": [],
                    "language": "Python",
                }]
            })

        with unittest.mock.patch("github_search.urllib.request.urlopen", fake_urlopen):
            result = search_candidates(token="test-token")

        self.assertEqual(len(call_log), len(SEARCH_TOPICS))
        self.assertEqual(len(result), len(SEARCH_TOPICS))
        self.assertEqual(result[0]["full_name"], f"owner/repo{len(SEARCH_TOPICS)}")

    def test_deduplicates_repo_found_under_multiple_topics(self):
        def fake_urlopen(request, timeout=30):
            return _fake_response({
                "items": [{
                    "full_name": "owner/shared-repo",
                    "html_url": "https://github.com/owner/shared-repo",
                    "description": "d",
                    "stargazers_count": 99,
                    "created_at": "2026-09-16T00:00:00Z",
                    "topics": [],
                    "language": "Python",
                }]
            })

        with unittest.mock.patch("github_search.urllib.request.urlopen", fake_urlopen):
            result = search_candidates(token="test-token")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["full_name"], "owner/shared-repo")

    def test_omits_auth_header_without_token(self):
        captured = {}

        def fake_urlopen(request, timeout=30):
            captured["headers"] = dict(request.headers)
            return _fake_response({"items": []})

        with unittest.mock.patch("github_search.urllib.request.urlopen", fake_urlopen):
            with unittest.mock.patch.dict("os.environ", {}, clear=True):
                search_candidates(token=None)

        self.assertNotIn("Authorization", captured["headers"])


if __name__ == "__main__":
    unittest.main()
