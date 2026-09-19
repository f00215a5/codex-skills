---
name: ui-guide-lite
description: Use when creating or revising a 系統 UI 操作說明書, user manual, or Python-only DOCX guide that needs complete real-screen evidence, traceable annotations, field definitions, operation steps, incremental QA, and independent delivery review.
---

# UI 操作說明書（輕量版）

建立可操作、可驗證的系統 UI 說明書。輕量版以實機畫面和可追溯來源描述 UI，不猜測控制項或後續影響；使用 Python、`python-docx` 和 Pillow 建立 DOCX、處理圖片與做可驗證的結構 QA。版本候選為 `0.5.0`，證據、隱碼、操作語意與交付阻擋標準對標一般版 `0.5.0`；差異只在 renderer 不可用時的版面／結構可驗證範圍。

本版流程不依賴或使用 `Documents`、Word 或 LibreOffice renderer。可做 DOCX 內容讀回、嵌圖清單／雜湊、圖說與結構檢查，以及以 Pillow 產生實際嵌圖尺寸的內容預覽；這些結果只能稱為內容預覽或結構／封裝檢查，不能宣稱已通過 Word 分頁、字型、換行或最終視覺渲染。`render_visual.status` 使用 `not_performed` 或 `out_of_scope` 並附原因時，若其他適用關卡完成，仍可在輕量版範圍內正式交付；本流程未使用 renderer 本身不構成 `blocked`。

## 工作路由與必要規範

依序完成「範圍確認 → 代表圖端到端實測 → 完整性／取證 → 隱碼與標註 → 文件建置與讀回 → 結構／幾何 QA → 獨立交付審核」。整改也依此順序推進：先判斷下一步是否能實質提高讀者完成主要流程的可用性；有阻擋項時不得以重建、舊檔或機械 pass 掩蓋它。

依階段閱讀本 skill 內的 references；不依賴已安裝的完整版 plugin：

- 取證前讀 [screenshot-completeness-workflow.md](references/screenshot-completeness-workflow.md)、[screenshot-manifest.md](references/screenshot-manifest.md)、[screenshot-redaction-policy.md](references/screenshot-redaction-policy.md) 和 [incremental-qa-workflow.md](references/incremental-qa-workflow.md)。
- 標註前讀 [annotation-qa.md](references/annotation-qa.md)，需要座標校準或內容預覽時再讀 [render-and-annotation-qa.md](references/render-and-annotation-qa.md)。
- build 前讀 [document-structure-qa.md](references/document-structure-qa.md)、[default-document-layout.md](references/default-document-layout.md) 和 [visual-consistency-standard.md](references/visual-consistency-standard.md)。
- 交付前讀 [independent-delivery-review.md](references/independent-delivery-review.md)。

QA record 記錄本次 `ui-ops-manual-lite` 版本、實際讀過的相對 reference 路徑、適用 schema、代表圖／批次、唯一 finding ledger、資產 freeze／checkpoint、回歸和實際整改輪次。不要用一份新的審核結果取代既有 ledger，也不要把完整版的 reference 或安裝狀態當作 lite 的前置條件。

## 新任務第一輪回覆與預設

若目前任務尚未確認必要範圍或交付資訊，第一輪回覆先提出「預設範圍確認」；若使用者在目前任務已明確接受預設、已提供目標畫面與交付資料夾，沿用該確認，不重複詢問同一授權。若只缺一兩項，只詢問缺項，不重新送出整份表單。

必要時使用下列固定欄位；可由使用者逐項修改：

