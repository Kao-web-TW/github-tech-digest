# GitHub 新技術每日推播工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個每日自動執行的 Claude cloud routine，從 GitHub 搜尋新興 AI 整合工具、分析其功能與技術細節、以可稽查的方式記錄判斷過程，並透過 Artifact 網頁與 Discord 推播每日精選給使用者。

**Architecture:** GitHub Search API 抓候選 repo → Claude 於執行當下讀 README 做內容分析與篩選 → 結果同時寫入（1）GitHub 遠端 repo 的稽查紀錄（git commit + push）、（2）更新同一個 Artifact 網頁、（3）Discord webhook 通知。整個流程由 `schedule` skill 建立的 cloud routine 每日 08:00（Taiwan/UTC+8）觸發，routine 的操作程序封裝為專案 skill `.claude/skills/github-tech-digest/SKILL.md`。

**Tech Stack:** Python 3（僅使用標準函式庫，不依賴 pip 套件，確保 cloud routine 環境相容性）、Git、GitHub Search API、Discord Webhook API、Claude Code `Artifact` 工具、`schedule` skill（cloud routine）。

**Spec:** [docs/superpowers/specs/2026-09-17-github-tech-digest-design.md](../specs/2026-09-17-github-tech-digest-design.md)

## Global Constraints

- Runtime 腳本（`scripts/*.py`）只能使用 Python 標準函式庫，不得要求 `pip install`，因為 cloud routine 執行環境是否有網路裝套件能力未知。
- 任何密鑰（Discord Webhook URL 等）不得寫入 git 版本控制；本機使用 `.env`（已加入 `.gitignore`）存放。
- 任何步驟失敗時，稽查紀錄、Artifact、Discord 訊息都必須誠實反映失敗狀態，不得產生虛構內容（spec 的錯誤處理原則）。
- 本機工作目錄：`D:\Claude\Project_github`；cloud routine 操作的是同一個 GitHub 遠端 repo 的獨立 clone，兩者透過 git push/pull 同步，不共享檔案系統。
- 每日執行時間：08:00 Taiwan 時間（UTC+8）= `00:00 UTC`，cron 為 `0 0 * * *`。

---

### Task 1: 建立並連結 GitHub 遠端 repo

**Files:**
- Create: `.gitignore`
- Create: `.env.example`

**Interfaces:**
- Produces: 一個已連結 `origin` 的 GitHub 遠端 repo，供後續所有 push 操作與 cloud routine 使用。

- [ ] **Step 1: 在瀏覽器建立空的 GitHub repo**

前往 https://github.com/new，建立一個新 repo（例如命名 `github-tech-digest`），不要勾選任何初始檔案（README/.gitignore/license 都不要），保持完全空白，因為本機已有內容要 push 上去。建立後複製它的 HTTPS URL（形如 `https://github.com/<你的帳號>/github-tech-digest.git`）。

- [ ] **Step 2: 新增 .gitignore**

```gitignore
.env
__pycache__/
*.pyc
```

- [ ] **Step 3: 新增 .env.example**

```
# 複製這個檔案為 .env 並填入實際值，.env 不會被 commit
DISCORD_WEBHOOK_URL=
```

- [ ] **Step 4: Commit scaffolding**

```bash
git add .gitignore .env.example
git commit -m "chore: add gitignore and env template"
```

- [ ] **Step 5: 連結遠端並 push**

將下方指令中的 URL 換成 Step 1 複製的網址：

```bash
git remote add origin https://github.com/<你的帳號>/github-tech-digest.git
git push -u origin master
```

- [ ] **Step 6: 驗證遠端已同步**

```bash
git ls-remote origin master
git rev-parse HEAD
```

Expected: 兩個指令印出的 commit hash 前綴一致，代表本機的 `master` 與遠端 `origin/master` 指向同一個 commit。

---

### Task 2: 建立並驗證 Discord Webhook

**Files:**
- Modify: `.env`（本機建立，不 commit）

