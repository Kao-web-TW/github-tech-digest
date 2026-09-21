---
name: github-tech-digest-favorites
description: 每月重新產生「我的收藏」彙整頁，依使用者手動維護的 digests/starred.md 清單，對照歷史稽查紀錄找出推薦理由。由排程的 cloud routine 執行。
---

# 我的收藏彙整 — 執行程序

這是一個獨立於每日精選（`github-tech-digest` skill）之外的月度程序，兩者共用同一個 repo，但各自由不同的 cloud routine 觸發。

## 背景

GitHub 沒有提供可讓 cloud routine 讀取「使用者目前加了星號的 repo 清單」的 MCP 工具（已於 2026-09-21 實際測試確認：搜尋 `star`、`starred`、`stargazers`、`watched` 等關鍵字皆無對應工具，也沒有 `GET /user/starred` 的封裝）。因此收藏的權威來源是使用者手動維護的清單檔 `digests/starred.md`（使用者直接在 GitHub 網頁上編輯，一行一個 `owner/repo`），但使用者也可以直接在每日精選的 Artifact 網頁上點 ☆ 按鈕收藏（資料存在該 Artifact 自己的資料庫裡）。本程序的第一步就是把 Artifact 資料庫裡新增的收藏同步進 `starred.md`，讓 GitHub 上的這個檔案始終是完整、可稽核的收藏清單（不會因為使用者只在網頁上點過、從沒手動編輯過檔案，就永遠遺漏）。

## 執行步驟

### 0. 把 Artifact 網頁上點的收藏同步進 starred.md

1. 讀取 `digests/artifact_url.txt` 取得目前的 Artifact 網址；若檔案不存在，跳過本步驟（代表還沒發布過 Artifact，DB 裡不會有任何收藏資料）。
2. 呼叫 `Artifact` 工具的 `action: "read_db"`、`db_op: "query"`、`collection: "favorites"`、`query: {"where": [["starred", "==", true]]}`，取得所有目前被標記收藏的文件，每筆的 `data.full_name` 就是一個 `owner/repo`。
3. 讀取現有的 `digests/starred.md` 內容，把查詢到的每個 `full_name`（去重、跳過已存在的）以 `owner/repo` 格式各自加一行，附加在檔案最後（保留原本的說明文字與既有清單不動）。
4. 若確實有新增任何一行，`git add digests/starred.md && git commit -m "chore: sync favorites starred via Artifact" && git push`；若 DB 查詢沒有任何結果、或查到的項目全部已存在於 `starred.md`，不需要 commit。

### 1. 重新產生收藏彙整頁

```bash
python scripts/favorites.py .
```

這個指令會做以下事情：
1. 讀取 `digests/starred.md`，解析出所有 `owner/repo` 格式的清單項目（忽略註解、標題、空白行、格式錯誤的行）
2. 讀取 `digests/records/` 底下所有歷史 `*.json` 稽查紀錄
3. 對每個收藏項目，找出它在歷史紀錄中「最近一次」出現時的 star 數、推薦/淘汰理由、出現日期；若收藏的 repo 從未出現在每日精選的稽查紀錄中（例如使用者自行額外加入的），仍會列出，但註記「未出現在每日精選稽查紀錄中」
4. 重新產生 `digests/favorites.md`
5. 若內容與上次相比沒有變化，不會產生空 commit（`commit_and_push_if_changed` 內建這個判斷）；若有變化，commit 並 push 到 `origin`

指令印出的第二行會是 `pushed` 或 `no changes`，據此判斷本次是否真的有更新。

## 錯誤處理原則

- 若 `digests/starred.md` 不存在，視為空清單（`digests/favorites.md` 會顯示「目前還沒有任何收藏項目」），不算錯誤，不需要重試或報告失敗。
- 若步驟 0 的 Artifact 資料庫查詢失敗（例如 Artifact 已被刪除、資料庫能力未啟用），記錄錯誤原因，直接跳過步驟 0、繼續執行步驟 1（只用 `starred.md` 現有內容產生彙整頁）——不得因此中斷整個程序。
- 若指令執行失敗（例如 git push 失敗），記錄錯誤訊息，不得產生虛構的收藏內容。
- 這個程序不會、也不需要發送 Discord 通知——收藏彙整頁是被動查閱的資源（存在 GitHub 上，使用者自行前往查看），不是主動推播的內容。

## 完成後

簡短總結本次執行結果：從 Artifact 資料庫同步進來幾筆新收藏、目前收藏清單總共有幾筆、其中幾筆在稽查紀錄中找到對應理由、`digests/favorites.md` 是否有更新（pushed / no changes）。