1. 前端 repository（可選）：URL／本機路徑與 branch、tag 或 commit；用於提出可驗證的畫面候選。
2. 後端 repository（可選）：URL／本機路徑與 branch、tag 或 commit；只用於確認資料異動與成功影響。
3. 目標畫面：URL／路徑清單或上傳清單；沒有清單不自行猜測範圍。
4. 交付：文件名稱、初始版本和交付資料夾；未確認前不寫入未授權位置。
5. 截圖：每個目標畫面包含入口／到達路徑、完整主要流程和畫面選項；長頁依完整性規範使用 full-page 或有序 viewport sequence。
6. UI 覆蓋：實際可見的欄位、表頭、必填標記、icon、按鈕、狀態與限制；無法確認的欄位寫「待確認」。
7. 隱碼／標註：精準遮蔽敏感值，保留金額與操作 labels；互動目標以紅框和編號標示。
8. 驗證：確認使用 Python-only DOCX 結構／內容讀回和獨立 review；不把 Word renderer 當作 lite 的交付前置條件。

同時確認登入／測試資料的授權範圍。只用於取證；密碼、權杖、個資和不應外流的業務資料必須遮蔽。會寫入、送出、刪除或排程的 UI 動作要取得當下授權；只讀取和可逆的取證、檢查與 build 可依已確認範圍繼續。

## 初始化：本地 venv

首次使用時依現有 bootstrap 建立本地 venv，僅使用 Python 套件 `python-docx` 和 Pillow；不要安裝外部文件引擎或臨時建立另一個 venv：

```text
Windows PowerShell: & python "<skill-path>\scripts\bootstrap.py"
macOS/Linux: python3 "<skill-path>/scripts/bootstrap.py"
```

Windows 使用 `Scripts\python.exe`；macOS／Linux 使用同一 venv 根目錄下的 `bin/python`。不要改用系統 Python、全域 pip、外部文件引擎或臨時建立另一個 venv：

```text
Windows PowerShell: & "<venv>\Scripts\python.exe" "<skill-path>\scripts\<script>.py"
macOS/Linux: "<venv>/bin/python" "<skill-path>/scripts/<script>.py"
```

各腳本的必要參數依其 `--help` 與下方的具體流程補上。

腳本測試固定走 `run_tests.py`。它會逐檔執行目前的 `tests\*.tests.py`（這些 dotted 檔名不交給 `unittest discover`），拒絕找不到測試、子程序失敗或任何檔案回報 0 tests：

```text
Windows PowerShell: & "<venv>\Scripts\python.exe" "<skill-path>\scripts\run_tests.py" --tests-dir "<skill-path>\tests"
macOS/Linux shell: "<venv>/bin/python" "<skill-path>/scripts/run_tests.py" --tests-dir "<skill-path>/tests"
```

## 取證、完整主圖與來源

以使用者確認的功能清單建立覆蓋表。每個必要操作／狀態都要有完整頁面主圖與最終文件位置；局部放大圖只能補充，不能取代主圖。先選一張能代表頁面上下文、操作目標和隱碼情況的代表圖，完成 raw → redacted → annotated → 暫存 DOCX／讀回的端到端流程並通過圖片關卡，再按畫面／狀態分小批次。每張圖都要有自己的 `captureState.id`、raw/source SHA-256、viewport／scroll／full-page 校準依據、redaction／annotation bbox 和 manifest；不同狀態即使尺寸相同也不得沿用舊座標。

主圖規則：

- 預設保留整個應用程式頁面、頁首／標題、導覽或側邊欄、主要內容和操作區的相對位置。短頁用完整 viewport；長頁使用工具支援的 full-page，或以有順序、scroll offset、重疊區域及各自 manifest 的 `viewport-sequence` 覆蓋內容。
- full-page 可能重排、改變 lazy content 或讓 fixed header 覆蓋內容。每張 raw 拍完後重新確認實際 PNG 尺寸和 DOM／文字 bbox；**不能用 `pngHeight / viewportHeight` 當成全頁像素倍率**，也不能把拍攝前的固定 y、列距或 viewport 座標直接套到全頁 PNG。依該張圖的實際輸出、已知控制項和 scroll 定義校準並記錄。
- 彈窗保留其頁面背景和完整彈窗；內容過長時按同一連續 viewport 規則補齊。不得只裁切欄位、按鈕或錯誤訊息作唯一操作圖。
- 使用者沒有明示時只用實際截圖。不得用生成、重繪或抽象圖冒稱 screenshot；取得不到適用實圖時保留 `draft`／待補證據並說明缺件。

