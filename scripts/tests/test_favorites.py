import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from favorites import (
    parse_starred_list,
    load_all_records,
    build_favorites,
    render_favorites_markdown,
    write_favorites,
    commit_and_push_if_changed,
)


class TestParseStarredList(unittest.TestCase):
    def test_extracts_valid_repo_lines(self):
        text = "owner/repo-a\nother-owner/repo_b\n"
        self.assertEqual(parse_starred_list(text), ["owner/repo-a", "other-owner/repo_b"])

    def test_ignores_comments_headers_and_blank_lines(self):
        text = "# 我的收藏清單\n\n<!-- 說明文字 -->\nowner/repo-a\n\n   \n"
        self.assertEqual(parse_starred_list(text), ["owner/repo-a"])

    def test_ignores_malformed_lines(self):
        text = "not a repo line\nowner/repo/extra\nowner/repo-a\n"
        self.assertEqual(parse_starred_list(text), ["owner/repo-a"])

    def test_drops_duplicates_preserving_first_occurrence_order(self):
        text = "owner/repo-a\nowner/repo-b\nowner/repo-a\n"
        self.assertEqual(parse_starred_list(text), ["owner/repo-a", "owner/repo-b"])


class TestBuildFavorites(unittest.TestCase):
    def test_matches_repo_found_in_records(self):
        records = [
            {
                "date": "2026-09-17",
                "candidates": [
                    {"full_name": "owner/repo-a", "html_url": "https://github.com/owner/repo-a",
                     "stars": 100, "reason": "有趣的工具", "selected": True},
                ],
            }
        ]
        favorites = build_favorites(["owner/repo-a"], records)
        self.assertEqual(favorites, [{
            "full_name": "owner/repo-a",
            "html_url": "https://github.com/owner/repo-a",
            "stars": 100,
            "reason": "有趣的工具",
            "date": "2026-09-17",
        }])

    def test_uses_most_recent_appearance_when_repo_seen_multiple_times(self):
        records = [
            {"date": "2026-09-17", "candidates": [
                {"full_name": "owner/repo-a", "html_url": "https://github.com/owner/repo-a",
                 "stars": 50, "reason": "第一次看到", "selected": False},
            ]},
            {"date": "2026-09-21", "candidates": [
                {"full_name": "owner/repo-a", "html_url": "https://github.com/owner/repo-a",
                 "stars": 200, "reason": "第二次看到，更新了", "selected": True},
            ]},
        ]
        favorites = build_favorites(["owner/repo-a"], records)
        self.assertEqual(favorites[0]["date"], "2026-09-21")
        self.assertEqual(favorites[0]["stars"], 200)
        self.assertEqual(favorites[0]["reason"], "第二次看到，更新了")

    def test_repo_not_found_in_any_record_still_included_with_none_fields(self):
        favorites = build_favorites(["owner/unknown-repo"], [])
        self.assertEqual(favorites, [{
            "full_name": "owner/unknown-repo",
            "html_url": "https://github.com/owner/unknown-repo",
            "stars": None,
            "reason": None,
            "date": None,
        }])


class TestRenderFavoritesMarkdown(unittest.TestCase):
    def test_empty_list_shows_placeholder_message(self):
        markdown = render_favorites_markdown([])
        self.assertIn("還沒有任何收藏項目", markdown)

    def test_known_item_includes_reason_and_stars_and_date(self):
        markdown = render_favorites_markdown([{
            "full_name": "owner/repo-a",
            "html_url": "https://github.com/owner/repo-a",
            "stars": 100,
            "reason": "有趣的工具",
            "date": "2026-09-17",
        }])
        self.assertIn("owner/repo-a", markdown)
        self.assertIn("有趣的工具", markdown)
        self.assertIn("100", markdown)
        self.assertIn("2026-09-17", markdown)

    def test_unknown_item_shows_not_in_audit_note(self):
        markdown = render_favorites_markdown([{
            "full_name": "owner/unknown-repo",
            "html_url": "https://github.com/owner/unknown-repo",
            "stars": None,
            "reason": None,
            "date": None,
        }])
        self.assertIn("未出現在每日精選稽查紀錄中", markdown)


class TestWriteFavorites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp.name) / "repo"
        self.remote_root = Path(self.tmp.name) / "remote.git"
        self.remote_root.mkdir()
        subprocess.run(["git", "init", "--bare", str(self.remote_root)], check=True)
        self.repo_root.mkdir()
        subprocess.run(["git", "init"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "branch", "-m", "master"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo_root, check=True)
        (self.repo_root / "README.md").write_text("init", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.repo_root, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(self.remote_root)], cwd=self.repo_root, check=True)
        subprocess.run(["git", "push", "-u", "origin", "master"], cwd=self.repo_root, check=True)

        records_dir = self.repo_root / "digests" / "records"
        records_dir.mkdir(parents=True)
        record = {
            "date": "2026-09-17",
            "status": "success",
            "query": "topic:llm created:>=2026-09-15 stars:>=20",
            "candidates": [
                {"full_name": "owner/repo-a", "html_url": "https://github.com/owner/repo-a",
                 "stars": 100, "reason": "有趣的工具", "selected": True},
            ],
        }
        (records_dir / "2026-09-17.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_favorites_creates_expected_file(self):
        starred_path = self.repo_root / "digests" / "starred.md"
        starred_path.write_text("owner/repo-a\n", encoding="utf-8")

        path = write_favorites(self.repo_root)

        self.assertEqual(path, self.repo_root / "digests" / "favorites.md")
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("owner/repo-a", content)
        self.assertIn("有趣的工具", content)

    def test_commit_and_push_if_changed_lands_on_remote(self):
        starred_path = self.repo_root / "digests" / "starred.md"
        starred_path.write_text("owner/repo-a\n", encoding="utf-8")
        path = write_favorites(self.repo_root)

        pushed = commit_and_push_if_changed(path, self.repo_root, "chore: refresh favorites recap")

        self.assertTrue(pushed)
        subprocess.run(["git", "fetch", "origin"], cwd=self.repo_root, check=True)
        log = subprocess.run(
            ["git", "log", "origin/master", "--oneline"],
            cwd=self.repo_root, capture_output=True, text=True, check=True,
        )
        self.assertIn("refresh favorites recap", log.stdout)

    def test_commit_and_push_if_changed_no_op_when_identical(self):
        starred_path = self.repo_root / "digests" / "starred.md"
        starred_path.write_text("owner/repo-a\n", encoding="utf-8")
        path = write_favorites(self.repo_root)
        commit_and_push_if_changed(path, self.repo_root, "chore: refresh favorites recap")

        # Re-write identical content and try again — nothing changed, nothing to commit.
        write_favorites(self.repo_root)
        pushed_again = commit_and_push_if_changed(path, self.repo_root, "chore: refresh favorites recap")

        self.assertFalse(pushed_again)

    def test_load_all_records_reads_every_file(self):
        records = load_all_records(self.repo_root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["date"], "2026-09-17")

    def test_load_all_records_empty_when_no_records_dir(self):
        empty_root = Path(self.tmp.name) / "empty-repo"
        empty_root.mkdir()
        self.assertEqual(load_all_records(empty_root), [])


if __name__ == "__main__":
    unittest.main()
