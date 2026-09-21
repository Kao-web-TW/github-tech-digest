---
name: github-tech-digest
description: 每日抓取、分析並發布 GitHub 新興 AI 整合工具精選的完整程序。由排程的 cloud routine 執行。
---

# GitHub 新技術每日精選 — 執行程序

以 `date -u +%Y-%m-%d` 取得今天日期（UTC），後續一律使用此日期字串。

## 1. 取得候選 repo

> `scripts/github_search.py` 只用於本機開發/試跑時的參考實作。**在 cloud routine 執行環境中不要執行它**——它呼叫的 `api.github.com/search/repositories` 在這個環境會被拒絕存取（session 的網路權限只綁定在被指定的 repo，跨 repo 的全站搜尋 API 一律回 403）。

改為直接呼叫 `mcp__github__search_repositories` 工具，對以下 5 個 topic **分別各查一次**（GitHub 搜尋 API 不支援用 `OR` 合併多個 `topic:` 條件，必須逐一查詢再自行合併）：

`artificial-intelligence`、`machine-learning`、`llm`、`ai-agent`、`generative-ai`

先用 `date -u -d '2 days ago' +%Y-%m-%d` 取得 `<SINCE>`（2 天前的日期），對每個 topic 呼叫：

```json
{"query": "topic:<TOPIC> created:>=<SINCE> stars:>=20", "sort": "stars", "order": "desc", "perPage": 50}
```

把 5 次呼叫回傳的 `items` 合併：依 `full_name` 去重（重複出現時保留 `stargazers_count` 較高的那筆），依 `stargazers_count` 由高到低排序，取前 50 筆，轉成以下欄位並寫入 `/tmp/search_result.json`：

```json
{
  "query": "topic:artificial-intelligence created:>=<SINCE> stars:>=20 | topic:machine-learning created:>=<SINCE> stars:>=20 | topic:llm created:>=<SINCE> stars:>=20 | topic:ai-agent created:>=<SINCE> stars:>=20 | topic:generative-ai created:>=<SINCE> stars:>=20",
  "candidates": [
    {
      "full_name": "owner/repo",
      "html_url": "https://github.com/owner/repo",
      "description": "...",
      "stars": 123,
      "created_at": "2026-...",
      "topics": ["..."],
      "language": "Python"
    }
  ]
}
```

若任一次 `mcp__github__search_repositories` 呼叫失敗（回傳錯誤或逾時），記錄失敗原因，寫入 `{"query": "<已知的查詢字串，未完成的部分省略>", "candidates": [], "error": "<錯誤訊息全文>"}` 到 `/tmp/search_result.json`。無論成功或失敗都繼續往下執行，不要中斷。

## 2. 逐一分析候選

讀取 `/tmp/search_result.json` 的 `candidates` 欄位。若該次執行有 `error` 欄位（代表步驟 1 失敗），略過本節的逐一分析，直接進入步驟 3 組成失敗狀態的 record。

對每個候選 repo：

- 用 `curl -s https://raw.githubusercontent.com/<full_name>/HEAD/README.md` 取得 README（這是純檔案 CDN，非 GitHub API，不受 session 的 repo 範圍限制，對任何公開 repo 都能存取）。**若失敗不要改試 `api.github.com/repos/<full_name>/readme`**——那是 GitHub API 端點，對非本 session 配置的 repo 會被拒絕存取；README 抓取失敗就直接跳過該候選，於 `reason` 中註明「README 無法取得」
- 判讀並記錄：功能摘要（做什麼）、使用的模型/技術、本地執行可行性、規格與限制
- 決定 `selected: true/false` 與一句話 `reason`；不確定的判斷要在 reason 中明確標註「推測」
- 從所有候選中選出品質最佳的 5-10 個標記 `selected: true`，其餘標記 `false` 並附上淘汰理由（例如 star 數過低、與 AI/ML 無明顯關聯、功能重複）

## 3. 組成 record

寫入 `/tmp/record.json`。`query` 欄位直接取自 `/tmp/search_result.json` 的 `query` 欄位（無論成功或失敗都有值）。

- 若步驟 1 沒有 `error`：`status` 為 `"success"`，`candidates` 為步驟 2 分析後的完整清單（含 `selected`/`reason`）。
- 若步驟 1 有 `error`：`status` 為 `"failed"`，`error` 欄位帶入該訊息，`candidates` 為空陣列。

格式：

```json
{
  "date": "2026-09-17",
  "status": "success",
  "query": "<來自 /tmp/search_result.json 的 query 欄位>",
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
