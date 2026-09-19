# 圖片標註與 lite 內容預覽 QA

本版沒有 DOCX renderer；這份規格只處理圖片標註語意、嵌圖內容預覽和可機械驗證的結構。不得把內容 preview、`python-docx` 讀回或任何 exit code 說成 Word 分頁／字型／最終視覺通過。

## 標註先於建置

先依 [screenshot-completeness-workflow.md](screenshot-completeness-workflow.md) 確認完整主圖，再依 [screenshot-manifest.md](screenshot-manifest.md) 保存每次 capture 的 state、hash 和尺寸。raw hash 改變，即使 PNG 尺寸相同，也要重新測量每筆 redaction／annotation bbox；不能沿用固定 y、列距或上一張圖的 caption mapping。

建立整合 screenshot manifest 後執行；redaction 與 annotation adapter 消費同一份 JSON：

```text
Windows PowerShell:
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\annotate.py" check --image "<redacted>.png" --annotations "<screenshot.json>"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\annotate.py" draw --image "<redacted>.png" --annotations "<screenshot.json>" --output "<annotated>.png"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\validate_screenshot_manifest.py" --manifest "<screenshot.json>" --output "<validation.json>"
macOS/Linux:
"<venv>/bin/python" "<skill-path>/scripts/annotate.py" check --image "<redacted>.png" --annotations "<screenshot.json>"
"<venv>/bin/python" "<skill-path>/scripts/annotate.py" draw --image "<redacted>.png" --annotations "<screenshot.json>" --output "<annotated>.png"
"<venv>/bin/python" "<skill-path>/scripts/validate_screenshot_manifest.py" --manifest "<screenshot.json>" --output "<validation.json>"
```

`check` 可先接受 `proposed`／`pending`／`manual-adjusted` 供 preview；不能為讓 draw 執行而預填 `verified`。builder 必須直接以 100% 並排檢視 raw、redacted、annotated，逐筆確認：

1. 紅框完整框住指定 control，不框鄰近 control 或空白。
2. 紅框編號、manifest annotation id、caption 編號和實際 control label 一致且在該張圖內唯一。
3. 框線、編號和 cursor 不遮住 control label、輸入值、錯誤訊息或保留的金額。
4. 圖片狀態、步驟、可用／鎖定條件和 caption 相符。
5. redaction 只覆蓋敏感值，raw 不在 DOCX 或交付包。

確認後才更新為整合 validator 支援的 `checked`／`verified`，再執行現行的 `--require-approved` gate。狀態欄位不能代替 builder 直接看圖，也不能代替另一位 reviewer 的獨立交付審核。

## 座標校準

工具契約允許時，使用目前 capture 的 DOM／文字 `getBoundingClientRect`／`Range.getBoundingClientRect` 取得數值 bbox，確認 device pixel ratio、scrollbar、固定 header、full-page 重排和 scroll offset 後逐張校準。full-page 不使用 `pngHeight / viewportHeight` 作為全局倍率；內部捲動區、viewport sequence 和 fixed element 必須按每張實際圖測量。DOM 不可用時不能猜測座標，也不能把遮罩程式注入頁面；先保存 raw，再離線產生 redacted／annotated。

## 內容預覽與 DOCX 讀回

build 後讀回真正 output：使用 `python-docx`／ZIP OOXML 讀取章節、主要流程文字、欄位表、圖說、numbering、嵌圖 relationship 和媒體 hash；使用 Pillow 依 DOCX 實際嵌入的 `width`／`height` 或 `display` metadata 產生內容 preview，直接看圖確認主要頁面、control labels、紅框和圖說可辨識。預覽只作內容證據，不是 Word render；不能據此宣稱頁數、分頁、字型替代、換行或最終版面 pass。

內容 preview 固定由 `preview_docx.py` 讀取真正輸出的 DOCX；它維持正文／表格順序，依 inline image 的實際嵌入尺寸產生 `preview.json`、`preview.html` 和縮放後的圖片。輸出目錄必須是新的或空目錄，`--dpi` 預設 96，可明示為 96：

```text
Windows PowerShell:
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\preview_docx.py" --docx "<deliverable>\manual.docx" --output-dir "<qa>\content-preview" --dpi 96
macOS/Linux:
"<venv>/bin/python" "<skill-path>/scripts/preview_docx.py" --docx "<deliverable>/manual.docx" --output-dir "<qa>/content-preview" --dpi 96
```

此工具的 `render_visual.status` 固定是 `not_performed`；內容 preview 只表示嵌圖內容／封裝可讀，不是 Word renderer、分頁或字型 pass。

圖片、manifest、build manifest、需求 evidence 或 DOCX 任何一項變更後，重算受影響 hash、重建 output，重新讀回並讓獨立 reviewer 檢視；不能只替舊 review 換 hash。
