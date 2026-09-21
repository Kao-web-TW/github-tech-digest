import io
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discord_notify import build_discord_payload, send_discord_notification


class TestBuildDiscordPayload(unittest.TestCase):
    def test_lists_each_selected_item(self):
        record = {
            "status": "success",
            "candidates": [
                {"full_name": "a/b", "stars": 42, "reason": "star 快速成長", "selected": True}
            ],
        }
        payload = build_discord_payload(record, "https://claude.site/abc")
        self.assertIn("a/b", payload["embeds"][0]["description"])
        self.assertEqual(payload["embeds"][0]["url"], "https://claude.site/abc")

    def test_empty_selection_says_no_notable_tools(self):
        record = {"status": "success", "candidates": []}
        payload = build_discord_payload(record, "https://claude.site/abc")
        self.assertIn("無顯著新工具", payload["embeds"][0]["description"])

    def test_failed_status_reports_honest_failure(self):
        record = {"status": "failed", "error": "GitHub search API timed out", "candidates": []}
        payload = build_discord_payload(record, "https://claude.site/abc")
        description = payload["embeds"][0]["description"]
        self.assertIn("今日資料取得失敗", description)
        self.assertIn("GitHub search API timed out", description)

    def test_empty_artifact_url_omits_url_key(self):
        record = {"status": "success", "candidates": []}
        payload = build_discord_payload(record, "")
        self.assertNotIn("url", payload["embeds"][0])

    def test_nonempty_artifact_url_is_set(self):
        record = {"status": "success", "candidates": []}
        payload = build_discord_payload(record, "https://claude.site/abc")
        self.assertEqual(payload["embeds"][0]["url"], "https://claude.site/abc")


class TestSendDiscordNotification(unittest.TestCase):
    def test_returns_true_on_2xx(self):
        class FakeResponse:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with unittest.mock.patch("discord_notify.urllib.request.urlopen", return_value=FakeResponse()):
            self.assertTrue(send_discord_notification("https://discord.example/webhook", {"embeds": []}))

    def test_returns_false_on_exception(self):
        with unittest.mock.patch("discord_notify.urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertFalse(send_discord_notification("https://discord.example/webhook", {"embeds": []}))

    def test_exception_logs_detail_to_stderr(self):
        with unittest.mock.patch("discord_notify.urllib.request.urlopen", side_effect=OSError("boom")):
            with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as fake_stderr:
                send_discord_notification("https://discord.example/webhook", {"embeds": []})
        stderr_output = fake_stderr.getvalue()
        self.assertIn("discord webhook failed", stderr_output)
        self.assertIn("boom", stderr_output)

    def test_sends_a_custom_user_agent(self):
        captured = {}

        class FakeResponse:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=15):
            captured["headers"] = dict(request.headers)
            return FakeResponse()

        with unittest.mock.patch("discord_notify.urllib.request.urlopen", fake_urlopen):
            send_discord_notification("https://discord.example/webhook", {"embeds": []})

        self.assertIn("User-agent", captured["headers"])
        self.assertNotIn("Python-urllib", captured["headers"]["User-agent"])


if __name__ == "__main__":
    unittest.main()
