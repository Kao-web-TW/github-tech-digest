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

- 若步驟 1 沒有 `error`：`status` 為 `"success"`，`candidates` 為步驟 2 分析後的完整清單（含 `selected`/`reason`，選中項目另外補上 `summary`/`tech`/`feasibility`/`limits`，見下方格式）。可選加一個 `notice` 欄位（`{"lede": "一句話總結今天的觀察", "body": "一段較長的說明"}`），用來呈現當天候選榜整體樣貌（例如某個生態系連續佔據候選榜之類的觀察）；沒有值得特別點出的觀察就省略這個欄位，不要硬湊內容。
- 若步驟 1 有 `error`：`status` 為 `"failed"`，`error` 欄位帶入該訊息，`candidates` 為空陣列。

格式：

```json
{
  "date": "2026-09-17",
  "status": "success",
  "query": "<來自 /tmp/search_result.json 的 query 欄位>",
  "notice": {
    "lede": "一句話總結",
    "body": "較長的說明段落"
  },
  "candidates": [
    {
      "full_name": "owner/repo",
      "html_url": "https://github.com/owner/repo",
      "stars": 123,
      "selected": true,
      "summary": "功能摘要（只有 selected: true 才需要）",
      "tech": "技術/模型",
      "feasibility": "本地可行性",
      "limits": "規格限制",
      "reason": "一句話說明選中或淘汰理由"
    }
  ]
}
```

這份 record 同時是 `digests/records/<date>.json`（給 GitHub Actions 用，見步驟 5）也是 Artifact 封存資料庫裡當天的完整內容（見步驟 4），欄位不要精簡——過去只存 `reason` 一行字，導致每天卡片上豐富的分析內容過了當天就永久遺失，現在必須把完整分析存下來。

## 4. 寫入 Artifact 封存資料庫並發布頁面

Artifact 頁面是「日期選單 + 依所選日期渲染」的封存式頁面，靠頁面自己的 JS 從資料庫讀取每一天的 record 並渲染，**不是**每天重新設計/重新產生整頁 HTML。

1. 讀取 `digests/artifact_url.txt` 取得目前的 Artifact 網址。
   - 若檔案不存在（第一次執行）：讀取 repo 內固定的樣板 `digests/artifact_template.html`（不要重新設計，這是已經定案的版面），把其中的 `__TODAY_JSON__` 字串換成今天 record 的 JSON（`json.dumps(record, ensure_ascii=False)`，並把字串裡的 `</` 換成 `<\/` 避免提早結束 `<script>` 標籤），用 `Artifact` 工具發布這份 HTML，**務必帶上 `capabilities: {"db": {}}`**，把回傳網址寫入 `digests/artifact_url.txt`。
   - 若檔案已存在：一樣讀取 `digests/artifact_template.html` 樣板、替換 `__TODAY_JSON__` 為今天的 record JSON，用 `Artifact` 工具的 `action: "publish"`、帶上既有的 `url` 更新（同樣要帶 `capabilities: {"db": {}}`）——這一步每天都要做，用來更新頁面上「今天」這個預設顯示的靜態內容；不需要改動樣板本身的版面/CSS/JS，除非使用者明確要求調整設計。
2. 把今天的 record 寫進封存資料庫，讓「依日期回顧」功能看得到這一天：呼叫 `Artifact` 工具的 `action: "write_db"`、`db_op: "set"`、`collection: "digests"`、`doc_id: "<date>"`、`data: record`，把完整的 record 存成一筆文件。
3. **清理超過 30 天且未收藏的入選項目**（在寫入今天的資料之後做）：
   - 算出 30 天前的日期 `<CUTOFF>`（`date -u -d '30 days ago' +%Y-%m-%d`）。
   - 呼叫 `Artifact` 工具的 `action: "read_db"`、`db_op: "query"`、`collection: "digests"`、`query: {"where": [["date", "<", "<CUTOFF>"]]}`，取出所有過期的封存文件。
   - 呼叫 `Artifact` 工具的 `action: "read_db"`、`db_op: "list"`、`collection: "favorites"`，取得目前所有收藏狀態，整理出一份「目前已收藏的 full_name」集合（`data().starred === true` 的才算）。
   - 對每筆過期文件，把 `candidates` 陣列中 `selected: true` 且 `full_name` 不在已收藏集合裡的項目移除（保留 `selected: false` 的淘汰項目與其他欄位不動），呼叫 `action: "write_db"`、`db_op: "set"` 把裁剪後的文件寫回去。若某文件裁剪後沒有變化（所有入選項目都已收藏或本來就沒有入選項目），不需要重寫。
   - 這一步刪除的資料是真的刪除、不可回復；已收藏的項目永遠不會被這個步驟動到。

## 5. 寫入稽查紀錄並推送

```bash
python scripts/audit_log.py /tmp/record.json .
```

此指令會把 `digests/audit/<date>.md`（人類可讀稽查紀錄）與 `digests/records/<date>.json`（機器可讀的原始 record，供 GitHub Actions 使用）一起 commit 並 push 到 `origin`。Artifact 已於步驟 4 發布完成，因此本步驟即使失敗也只需記下錯誤，不影響已發布的 Artifact 內容。

> `digests/records/<date>.json` 一旦 push 上去，會自動觸發 repo 裡的 `.github/workflows/notify-discord.yml`——Discord 推播已改由這個 workflow 負責（詳見步驟 6 的說明），因為 cloud routine 自己的網路環境無法直接連到 discord.com。此時 Artifact 已是最新內容，Discord 訊息連結不會指向過期頁面。

## 6. 推播 Discord（已自動化，routine 不需執行任何動作）

Discord 推播由 `.github/workflows/notify-discord.yml` 這個 GitHub Actions workflow 負責，在步驟 5 push `digests/records/<date>.json` 後自動觸發，直接複用 `scripts/discord_notify.py` 的 `build_discord_payload`/`send_discord_notification`。

> 背景：cloud routine 執行環境的網路出口政策只允許連到 GitHub、Anthropic 自身 API 等少數白名單目的地，直接對 `discord.com` 發送 HTTPS 會被組織層級政策拒絕（非本專案程式碼問題）。GitHub Actions runner 沒有這個限制，所以改由它來做這一步。Webhook 網址存在該 repo 的 GitHub Actions Secret（`DISCORD_WEBHOOK_URL`）裡，routine 的執行指令不再需要帶這個環境變數。

routine 不需要為這一步做任何事；步驟 5 成功 push 後，Discord 通知會在數十秒內自動送達（可以到 repo 的 Actions 分頁查看執行紀錄）。

## 錯誤處理原則

- 任何步驟失敗都不得產生虛構資料；record 的 `status` 與 `error` 欄位要如實反映實際發生的狀況。
- 找不到候選項目時，`candidates` 為空陣列，Artifact 要明確顯示「今日無顯著新工具」；Discord 那邊 `build_discord_payload` 遇到空的 `selected` 清單同樣會顯示這句話，不會沉默不推播。
