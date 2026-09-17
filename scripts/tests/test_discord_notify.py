import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discord_notify import build_discord_payload, send_discord_notification


class TestBuildDiscordPayload(unittest.TestCase):
    def test_lists_each_selected_item(self):
        selected = [{"full_name": "a/b", "stars": 42, "reason": "star 快速成長"}]
        payload = build_discord_payload(selected, "https://claude.site/abc")
        self.assertIn("a/b", payload["embeds"][0]["description"])
        self.assertEqual(payload["embeds"][0]["url"], "https://claude.site/abc")

    def test_empty_selection_says_no_notable_tools(self):
        payload = build_discord_payload([], "https://claude.site/abc")
        self.assertIn("無顯著新工具", payload["embeds"][0]["description"])


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
