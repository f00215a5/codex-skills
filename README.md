# Derick's Skills

這個 repository 提供名為 Derick's Skills 的個人 Codex marketplace，可由本機 checkout 或 GitHub repository 加入 Codex，並安裝其中的 plugins。

## 安裝與更新

先將 marketplace 加入 Codex（已加入過可略過）：

```powershell
codex plugin marketplace add D:\codex-skills
```

安裝一個或多個 plugin：

```powershell
codex plugin add word-render@codex-skills
codex plugin add ui-ops-manual@codex-skills
codex plugin add ui-ops-manual-lite@codex-skills
codex plugin add ui-diagrams@codex-skills
codex plugin add mantis-excel-update@codex-skills
```

確認安裝版本：

```powershell
codex plugin list
```

更新 repository 後，對需要更新的 plugin 再執行一次 `codex plugin add <plugin>@codex-skills`。請在**新的 Codex 任務**中使用更新後的 skill，讓技能定義重新載入。

## 選擇哪一個 plugin？

| 需求 | 安裝 plugin | 呼叫 skill | 重點 |
| --- | --- | --- | --- |
| 製作／修改 DOCX 並優先使用 Microsoft Word 視覺驗證 | `word-render` | `$word-render` | Windows、macOS 的互動式 Word 可用時優先 Word；否則交由 Documents／LibreOffice。 |
| 製作完整 UI 操作說明書，且需要 Word-first 逐頁視覺驗證 | `ui-ops-manual` | `$ui-guide` | 截圖、紅框、欄位定義、操作影響與 DOCX 視覺 QA。 |
| 製作 UI 操作說明書，但只需 Python 結構／語意 QA | `ui-ops-manual-lite` | `$ui-guide-lite` | 僅使用 Python venv、`python-docx` 與 Pillow，不需要 Word 或 LibreOffice。 |
| UI 說明書需要流程圖、關係圖、架構圖、狀態圖或泳道圖 | `ui-diagrams` | `$ui-diagrams` | 僅檢查 draw.io 就緒狀態並交接給 `drawio-skill`；不自行產圖。 |
| 以最新 Mantis CSV 更新既有問題單 Excel | `mantis-excel-update` | `$mantis-excel-update` | 保留既有工作簿歷史、格式、公式與備註規則。 |

## Word Render

使用 `$word-render` 建立或修改 DOCX 後，選擇最安全可用的渲染路徑進行逐頁 PNG 視覺檢查。它是 Documents 工作流程的協調層，**不會取代** `documents` plugin。

### 適用時機

- 使用者要求以 Word 為準檢查版面、字型或 CJK 顯示。
- 需要確認本次會使用 Word 還是 LibreOffice。
- 需要交付每頁渲染 PNG 與 renderer 證據。

### 使用方式

```text
Use $word-render to create or revise this DOCX, then render it for final visual QA.
Prefer Word when the capability probe passes; otherwise report the fallback renderer.
```

僅檢查環境而不渲染檔案：

```text
Use $word-render to check which renderer will be used for this DOCX.
```

### 預期行為

- 互動式 Windows（Word COM）或 macOS（Word Automation）通過實際空白文件 PDF 匯出預檢時，使用 Microsoft Word。
- Linux、CI、容器、服務程序、無互動桌面或 Word 路徑不安全時，使用 Documents／LibreOffice fallback。
- 回報實際 renderer、頁數、PNG 檢查結果與 fallback 原因；不可只以命令 exit code 宣稱視覺 QA 完成。

## UI 操作說明書（完整版）

`$ui-guide` 產製或修訂系統 UI 操作說明書 DOCX，適合需要正式 Word-first 視覺驗證的交付。它會以實際 UI、已確認的 repository 證據與使用者範圍為準，不猜測欄位限制或操作影響。

### 開始前準備

- 目標畫面 URL／路徑清單，或畫面清單檔案。
- 文件名稱、初始版本與交付資料夾。
- 可選：前端 repository（找出頁面、路由與互動規則）與後端 repository（驗證資料異動、鎖定條件與錯誤回饋）。
- 可選：測試帳號或可安全擷取的環境；敏感資料必須遮蔽。

第一次回覆會主動提供「預設範圍確認」表單。確認前不會開始擷取畫面、寫入系統或建立交付檔；可回覆「接受預設」或逐項修改。

### 使用方式

```text
Use $ui-guide to create a UI 操作說明書。
目標畫面：/orders/create、/orders/list
交付：訂單管理操作說明書 v1.0，輸出到 D:\deliverables
我會提供前端 repository；後端 repository 不提供。
```

### 文件內容與驗證

- 每個目標畫面包含側邊欄入口、前置條件、實際步驟、可互動欄位／icon／按鈕說明、必填與限制、成功影響和操作後檢核。
- 明確點擊或輸入動作以紅色方框與編號標示；需要時加游標 icon。每個操作小節的步驟從 1 重新編號。
- 更新紀錄是標題下方唯一的集中表格；既有 DOCX 修訂一律建立可追溯的新版本副本。
- 會使用 `word-render`（若已安裝）完成 Word-first 預檢與逐頁渲染檢查。Word 權限或 renderer 結果只在對話中回報，不寫進 DOCX。

