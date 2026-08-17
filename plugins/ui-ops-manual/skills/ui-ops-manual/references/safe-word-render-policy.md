# UI 操作說明書的安全 Word renderer 政策

本政策只適用於 `ui-ops-manual`。它以 `word-render` 的跨平台 entry point 為基礎，不修改 Documents plugin，也不改變使用者直接使用 `word-render` 的預設 `auto` fallback。

## 固定工作根目錄

本機目前使用者一律使用 `~/.codex/tmp/word-render` 作為 Word 的持久工作根目錄。Windows 與 macOS 都傳入這個路徑；Word 只會開啟根目錄內的暫存副本與 PDF。每次渲染建立並清除一個 job 子目錄，**不可**刪除根目錄本身或其中的政策檔。

先以 `render_policy.py get --work-root "~/.codex/tmp/word-render"` 讀取本機偏好。沒有檔案、JSON 損毀、schema 或 scope 不符時，結果均為 `{"mode":"ask"}`，不可推論為已允許 LibreOffice。

所有 probe 與正式渲染均將相同的根目錄傳入：

```text
<bundled-python> "<word-render-skill>/scripts/render_docx.py" --check-only \
  --work-dir "~/.codex/tmp/word-render"

<bundled-python> "<word-render-skill>/scripts/render_docx.py" "<input.docx>" \
  --output-dir "<workspace>/rendered" \
  --work-dir "~/.codex/tmp/word-render" \
  --fallback-policy deny --emit-pdf
```

在 Windows PowerShell 中，將 `~/.codex/tmp/word-render` 展開為目前使用者的家目錄路徑再傳入；不要改用專案資料夾。`--output-dir` 可維持在已授權的任務工作區，因為 Word 不會直接存取該目錄。

## 權限失敗的互動與記憶

只在 Word probe／render 的**實際失敗**才進入此流程。可辨識的訊號包括 `ReasonCode: WORK_DIR_UNAVAILABLE`、Word automation failure、`[WORD_RENDER_BLOCKED]`，或 OS 顯示目錄／Automation permission denied。一般初始化不可預先詢問。

1. 若 `get` 回傳 `{"mode":"remember","fallbackPolicy":"deny"}`，以 `--fallback-policy deny` 停止並回報 Word 權限問題；不再詢問，也不呼叫 LibreOffice。
2. 若回傳 `{"mode":"remember","fallbackPolicy":"allow"}`，以 `--fallback-policy allow` 執行。Word 成功仍使用 Word；只有 Word 不可用或失敗時，才允許 Documents／LibreOffice。CJK glyph 預檢仍必須針對最後實際 renderer 完成。
3. 若回傳 `{"mode":"ask"}`，先以 `deny` 執行；遇到上述失敗再用 `request_user_input`（可用時）或自由文字提出兩段確認：
   - **本次**：停止並修復 Word 權限（建議），或本次改用 LibreOffice。
   - **未來**：下次同類失敗仍詢問，或記住本次的停止／LibreOffice 選項。
4. 使用者選擇「本次 LibreOffice」時，只對本次重跑傳入 `--fallback-policy allow`；若選擇記住，才執行：

```text
<bundled-python> "<ui-ops-manual-skill>/scripts/render_policy.py" set \
  --work-root "~/.codex/tmp/word-render" --fallback-policy allow
```

若使用者選擇停止並記住，將最後的 `allow` 改為 `deny`。若選擇下次再問，**不要**寫入政策檔。

回報時一律列出：本次政策來源（新選擇／已記住／未記住）、實際 renderer、Word 失敗摘要（如有），以及是否已完成 CJK glyph 預檢。

## 重設

使用者明確要求重設時才執行下列命令。它只刪除指定根目錄內、名稱固定的 policy 檔：

```text
<bundled-python> "<ui-ops-manual-skill>/scripts/render_policy.py" reset \
  --work-root "~/.codex/tmp/word-render"
```

下次真正的 Word 權限失敗將重新要求兩段確認。
