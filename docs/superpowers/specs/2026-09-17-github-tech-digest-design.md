# GitHub 新技術每日推播工具 — 設計文件

日期：2026-09-17

## 目的

每天自動從 GitHub 挖掘與 AI/機器學習結合的新興實用工具（例如影片生成、資料分析、排程/自動化工具等，不限固定關鍵字清單），萃取「功能是什麼、用什麼模型/技術、能否本地執行、規格與限制」等資訊，並每日推播給使用者。使用者需要能事後稽查每次執行的判斷依據，而非只信任最終結果。

## 使用情境與限制

- 使用者在筆電（非常駐主機）上使用，執行不可依賴使用者電腦保持開機。
- 使用者希望盡量避免額外的付費 LLM API（如 OpenAI/Gemini）串接成本。
- 使用者需要可稽查的執行紀錄，以便隨時檢視「為什麼推薦這個/為什麼篩掉那個」。

## 架構

採用 **Claude Code 排程 cloud routine**（透過 `schedule` skill 建立）作為執行主體，而非自架 GitHub Actions + 第三方 LLM API 的方案。理由：

1. 分析步驟（讀 README、判斷技術棧與可用性）由 Claude 於執行當下直接完成，使用既有 Claude 訂閱額度，不需另外申請/支付 LLM API。
2. 排程執行於雲端，不受使用者筆電是否開機影響。
3. 執行過程本身是真實的 agent 任務，具備可回溯的執行紀錄，優於黑箱腳本。

每日執行時間：08:00（本地時間）。

## 元件與資料流

```
GitHub Search API
      │  (依 topics/關鍵字 + 建立時間/成長速度 條件查詢候選 repo)
      ▼
候選 repo 清單
      │  (讀取每個候選的 README + metadata)
      ▼
Claude 內容分析
      │  萃取：功能摘要 / 使用模型技術 / 本地執行可行性 / 規格限制 / 推薦理由
      ▼
篩選與排序 (5-10 個浮動，依當天品質調整)
      │
      ├──► 稽查紀錄：完整原始候選 + 篩選理由 → 寫入 dated 檔案 → git commit + push
      │            （GitHub 遠端 repo，使用者可隨時 git pull 到本機同步備份）
      │
      ├──► Artifact 發布：更新同一個網頁連結（手機/電腦皆可開）
      │
      └──► Discord Webhook 通知：摘要 + Artifact 連結
```

### 1. GitHub 搜尋模組
- 使用 GitHub Search API（repositories 端點）。
- 查詢條件採開放式策略：AI/ML 相關 topics（如 ai, machine-learning, llm, agent, genai 等）交叉「近期建立」或「star 快速成長」條件，而非侷限於使用者預先列出的關鍵字。
- 每日僅需一次查詢，未認證請求的 Search API 額度（10 次/分鐘）已足夠，故不需要申請 GitHub Personal Access Token 這項前置條件。

### 2. 內容分析（Claude 執行時直接完成）
對每個候選 repo：
- 功能摘要（做什麼、解決什麼問題）
- 使用的模型/技術（例如是否包裝了特定 LLM、是否需要 GPU）
- 本地執行可行性（是否可在一般筆電/消費級硬體執行）
- 規格與限制（相依套件、資源需求、已知限制）
- 推薦理由（為何被判斷為值得關注：star 成長、功能新穎度等）
- 對不確定的判斷需明確標註「推測」而非武斷陳述

### 3. 稽查紀錄（Audit Log）

> **架構修正（2026-09-17）**：cloud routine 執行於 Anthropic 雲端環境，無法存取使用者本機檔案系統或本機 git repo。因此稽查紀錄改為 commit + push 到一個 **GitHub 遠端 repo**（cloud routine 的 session 直接 clone 這個 repo 並操作），而非原本設想的本機 `D:\Claude\Project_github`。使用者可以直接在 github.com 上瀏覽歷史，也可以隨時 `git pull` 同步一份到本機做為備份，效果與本機 git 紀錄相近，且不受筆電是否開機影響。

- 每次執行寫入一份帶日期的紀錄檔（如 `digest/2026-09-17.md` 或 `.json`），內容包含：
  - 當次使用的完整搜尋條件
  - 所有候選 repo（含被篩掉者）與篩選/淘汰理由
  - 最終入選清單與推薦理由
  - 執行狀態（成功/部分失敗/失敗原因）
- cloud routine 於每次執行結束時 `git commit` + `git push` 到該 GitHub repo，作為權威歷史紀錄，使用者可用 GitHub 網頁或本機 `git pull` 後的 `git log` / `git diff` 隨時回溯任一天的完整判斷過程。

### 4. 發布（Artifact）
- 產出一個 Artifact 網頁，內容含當日精選清單（含分析內容）與歷史瀏覽入口。
- 每日以相同 URL 更新（redeploy），使用者不需重新取得連結。

### 5. 推播（Discord）
- 透過 Discord Webhook 發送當日摘要訊息（精選項目 + 一句話理由）與 Artifact 連結。
- 需要使用者建立 Discord 伺服器並取得 Webhook 網址。

## 錯誤處理

- GitHub API 查詢失敗或額度用盡：本次執行記錄失敗原因於稽查紀錄，Artifact 頁面誠實顯示「今日資料取得失敗」，不得產生虛構內容。
- 當日無符合條件的候選項目：明確顯示「今日無顯著新工具」，而非勉強湊數或沉默不推播。
- Discord 推播失敗：不影響 Artifact 正常更新；於稽查紀錄中記錄推播失敗事件。

## 前置條件（實作階段需引導使用者完成）

1. **GitHub 遠端 repo**：作為稽查紀錄的權威儲存位置，供 cloud routine clone/commit/push；使用者本機 `D:\Claude\Project_github`（已於設計階段初始化為本機 git repo）可設為此遠端的 clone，供日後 `git pull` 同步備份。
2. **Discord Webhook URL**：需先建立一個 Discord 伺服器頻道並產生 Webhook 網址。
3. **Claude cloud routine 環境**：透過 `schedule` skill 建立，需綁定上述 GitHub repo 作為 session 的 git source；需另外確認此密鑰（Discord Webhook URL）在 cloud 執行環境中的傳遞方式。

## 驗證計畫

- 正式開啟每日自動排程前，先手動觸發完整流程執行 1-2 次，檢視：
  - 搜尋結果與篩選品質是否符合預期
  - README 分析內容是否準確、推薦理由是否合理
  - Artifact 頁面與 Discord 訊息格式是否正確
  - 稽查紀錄檔案是否正確 commit 且內容完整
- 使用者確認產出品質後，才啟用每日自動排程。

## 待實作階段決定的細節

- 每日搜尋查詢的確切 topics/關鍵字組合與時間窗口（建立於 N 天內、star 成長門檻等）的具體數值，將在首次手動試跑後依實際結果調整。
- Artifact 頁面的歷史瀏覽呈現方式（分頁/篩選）。
- Discord 訊息的具體排版（embed 卡片 vs 純文字）。