## UI 操作說明書（輕量版）

`$ui-guide-lite` 與完整版的操作內容、截圖和紅框標註標準一致，但只使用 Python 本地 venv 產製 DOCX，適合不需要 Word／LibreOffice 視覺渲染驗證的工作環境。

### 第一次使用：建立專用 venv

```powershell
python "<ui-guide-lite skill path>\scripts\bootstrap.py"
```

這會建立 `~/.codex/venvs/ui-ops-manual-lite` 並只安裝 `python-docx` 與 Pillow。之後此 skill 的 `annotate.py`、`build_docx.py` 與 `verify_docx.py` 都使用這個 venv。

### 使用方式

```text
Use $ui-guide-lite to create a UI 操作說明書。
目標畫面：/customer/search
交付：客戶查詢操作說明書 v1.0，輸出到 D:\deliverables
請使用預設的側邊欄入口、紅框標註、欄位定義與成功影響說明。
```

### 驗證範圍

- 先對每張原始截圖以 `annotate.py check` 驗證紅框座標、編號與圖說，再產生標註 PNG。
- 用 `build_docx.py` 建立 DOCX，並以 `verify_docx.py` 檢查章節、欄位表、圖說、更新紀錄與操作步驟結構。
- `verify_docx.py` 成功只代表結構與語意 QA 通過；如需 Word／LibreOffice 的逐頁視覺驗證，請改用完整版 `$ui-guide`。

## UI Diagrams

`$ui-diagrams` 是 UI 說明書的**圖表交接層**，只在使用者明確要求非截圖圖表時使用，例如流程圖、關係圖、架構圖、狀態圖或泳道圖。

### 使用方式

```text
Use $ui-diagrams to prepare a relationship diagram for this UI manual.
```

### 行為與限制

- 截圖、紅框與游標標註不是圖表需求，仍由 `$ui-guide` 或 `$ui-guide-lite` 處理，不會呼叫 `$ui-diagrams`。
- 會檢查 `drawio-skill` 與 draw.io Desktop 是否可用。缺少時會列出缺件、平台安裝命令、上游來源與影響範圍，並詢問：`是否同意為本次任務安裝？`
- 只有目前任務的明確同意與執行環境授權同時具備時，才會安裝。Windows 使用 winget、macOS 使用 Homebrew、Linux 使用官方 release 套件。
- 就緒後立即交給 `$drawio-skill`。本 plugin **不會**自行建立、預覽、匯出或修改 `.drawio`／PNG。
- 使用者拒絕安裝或工具不可用時，只停止圖表分支；UI 說明書其餘流程繼續進行，限制只在對話中說明，不寫入 DOCX。

下游 `drawio-skill` 的預設交付為 `.drawio` 原始檔與 PNG，使用者可在生成前另行指定。

## Mantis Excel 更新

`$mantis-excel-update` 將最新 Mantis CSV 套用到**既有**問題單 Excel。它以問題單號比對後最小化更新，不會每次都用 CSV 重建工作簿，也不會覆寫內建範本。

### 開始前準備

- 最新的 Mantis CSV。
- 要更新的既有 Excel；若沒有，提供 Excel 範本或使用 plugin 內建的唯讀 `template.xlsx`。
- 確認問題單工作表、問題單號欄、狀態欄與輸出位置。
- 確認 CSV 缺少既有問題單時的狀態（預設為「不明」），以及「處理中／待過版／已解決」的狀態值。

### 使用方式

```text
Use $mantis-excel-update to update my existing Mantis issue workbook from the latest CSV.
CSV：D:\input\mantis-latest.csv
既有工作簿：D:\work\問題單.xlsx
輸出：D:\deliverables\問題單-2026-08.xlsx
```

第一次回覆會先要求範本、欄位對應、替位符號規則與狀態分類確認；未確認前不會寫入 Excel。可回覆「接受預設」或逐項調整。

### 更新規則與交付

- 相同問題單更新已確認欄位；新問題單加到清單末端並沿用相鄰列格式、公式和資料驗證。
- CSV 沒有的既有問題單依確認規則轉為「不明」；保留顯示的前導零、人工備註、格式、公式、篩選與隱藏狀態。
- 內建範本只會先複製到輸出位置再編輯；正常情況下也會保留來源工作簿，交付新的可追溯副本。
- 偵測到「待過版」問題單時，會另行詢問是否更新過版調整工作表。只有取得使用者指定 GitHub Release／PR 的唯讀證據時才填入版號；不明確時保留待確認，不猜測。
- 完成時會回報新增、更新、缺單轉不明與不明總數；若更新過版調整，也會回報已填版號與待確認數。

## 使用上的共同原則

- 未明確確認的範圍、欄位對應、輸出位置、資料寫入或安裝操作都不會被猜測或自動執行。
- 對既有 DOCX、Excel 和範本，預設建立新版本／工作副本，不覆寫來源。
- 執行環境、權限、renderer 與工具可用性屬於對話回報，不應混入交付的操作說明書內容。