每張圖的來源使用 `sourceKind`：`captured`、`provided`、`reused`，或使用者明示且記錄批准的 `schematic`。覆蓋表要標示 `captureKind`（`full-page`、`viewport-sequence`、`detail`）；`detail` 必須指向同一狀態的完整主圖。

## 非截圖圖表（條件式）

只有使用者明確要求流程圖、關係圖、架構圖、狀態圖或泳道圖等非截圖圖表時，才呼叫共用 $ui-diagrams 技能；由該技能處理圖表的就緒檢查與交接。本技能不自行重複圖表生成。截圖、紅框、游標和互動標註仍依本 skill 的實圖與整合 manifest 流程處理，不呼叫 $ui-diagrams。若圖表技能拒絕或無法使用，只停止圖表分支，繼續可獨立完成的手冊工作；限制留在對話或 QA record，不寫入 DOCX。

## 隱碼與標註

預設遮蔽姓名、身分／客戶／會員／員工 ID、地址、電話、電子郵件、保單／帳單／合約／交易／案件識別碼、密碼、權杖、API key、session 值及不應外流的內部帳號。**金額預設保留**；只有使用者或資料政策明確要求時才記錄金額遮蔽。欄名、控制項 labels、按鈕文字和必要操作提示要保留且可讀。遮蔽只覆蓋實際敏感值和必要 padding，不遮住 protected control／label；manifest、caption、檔名和 review evidence 不得含敏感原值。

固定順序是 raw → redacted → annotated → DOCX。raw 只留在受限 QA 工作區，不嵌入 DOCX 或交付包。每張圖建立一份整合 per-image screenshot manifest（包含 redactions 與 annotations）；座標優先由當次 DOM／文字 `getBoundingClientRect` 或 `Range.getBoundingClientRect` 測得，在確認 device pixel ratio、scrollbar、full-page 重排、fixed header 和 scroll 定義後逐張校準。DOM 不可用時不得猜測座標。

若輸入 bytes 的實際格式與檔名不同，先用 `scripts/capture.py canonicalize` 保存不可變原始 bytes、產生同尺寸同像素 canonical PNG 並寫 `captureProvenance`；缺少真實 viewport／scroll／capture id／capture kind／calibration 時保留 `metadataStatus: "incomplete"`，不得用 PNG 尺寸或 0 補值，正式 gate 會阻擋。`redact.py` 與 `annotate.py` 的工具 provenance 由同一 manifest 產生，manifest 仍直接保存 redacted／annotated hash；`annotationProvenance` 必須在獨立 review 的 `imageEvidence` 與 `reviewed_files` 綁定。review status 變更不重畫圖片，父圖、bbox、id、cursor 或 badge 變更則攔截舊 artifact。

預覽階段用 `annotate.py check` 和 `draw`；狀態可為 `proposed`／`pending`／`manual-adjusted`，不可為了讓 draw 執行而預填 `verified`。builder 直接以 100% 並排檢視 raw、redacted、annotated，確認框、編號、caption、控制項、狀態與敏感值後才更新 `checked`／`verified`，再以 `--require-approved` 做交付門檻。builder 的狀態不能替代獨立 reviewer。

## 文件建置、讀回與 lite 可驗證版面

開始排版前讀文件結構與版面 references。使用 `build_docx.py` 產生新版本副本，不覆寫既有來源；manifest 的圖片只能引用 redacted／annotated PNG。每章包含入口、前置／鎖定條件、實際操作步驟、欄位／按鈕表、成功影響、失敗／取消行為和操作後檢核；每個操作小節的真正 Word numbering 都從步驟 1 重啟，圖說中的紅框 id 與該張 annotated manifest 一一對齊。

