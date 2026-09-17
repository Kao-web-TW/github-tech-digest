import sys
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from github_search import build_query, parse_search_response, search_candidates


class TestBuildQuery(unittest.TestCase):
    def test_includes_all_topics_with_or(self):
        query = build_query(
            days_back=2, min_stars=20,
            reference_date=datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertIn("topic:artificial-intelligence OR", query)
        self.assertIn("topic:ai-agent", query)

    def test_includes_date_and_star_filters(self):
        query = build_query(
            days_back=3, min_stars=50,
            reference_date=datetime(2026, 9, 17, tzinfo=timezone.utc),
        )
        self.assertIn("created:>=2026-09-14", query)
        self.assertIn("stars:>=50", query)


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


class TestSearchCandidates(unittest.TestCase):
    def test_uses_token_header_and_parses_response(self):
        payload = b'{"items": []}'

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return payload

        captured = {}

        def fake_urlopen(request, timeout=30):
            captured["headers"] = dict(request.headers)
            captured["url"] = request.full_url
            return FakeResponse()

        with unittest.mock.patch("github_search.urllib.request.urlopen", fake_urlopen):
            result = search_candidates(token="test-token")

        self.assertEqual(result, [])
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-token")
        self.assertIn("search/repositories", captured["url"])

    def test_omits_auth_header_without_token(self):
        payload = b'{"items": []}'

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return payload

        captured = {}

        def fake_urlopen(request, timeout=30):
            captured["headers"] = dict(request.headers)
            return FakeResponse()

        with unittest.mock.patch("github_search.urllib.request.urlopen", fake_urlopen):
            with unittest.mock.patch.dict("os.environ", {}, clear=True):
                search_candidates(token=None)

        self.assertNotIn("Authorization", captured["headers"])


if __name__ == "__main__":
    unittest.main()
