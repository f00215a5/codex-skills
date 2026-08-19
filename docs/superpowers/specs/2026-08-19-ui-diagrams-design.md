# ui-diagrams 設計規格

日期：2026-08-19
狀態：已確認，待實作規劃

## 目的

新增獨立 marketplace plugin `ui-diagrams`，提供核心 skill `$ui-diagrams`。它是 `$ui-guide` 與 `$ui-guide-lite` 的共用圖表前置層：只處理操作介面說明書中的流程圖、關係圖、架構圖、泳道圖及其他非截圖標註的圖表需求。

圖表的實際建立沿用上游 [Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill)；本外掛不複製或分叉上游的產圖邏輯。

## 範圍與邊界

- `$ui-guide` 與 `$ui-guide-lite` 僅在使用者明確要求圖表時呼叫 `$ui-diagrams`。
- 截圖、紅框、游標、欄位說明與 DOCX 主流程維持由原本 UI 手冊技能處理，不會因圖表依賴缺少而停止。
- 只在使用者同意後安裝外部 skill 或 draw.io Desktop；不得預先下載、安裝或修改系統套件。
- 若圖表分支不能執行，明確回報原因並跳過圖表；不得假裝以截圖紅框或其他未同意格式取代 draw.io 圖表。

## 外掛結構

```text
plugins/ui-diagrams/
├── .codex-plugin/plugin.json
└── skills/ui-diagrams/
    ├── SKILL.md
    ├── agents/openai.yaml
    └── references/
        └── dependency-and-install-policy.md
```

- plugin 與 skill 均命名 `ui-diagrams`，避免兩個 UI 手冊外掛同時安裝時發生 skill 名稱衝突。
- 兩個既有 plugin 各自的 `ui-guide`／`ui-guide-lite` 新增簡短、條件式的路由規則，要求在合格的圖表需求出現時先使用 `$ui-diagrams`。
- `ui-ops-manual`、`ui-ops-manual-lite` 與新 plugin 均使用獨立 manifest version 與 Codex cache-buster。

## 觸發條件

使用者明確需要下列任一非截圖圖表時，啟用 `$ui-diagrams`：

- 操作流程圖、決策流程圖、泳道流程圖。
- UI 模組、頁面、角色、資料或功能之間的關係圖。
- 操作架構圖、狀態圖、關聯／依賴圖。

不因下列情況啟用：

- 僅要求既有畫面截圖、紅框、游標、按鈕或欄位標註。
- 只需文字條列或 Word／DOCX 的普通表格。
- 未提及圖表且沒有明確圖表意圖的操作手冊任務。

## 依賴檢核與結果狀態

在讀取圖表需求後、開始產生圖檔前，依序確認：

1. 上游 `drawio-skill` 可在本機 Codex 技能目錄讀取，且可在當前任務載入其 `SKILL.md`。
2. draw.io Desktop CLI 存在且可執行版本檢查。支援 PATH 上的 `drawio`／`draw.io`，以及平台常見的 Desktop app 執行檔位置。
3. 若 CLI 存在但受沙箱、顯示工作階段或 Electron 啟動限制，最多進行一次合規的提升權限重試；仍失敗即分類為「目前環境不可用」，不持續重試。

結果分類：

| 狀態 | 行為 |
| --- | --- |
| ready | 讀取並執行上游 `drawio-skill`。 |
| needs-install | 列出缺少項目、安裝來源與將執行的命令，詢問使用者是否同意安裝。 |
| unavailable | 在對話回報環境限制，停止本次圖表分支；UI 手冊主流程繼續。 |
| declined | 在對話回報使用者未同意安裝，停止本次圖表分支；UI 手冊主流程繼續。 |

## 使用者同意後的安裝

只有使用者對本次任務明確同意後才執行。

- `drawio-skill`：從 `https://github.com/Agents365-ai/drawio-skill` 安裝至目前使用者的 Codex skill 位置；安裝成功後，當前任務直接讀取該 skill，並提醒使用者以新 task 取得正常的 skill discovery。
- draw.io Desktop：依作業系統與已存在的套件管理器選擇最小且可驗證的官方／常用安裝途徑：Windows 使用可用的 `winget` 或上游桌面安裝程式；macOS 使用 `brew install --cask drawio` 或上游安裝程式；Linux 優先使用發行版對應的 `.deb`／`.rpm` 或已設定的套件管理器。
- 安裝後必須再次進行 readiness 檢核，僅在 `ready` 時進入上游圖表工作流程。
- 安裝需要系統權限、下載或 GUI 互動時，仍依當前執行環境的核可機制請求權限；使用者同意安裝不代表可略過系統核可。

## 產製與交付

當狀態為 `ready`，`$ui-diagrams` 使用上游 skill 的圖表類型、結構驗證、preview 與 export 規則。

- 預設交付為同名的 `.drawio` 原檔與 PNG。
- 開始產製時告知此預設；使用者可改成只要其中一項，或追加 SVG、PDF、JPG。
- 交付前向使用者回報兩個檔案的路徑與圖表驗證／預覽結果。
- 圖表檔案與 PNG 由 UI 手冊主技能依使用者同意的文件流程納入 DOCX；不把缺少依賴、安裝結果或沙箱限制寫進操作說明書內容。

## 失敗處理

- 使用者拒絕安裝、安裝失敗或 runtime 不可用時，清楚說明只影響 draw.io 圖表。
- 主技能繼續完成已確認範圍內的截圖、操作步驟、欄位定義、DOCX 結構／渲染或 Python-only 結構 QA。
- 未經使用者確認，不以 Mermaid、手繪 SVG、截圖紅框或其他圖表格式替代 draw.io deliverable。

## 驗收

1. `ui-diagrams` plugin 與 `$ui-diagrams` skill 通過結構驗證。
2. 兩個 UI 手冊 skill 在圖表觸發條件下都路由到 `$ui-diagrams`，並在純截圖需求下不路由。
3. 測試覆蓋 ready、needs-install／同意、declined、unavailable 四種路徑。
4. 測試確認拒絕／不可用只停止圖表分支，主文件流程不受阻斷。
5. 測試確認預設交付為 `.drawio` 與 PNG，且可由使用者覆寫。