lite 的結構／幾何檢查要攔截可由 OOXML／封裝可靠判定的風險：表格或圖片超出 section 容器可用寬高、固定列高或固定像素高度、欄網格與 cell 寬度不一致、錯誤表格對齊、numbering 定義／引用／重啟不完整、raw 或未遮蔽圖片進入 DOCX、嵌圖 relationship 遺失、圖說缺失，以及 manifest／review hash 失配。表格寬度依內容彈性調整，但必須落在容器可用區；合法窄表仍要置中。

完成 build 後由 Python 讀回真正輸出的 DOCX，走讀主要流程、正文／表格文字、嵌入媒體數量與 hash、每張圖的圖說和 numbering／結構；用 Pillow 或等效程式產生實際嵌圖尺寸的內容預覽，必要時直接看圖確認圖說與主要內容可辨識。讀回和 preview 只能證明內容／封裝／結構範圍，不能宣稱分頁、字型替代、換行或 Word renderer 實際 pass。文件結構、命令與風險清單見 [document-structure-qa.md](references/document-structure-qa.md) 和 [default-document-layout.md](references/default-document-layout.md)。

## 增量整改與交付門檻

只維護一份跨輪次 finding ledger。每筆至少有 `id`、`asset/state`、`stage`、`category`、`status`、evidence、fix verification；上一輪未解項目與新 findings 合併保存。阻擋項包括錯誤／誤導操作、主要流程或關鍵實圖缺失、敏感值漏遮、遮住控制項／labels、內容不可讀。這些項目未解時不能標 `pass`。

非阻擋的次要欄位深度、措辭精緻度和輕微美觀可在 finding 中以 `accepted limitation` 附 reason／evidence，不能用來包裝 blocker。清楚定義「無改善」：本輪指定缺陷在實際 output 未消失或影響未減、修正了錯的位置或只改 source 未更新／重建 output，或引入同級／更重回歸。第一次無改善先記錄 evidence 並診斷原因；同一缺陷使用同一策略連續兩次無改善是上限，不是必跑配額；已有 evidence 顯示策略不再提高主要可用性時，可更早改做定點最小修復、採用使用者已明示的範圍縮限，或如實回報部分 draft／blocked。主要漏遮、誤導、缺關鍵流程或內容不可讀仍不能 pass；不得僅更改狀態、刪減必要驗證、依 validator pass 或舊成品把 blocker 改成 pass。

每個已通過階段 freeze source／output hash、capture state、依賴與 builder 輸入，建立版本化、不可覆寫的 immutable checkpoint；raw、redacted、annotated、manifest、caption、DOCX 或需求證據變更會使受影響下游 review 失效，必須從該依賴重建並重新檢查。建置後一定讀回真正 output，不能把 source 已更新當成成品已更新。

builder 可以先直接看圖並交接 `draft`／待 reviewer 狀態；最終交付 reviewer 必須是 builder 以外的獨立人工或執行者，`builder.id` 與 `reviewer.id` 明確且不同，不能由 builder 改名自審。沒有 reviewer、圖片／需求證據不可讀、必要 evidence 缺失或過期時為 `blocked`／`draft`；缺 renderer 本身不列入 blocker。review JSON 固定包含 `requirements`、`redaction`、`operation`、`layout_structure` 四類 checks，及 `render_visual` 的 `not_performed`／`out_of_scope` 原因。所有 artifact／reviewed files hash 必須綁定真正輸出，任何受影響檔案變更都要重做相關 checks。

## 驗證與交付回報

在 Windows venv 內（macOS／Linux 將前綴替換為同一 venv 的 `bin/python`）依腳本現行 CLI 執行：