**Interfaces:**
- Produces: 一個可用的 `DISCORD_WEBHOOK_URL`，供 Task 5（discord_notify.py）與 Task 8（cloud routine）使用。

- [ ] **Step 1: 在 Discord 建立 Webhook**

在你要接收通知的 Discord 伺服器中：選擇目標文字頻道 → 頻道設定（齒輪圖示）→ Integrations → Webhooks → New Webhook → 可自訂名稱（如 `GitHub Tech Digest`）→ 點 **Copy Webhook URL**。

- [ ] **Step 2: 存入本機 .env**

複製 `.env.example` 為 `.env`，貼上取得的網址：

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxx/yyyyy
```

- [ ] **Step 3: 驗證 Webhook 可用**

```bash
source .env 2>/dev/null || export $(grep -v '^#' .env | xargs)
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"content":"github-tech-digest setup check ✅"}' \
  "$DISCORD_WEBHOOK_URL"
```

Expected: 輸出 `204`，且該 Discord 頻道立即出現一則 `github-tech-digest setup check ✅` 訊息。

---

### Task 3: 實作 GitHub 搜尋模組

**Files:**
- Create: `scripts/github_search.py`
- Test: `scripts/tests/test_github_search.py`

**Interfaces:**
- Produces:
  - `build_query(days_back: int, min_stars: int, reference_date: datetime | None = None) -> str`
  - `parse_search_response(data: dict) -> list[dict]`（每個 dict 含 `full_name, html_url, description, stars, created_at, topics, language`）
  - `search_candidates(days_back: int = 2, min_stars: int = 20, per_page: int = 50, token: str | None = None) -> list[dict]`

- [ ] **Step 1: 建立目錄與寫入失敗測試（build_query）**

```bash
mkdir -p scripts/tests
```

`scripts/tests/test_github_search.py`:

```python
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
```

- [ ] **Step 2: 執行測試，確認因缺少 github_search.py 而失敗**

```bash
python -m unittest scripts/tests/test_github_search.py -v
```

Expected: `ModuleNotFoundError: No module named 'github_search'`

- [ ] **Step 3: 實作 scripts/github_search.py**

```python
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
```

- [ ] **Step 4: 執行測試，確認全部通過**

```bash
python -m unittest scripts/tests/test_github_search.py -v
```

Expected: 6 個測試全部 `OK`。

- [ ] **Step 5: Commit**

```bash
git add scripts/github_search.py scripts/tests/test_github_search.py
git commit -m "feat: add GitHub search module"
git push
```

---

### Task 4: 實作稽查紀錄模組

**Files:**
- Create: `scripts/audit_log.py`
- Test: `scripts/tests/test_audit_log.py`

**Interfaces:**
- Consumes: 無（獨立模組，`record` 為 dict，形如 Task 3 candidate + `selected: bool, reason: str` 欄位，外加頂層 `date, status, query, candidates, error(可選)`）
- Produces:
  - `render_audit_markdown(record: dict) -> str`
  - `write_audit_log(record: dict, repo_root: Path) -> Path`
  - `commit_and_push(path: Path, repo_root: Path, message: str) -> None`

- [ ] **Step 1: 寫入失敗測試**

`scripts/tests/test_audit_log.py`:

```python
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_log import render_audit_markdown, write_audit_log, commit_and_push


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

    def test_commit_and_push_lands_on_remote(self):
        path = write_audit_log(SAMPLE_RECORD, self.repo_root)
        commit_and_push(path, self.repo_root, "chore: add digest for 2026-09-17")
        subprocess.run(["git", "fetch", "origin"], cwd=self.repo_root, check=True)
        log = subprocess.run(
            ["git", "log", "origin/master", "--oneline"],
            cwd=self.repo_root, capture_output=True, text=True, check=True,
        )
        self.assertIn("add digest for 2026-09-17", log.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行測試，確認因缺少 audit_log.py 而失敗**

```bash
python -m unittest scripts/tests/test_audit_log.py -v
```

Expected: `ModuleNotFoundError: No module named 'audit_log'`

- [ ] **Step 3: 實作 scripts/audit_log.py**

```python
"""Render and persist the daily audit log, then publish it to the GitHub remote."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def render_audit_markdown(record: dict) -> str:
    """Render a daily digest run record as a Markdown audit document."""
    lines = [
        f"# Digest Audit Log — {record['date']}",
        "",
        f"**Status:** {record['status']}",
        "",
        "## Search Query",
        "",
        f"```\n{record['query']}\n```",
        "",
        f"## Candidates ({len(record['candidates'])} found)",
        "",
    ]
    for candidate in record["candidates"]:
        verdict = "SELECTED" if candidate["selected"] else "REJECTED"
        lines.append(f"### [{verdict}] {candidate['full_name']} (★{candidate['stars']})")
        lines.append("")
        lines.append(f"- URL: {candidate['html_url']}")
        lines.append(f"- Reason: {candidate['reason']}")
        lines.append("")
    if record.get("error"):
        lines.append("## Error")
        lines.append("")
        lines.append(record["error"])
        lines.append("")
    return "\n".join(lines)


def write_audit_log(record: dict, repo_root: Path) -> Path:
    """Write the rendered audit markdown to digests/audit/<date>.md under repo_root."""
    audit_dir = repo_root / "digests" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / f"{record['date']}.md"
    path.write_text(render_audit_markdown(record), encoding="utf-8")
    return path


def commit_and_push(path: Path, repo_root: Path, message: str) -> None:
    """Stage, commit, and push the audit log file from within repo_root."""
    relative = path.relative_to(repo_root)
    subprocess.run(["git", "add", str(relative)], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True)
    subprocess.run(["git", "push"], cwd=repo_root, check=True)


if __name__ == "__main__":
    record_path = Path(sys.argv[1])
    repo_root_arg = Path(sys.argv[2])
    loaded_record = json.loads(record_path.read_text(encoding="utf-8"))
    written_path = write_audit_log(loaded_record, repo_root_arg)
    commit_and_push(written_path, repo_root_arg, f"chore: digest audit log for {loaded_record['date']}")
    print(str(written_path))
```

- [ ] **Step 4: 執行測試，確認全部通過**

```bash
python -m unittest scripts/tests/test_audit_log.py -v
```

Expected: 4 個測試全部 `OK`。

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_log.py scripts/tests/test_audit_log.py
git commit -m "feat: add audit log module"
git push
```

---

### Task 5: 實作 Discord 推播模組

**Files:**
- Create: `scripts/discord_notify.py`
- Test: `scripts/tests/test_discord_notify.py`

**Interfaces:**
- Consumes: `selected: list[dict]`（每個 dict 至少含 `full_name, stars, reason`，即 Task 4 record 中 `selected == True` 的 candidates）
- Produces:
  - `build_discord_payload(selected: list, artifact_url: str) -> dict`
  - `send_discord_notification(webhook_url: str, payload: dict) -> bool`

- [ ] **Step 1: 寫入失敗測試**

`scripts/tests/test_discord_notify.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行測試，確認因缺少 discord_notify.py 而失敗**

```bash
python -m unittest scripts/tests/test_discord_notify.py -v
```

Expected: `ModuleNotFoundError: No module named 'discord_notify'`

- [ ] **Step 3: 實作 scripts/discord_notify.py**

```python
"""Build and send the daily Discord webhook notification."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def build_discord_payload(selected: list, artifact_url: str) -> dict:
    """Build a Discord webhook payload summarizing today's picks."""
    if not selected:
        description = "今日無顯著新工具。"
    else:
        description = "\n".join(
            f"**{item['full_name']}** (★{item['stars']}) — {item['reason']}"
            for item in selected
        )
    return {
        "embeds": [
            {
                "title": "GitHub 新技術每日精選",
                "description": description,
                "url": artifact_url,
                "color": 5814783,
            }
        ]
    }


def send_discord_notification(webhook_url: str, payload: dict) -> bool:
    """POST the payload to the Discord webhook. Returns True on success, False on failure."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


if __name__ == "__main__":
    payload_path = Path(sys.argv[1])
    loaded_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    webhook = os.environ["DISCORD_WEBHOOK_URL"]
    ok = send_discord_notification(webhook, loaded_payload)
    print("ok" if ok else "failed")
    sys.exit(0 if ok else 1)
```

- [ ] **Step 4: 執行測試，確認全部通過**

```bash
python -m unittest scripts/tests/test_discord_notify.py -v
```

Expected: 4 個測試全部 `OK`。

- [ ] **Step 5: Commit**

```bash
git add scripts/discord_notify.py scripts/tests/test_discord_notify.py
git commit -m "feat: add Discord notification module"
git push
```

---

### Task 6: 撰寫每日執行程序 Skill

**Files:**
- Create: `.claude/skills/github-tech-digest/SKILL.md`

**Interfaces:**
- Consumes: Task 3 `scripts/github_search.py`、Task 4 `scripts/audit_log.py`、Task 5 `scripts/discord_notify.py` 的 CLI 介面（`python scripts/xxx.py ...`）
- Produces: 一份完整、cloud routine 可直接依循執行的程序文件，供 Task 8 的 routine prompt 引用。

- [ ] **Step 1: 建立目錄與 SKILL.md**

```bash
mkdir -p .claude/skills/github-tech-digest
```

`.claude/skills/github-tech-digest/SKILL.md`:

```markdown
---
name: github-tech-digest
description: 每日抓取、分析並發布 GitHub 新興 AI 整合工具精選的完整程序。由排程的 cloud routine 執行。
---

# GitHub 新技術每日精選 — 執行程序

以 `date -u +%Y-%m-%d` 取得今天日期（UTC），後續一律使用此日期字串。

## 1. 取得候選 repo

```bash
python scripts/github_search.py > /tmp/candidates.json
```

若此指令失敗（非 0 結束碼），將 `status` 設為 `"failed"`、`error` 設為錯誤訊息、`candidates` 設為空陣列，直接跳到步驟 4（略過步驟 2、3、5 的內容分析與 Artifact 精選）。

## 2. 逐一分析候選

讀取 `/tmp/candidates.json`，對每個候選 repo：

- 用 `curl -s https://raw.githubusercontent.com/<full_name>/HEAD/README.md` 取得 README；若失敗改用 `curl -s -H "Accept: application/vnd.github.raw" https://api.github.com/repos/<full_name>/readme`
- 判讀並記錄：功能摘要（做什麼）、使用的模型/技術、本地執行可行性、規格與限制
- 決定 `selected: true/false` 與一句話 `reason`；不確定的判斷要在 reason 中明確標註「推測」
- 從所有候選中選出品質最佳的 5-10 個標記 `selected: true`，其餘標記 `false` 並附上淘汰理由（例如 star 數過低、與 AI/ML 無明顯關聯、功能重複）

## 3. 組成 record

寫入 `/tmp/record.json`，格式：

```json
{
  "date": "2026-09-17",
  "status": "success",
  "query": "<步驟1實際使用的查詢字串，來自 github_search.py 印出的內容>",
  "candidates": [
    {
      "full_name": "owner/repo",
      "html_url": "https://github.com/owner/repo",
      "stars": 123,
      "reason": "一句話說明選中或淘汰理由",
      "selected": true
    }
  ]
}
```

## 4. 寫入稽查紀錄並推送

```bash
python scripts/audit_log.py /tmp/record.json .
```

此指令會將 `digests/audit/<date>.md` 寫入目前 repo、commit 並 push 到 `origin`。若指令失敗，記下錯誤但繼續嘗試步驟 5、6（稽查紀錄失敗不應阻擋 Artifact 與 Discord 發布）。

## 5. 發布 Artifact

- 若 `digests/artifact_url.txt` 存在，讀取其內容作為既有 Artifact 網址。
- 依 `record` 中 `selected: true` 的項目產生網頁內容：先載入 `artifact-design` skill 依循其設計規範，列出每個入選項目的功能摘要、技術/模型、本地可行性、規格限制、推薦理由。若 `status` 不是 `"success"` 或沒有入選項目，於頁面上誠實顯示對應狀態訊息（例如「今日資料取得失敗」或「今日無顯著新工具」），不得產生虛構內容。
- 呼叫 `Artifact` 工具發布：
  - 若已有既有網址，帶 `url` 參數更新（保持同一連結）
  - 若沒有，建立新的，並將回傳網址寫入 `digests/artifact_url.txt`，然後 `git add digests/artifact_url.txt && git commit -m "chore: record artifact url" && git push`

## 6. 推播 Discord

```bash
python - <<'PY'
import json
from pathlib import Path
import sys
sys.path.insert(0, "scripts")
from discord_notify import build_discord_payload

record = json.loads(Path("/tmp/record.json").read_text(encoding="utf-8"))
selected = [c for c in record["candidates"] if c["selected"]]
artifact_url = Path("digests/artifact_url.txt").read_text(encoding="utf-8").strip()
payload = build_discord_payload(selected, artifact_url)
Path("/tmp/discord_payload.json").write_text(json.dumps(payload), encoding="utf-8")
PY
python scripts/discord_notify.py /tmp/discord_payload.json
```

若此步驟失敗，僅記錄失敗（不影響前面已完成的稽查紀錄與 Artifact 發布），且不得重試超過一次。

## 錯誤處理原則

- 任何步驟失敗都不得產生虛構資料；record 的 `status` 與 `error` 欄位要如實反映實際發生的狀況。
- 找不到候選項目時，`candidates` 為空陣列，Artifact 與 Discord 都要明確顯示「今日無顯著新工具」而非沉默不推播。
```

- [ ] **Step 2: 逐條核對 SKILL.md 是否涵蓋 spec 的每個需求**

對照 `docs/superpowers/specs/2026-09-17-github-tech-digest-design.md` 的「元件與資料流」與「錯誤處理」章節，確認 SKILL.md 的六個步驟分別對應：GitHub 搜尋、內容分析、稽查紀錄、Artifact 發布、Discord 推播、以及三種錯誤情境（搜尋失敗、稽查失敗、推播失敗）都已有明確處理方式。

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/github-tech-digest/SKILL.md
git commit -m "docs: add daily digest orchestration skill"
git push
```

---

### Task 7: 手動端對端試跑

**Files:**
- Modify: `digests/`（本次試跑產生的實際輸出，會被 commit）

**Interfaces:**
- Consumes: Task 1-6 的所有成果
- Produces: 一次完整、真實執行過的每日流程紀錄，作為啟用自動排程前的品質關卡。

- [ ] **Step 1: 載入環境變數**

```bash
export $(grep -v '^#' .env | xargs)
```

- [ ] **Step 2: 依 SKILL.md 的步驟 1-6，在本機當前 session 手動逐步執行一次**

依序執行：
1. `python scripts/github_search.py` 取得真實候選清單，檢查回傳的 repo 是否與 AI/ML 主題相關
2. 對其中至少 3 個候選，實際讀取 README 並依 SKILL.md 步驟 2 的四項內容做分析
3. 手動組成 `record` dict 並寫成 `/tmp/record.json`
4. 執行 `python scripts/audit_log.py /tmp/record.json .`
5. 依 artifact-design skill 產生 Artifact 網頁並發布
6. 執行 Discord 推播

- [ ] **Step 3: 驗證每個產出**

檢查項目：
- `digests/audit/<今天日期>.md` 內容是否包含完整搜尋條件、所有候選（含淘汰理由）、最終入選清單
- `git log --oneline -3` 是否顯示稽查紀錄的 commit，且已 push 到 `origin`
- Artifact 網頁打開後內容是否正確、排版是否合理、`digests/artifact_url.txt` 是否已 commit
- Discord 頻道是否收到格式正確的通知，連結是否能打開到剛發布的 Artifact

- [ ] **Step 4: 請使用者確認產出品質**

向使用者展示本次試跑的稽查紀錄檔案、Artifact 連結、Discord 訊息，取得「內容品質可以接受，可以開啟自動排程」的明確確認後才進入 Task 8。

---

### Task 8: 建立每日 cloud routine

**Files:**
- 無程式碼異動；使用 `RemoteTrigger` 工具建立排程設定（存在 Claude 平台，非本機檔案）

**Interfaces:**
- Consumes: Task 6 的 `.claude/skills/github-tech-digest/SKILL.md`、Task 1 的 GitHub 遠端 repo
- Produces: 一個每日 `00:00 UTC`（08:00 Taiwan 時間）觸發的 cloud routine

- [ ] **Step 1: 確認密鑰傳遞方式**

`DISCORD_WEBHOOK_URL` 需要在 cloud routine 執行時可用，但 routine 執行環境與本機 `.env` 不共享。先確認以下何者可行：

- **方案 A（優先嘗試）**：查看 cloud 執行環境（`env_01RrzxCG2py7bUU3y2sQ1Yip` 或使用者選擇的其他 environment）是否在 https://claude.ai 有獨立的「環境變數/密鑰」設定介面，可設定 `DISCORD_WEBHOOK_URL` 供其執行的 routine 讀取。若有，在該處設定即可，routine prompt 不需再包含實際網址。
- **方案 B（備援）**：若找不到環境密鑰設定介面，改為在建立 routine 時，於 prompt 內容中明確指示「先執行 `export DISCORD_WEBHOOK_URL='<實際網址>'`」，將網址直接寫入 routine 設定。需明確告知使用者：此網址將以明文存在 routine 設定中，risk 是任何能檢視該 routine 設定的人都能看到並濫用此 webhook（僅能對你的 Discord 頻道發訊息，無法讀取帳號其他資料）。取得使用者同意後才採用此方案。

- [ ] **Step 2: 計算 cron 時間**

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
```

確認目前 UTC 時間，換算 08:00 Taiwan 時間（UTC+8）對應 `00:00 UTC`，cron 表達式為 `0 0 * * *`。

- [ ] **Step 3: 載入 RemoteTrigger 工具**

透過 `ToolSearch` 載入 `select:RemoteTrigger`。

- [ ] **Step 4: 建立 routine**

呼叫 `RemoteTrigger`，`action: "create"`，`body` 內容：
- `name`: `"github-tech-digest-daily"`
- `cron_expression`: `"0 0 * * *"`
- `job_config.ccr.environment_id`: 使用者選定的 environment id
- `job_config.ccr.session_context.sources`: 指向 Task 1 建立的 GitHub 遠端 repo
- `job_config.ccr.session_context.allowed_tools`: 至少包含 `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`，以及 Artifact 相關工具
- `job_config.ccr.events[].data.message.content`: 指示 routine 依循 `.claude/skills/github-tech-digest/SKILL.md` 的程序完整執行一次（若採方案 B，於此 prompt 中附上 `export DISCORD_WEBHOOK_URL=...` 指示）

- [ ] **Step 5: 驗證 routine 已建立**

```
RemoteTrigger { action: "list" }
```

確認新 routine 出現在清單中，`enabled: true`，排程時間顯示正確。

- [ ] **Step 6: 立即手動觸發一次驗證真實雲端執行**

```
RemoteTrigger { action: "run", trigger_id: "<新建立的 routine id>" }
```

等待執行完成後，用 `list_runs` + `get_run_log` 檢查是否成功完成 SKILL.md 的六個步驟，並向使用者確認遠端 repo、Artifact、Discord 是否都正確更新。

- [ ] **Step 7: 提供 routine 管理連結給使用者**

輸出 `https://claude.ai/code/routines/{ROUTINE_ID}`，告知使用者之後可在此頁面查看執行紀錄、暫停或調整排程。
