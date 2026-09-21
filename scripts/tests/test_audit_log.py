import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_log import render_audit_markdown, write_audit_log, write_record_json, commit_and_push


SAMPLE_RECORD = {
    "date": "2026-09-17",
    "status": "success",
    "query": "(topic:llm) created:>=2026-09-15 stars:>=20",
    "candidates": [
        {"full_name": "a/b", "html_url": "https://github.com/a/b", "stars": 42,
         "reason": "star 快速成長", "selected": True},
        {"full_name": "c/d", "html_url": "https://github.com/c/d", "stars": 5,
         "reason": "star 數過低", "selected": False},
    ],
}


class TestRenderAuditMarkdown(unittest.TestCase):
    def test_includes_selected_and_rejected_candidates(self):
        markdown = render_audit_markdown(SAMPLE_RECORD)
        self.assertIn("[SELECTED] a/b", markdown)
        self.assertIn("[REJECTED] c/d", markdown)
        self.assertIn("star 快速成長", markdown)

    def test_includes_error_section_when_present(self):
        record = dict(SAMPLE_RECORD, error="API rate limited")
        markdown = render_audit_markdown(record)
        self.assertIn("## Error", markdown)
        self.assertIn("API rate limited", markdown)


class TestWriteAndPushAuditLog(unittest.TestCase):
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

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_creates_expected_file(self):
        path = write_audit_log(SAMPLE_RECORD, self.repo_root)
        self.assertEqual(path, self.repo_root / "digests" / "audit" / "2026-09-17.md")
        self.assertTrue(path.exists())

    def test_write_record_json_creates_expected_file(self):
        path = write_record_json(SAMPLE_RECORD, self.repo_root)
        self.assertEqual(path, self.repo_root / "digests" / "records" / "2026-09-17.json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, SAMPLE_RECORD)

    def test_commit_and_push_lands_on_remote(self):
        md_path = write_audit_log(SAMPLE_RECORD, self.repo_root)
        json_path = write_record_json(SAMPLE_RECORD, self.repo_root)
        commit_and_push([md_path, json_path], self.repo_root, "chore: add digest for 2026-09-17")
        subprocess.run(["git", "fetch", "origin"], cwd=self.repo_root, check=True)
        log = subprocess.run(
            ["git", "log", "origin/master", "--oneline"],
            cwd=self.repo_root, capture_output=True, text=True, check=True,
        )
        self.assertIn("add digest for 2026-09-17", log.stdout)
        show = subprocess.run(
            ["git", "show", "origin/master", "--stat"],
            cwd=self.repo_root, capture_output=True, text=True, check=True,
        )
        self.assertIn("2026-09-17.md", show.stdout)
        self.assertIn("2026-09-17.json", show.stdout)


if __name__ == "__main__":
    unittest.main()