```text
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\redact.py" check --image "<qa>\raw.png" --redacted "<qa>\redacted.png" --manifest "<qa>\screenshot.json" --provenance "<qa>\provenance.json" --require-checked
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\annotate.py" check --image "<qa>\redacted.png" --annotations "<qa>\screenshot.json" --require-approved
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\validate_screenshot_manifest.py" --manifest "<qa>\screenshot.json" --output "<qa>\screenshot-validation.json"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\build_docx.py" --manifest "<workspace>\manual.json" --output "<deliverable>\manual.docx"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\preview_docx.py" --docx "<deliverable>\manual.docx" --output-dir "<qa>\content-preview" --dpi 96
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\verify_docx.py" --docx "<deliverable>\manual.docx" --manifest "<workspace>\manual.json"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\audit_delivery.py" --docx "<deliverable>\manual.docx" --output "<qa>\structure.json"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\audit_delivery.py" --docx "<deliverable>\manual.docx" --review "<qa>\review.json" --manifest "<workspace>\manual.json" --output "<qa>\review-validation.json"
```

對每份圖片證據固定使用 [screenshot-manifest.md](references/screenshot-manifest.md) 的單一整合 manifest，依序執行 `redact.py`、`annotate.py` 與 `validate_screenshot_manifest.py` adapters，讀回 source／redacted／annotated hashes、capture calibration、幾何與 review status；不要另造第三份圖片 manifest。validator 的 exit 1 仍可能已寫出 `blocked`／`fail` 報告，必須讀取 `geometry_status`、`manifest_status` 和 `semantic_review`。`verify_docx.py` exit 0 只代表列出的結構檢查通過；`audit_delivery.py` exit 0 只代表報告寫出。任何機械報告都不能代替直接看圖、最終 DOCX 內容讀回或獨立 reviewer。

上列不帶 `--review`／`--manifest` 的 `structure.json` 只是前置機械報告，不能作為正式完成條件。正式交付必須在另一位 reviewer 完成 review JSON 後執行最後一行，並檢查 `independent_review.status`、四類 checks、`image_evidence_chain.status` 和所有 hash；只要正式命令帶 `--manifest`，每張實際嵌入圖都要在 review 的 `imageEvidence` 中回指同一份整合 screenshot manifest、provenance 與已核對的 support files。

交接記錄逐項回報：隱碼、標註、結構／幾何、內容讀回、獨立審核、證據雜湊、交付範圍。renderer、權限與 fallback 狀態只在對話／QA record 回報，不寫進 DOCX。若缺圖、漏遮、誤導流程、遮 controls 或內容不可讀，回報 blocker 與 evidence，不以少量代表圖或 draft 宣稱完成。

## 常見錯誤

| 情況 | 正確處理 |
| --- | --- |
| 每次任務都重新要求已接受的預設 | 讀取目前任務的確認，沿用已確認範圍；只問缺少的目標或交付資訊。 |
| 只有局部欄位／按鈕圖 | 返回完整頁面主圖；detail 只能補充。 |
| full-page 使用 `pngHeight / viewportHeight` 或舊固定 y | 回到該張 raw，以實際輸出和校準 control 重新測量。 |
| 生成／重繪 UI 取代實圖 | 標記待補證據／draft；除非使用者明示並留下 schematic 批准，不得冒稱 screenshot。 |
| 敏感值漏遮或遮住 controls／labels | 精準縮小 redaction bbox，保留金額（除非明示遮蔽）和操作文字，重建下游圖片與 DOCX。 |
| source 已改但 DOCX／review 未更新 | 讀回真正 output，重算受影響 hash、重建 checkpoint 並重做 review。 |
| 同一缺陷同策略無改善 | 兩次是停止該策略的上限，不是必跑配額；已有 evidence 顯示無主要可用性改善時可更早定點修復、明示縮限或如實回報 draft／blocked。 |
| 把結構／preview 當 Word render pass | 只回報 lite 可驗證範圍；`render_visual` 填 `not_performed`／`out_of_scope`。 |
| builder 改名成 reviewer | 最終 review 必須實際由另一位未參與產製的人工或獨立執行者完成；明確記錄不同的 `builder.id`／`reviewer.id`，不能只改 JSON 名稱。 |
