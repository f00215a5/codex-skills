# 每張截圖 manifest 合約（輕量版）

在建立或驗收 raw／redacted／annotated 截圖前閱讀。每張頁面、狀態和擷取批次各自保存一份**整合 screenshot manifest**；不同狀態不得共用座標。`schema_version` 目前為 `1`。`redact.py`、`annotate.py` 和 per-image validator 都是這份 manifest 的 adapters／讀取者；不要再手寫另一份 raw／redacted／annotation schema，也不要讓模型維護互相矛盾的第三套資料。

## 整合 manifest

路徑以 manifest 的工作目錄為根。先對已落地、不可變的 canonical raw PNG 計算 `sourceSha256`，`captureState.rawSha256` 必須相同；redacted／annotated PNG 產出後都要計算 SHA-256 並回填 manifest 的 `redactedSha256`／`annotatedSha256`。正式 validator 前兩者必須存在且與實際檔案相符，不能只依賴 adapter／provenance 另存 hash。必要欄位與目前 validator／adapter 的兼容別名以腳本現行 schema 為準，以下是可追溯的最小形狀：

```json
{
  "schema_version": 1,
  "sourceImage": "raw/create-task.png",
  "sourceSha256": "<canonical-raw-png-sha256>",
  "captureProvenance": "qa/create-task-capture.json",
  "redactedImage": "redacted/create-task.png",
  "redactedSha256": "<redacted-png-sha256>",
  "redactionProvenance": "qa/create-task-redaction.json",
  "annotatedImage": "annotated/create-task.png",
  "annotatedSha256": "<annotated-png-sha256>",
  "annotationProvenance": "qa/create-task-annotation.json",
  "sourceKind": "captured",
  "captureKind": "full-page",
  "captureState": {
    "id": "create-task-filter-open-01",
    "rawSha256": "<same-canonical-raw-png-sha256>",
    "viewportCssSize": {"width": 1536, "height": 864},
    "scroll": {"x": 0, "y": 640},
    "calibration": {
      "mode": "known-control",
      "pngSize": {"width": 1920, "height": 2160},
      "viewportCssSize": {"width": 1536, "height": 864},
      "knownControl": {"name": "儲存", "bbox": {"x": 1050, "y": 670, "width": 92, "height": 40}}
    }
  },
  "originalImageSize": {"width": 1920, "height": 2160},
  "protectedAreas": [
    {"name": "儲存 button label", "bbox": {"x": 1038, "y": 660, "width": 120, "height": 60}}
  ],
  "redactions": [
    {
      "category": "policy-number",
      "method": "opaque-rectangle",
      "bbox": {"x": 840, "y": 248, "width": 240, "height": 32},
      "status": "pending"
    }
  ],
  "annotations": [
    {
      "id": "1",
      "controlName": "儲存",
      "caption": "紅框 1：儲存按鈕。",
      "bbox": {"x": 1050, "y": 670, "width": 92, "height": 40},
      "provenance": "dom-derived",
      "badgePosition": {"anchor": "top-left", "offset": {"x": 0, "y": 0}},
      "status": "pending"
    }
  ],
  "reviewStatus": "pending"
}
```

`sourceKind` 使用 `captured`、`provided`、`reused` 或使用者明示並批准的 `schematic`；`captureKind` 使用 `full-page`、`viewport-sequence` 或 `detail`。`detail` 必須以 `detailOf`／`mainImage` 回指同一狀態的完整主圖。每個 manifest 必須有 `redactions` 和 `annotations` 陣列；沒有敏感資料時使用空 `redactions` 並加不含原值的 `noSensitiveDataReason`。`reviewStatus`、redaction status 和 annotation status 在 builder／reviewer 直接看圖後才能由 pending 改為 checked／verified；任何 pending／blocked 都不能產生正式 pass。

`protectedAreas` 只放不可被遮住的 label、欄名、button 或其他定位區，不可把包含敏感值的整個 input／列列為 protected。redaction bbox 不得和 protected area 正面積重疊。manifest、caption、檔名和報告只保留類別、座標、狀態、capture id 和 hash，不寫敏感原值或可反推出原值的文字。

## Adapter 介面與證據順序

整合 manifest 是 single source of truth；adapter 只消費同一份檔案的對應欄位，不能自行建立第二份座標來源。`capture.py`、`redact.py`、`annotate.py` 產生的 provenance 只由工具生成父圖／hash／pixel-input 記錄；正式 validator 仍要求 manifest 直接回填圖片 hash，並以 `redactionProvenance`、`annotationProvenance` 綁定兩條衍生鏈：

```text
Windows PowerShell:
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\capture.py" canonicalize --input "<capture>" --raw-output "<qa>\raw\create-task.capture" --canonical-output "<qa>\raw\create-task.png" --provenance-output "<qa>\create-task-capture.json" --capture-id "create-task-filter-open-01" --capture-kind "full-page" --viewport-width 1536 --viewport-height 864 --scroll-x 0 --scroll-y 640 --capture-state "<qa>\capture-state.json"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\redact.py" draw --image "<raw.png>" --manifest "<screenshot.json>" --output "<redacted.png>" --provenance-output "<provenance.json>"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\redact.py" check --image "<raw.png>" --redacted "<redacted.png>" --manifest "<screenshot.json>" --provenance "<provenance.json>" --require-checked
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\annotate.py" check --image "<redacted.png>" --annotations "<screenshot.json>"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\annotate.py" draw --image "<redacted.png>" --annotations "<screenshot.json>" --output "<annotated.png>" --provenance-output "<annotation-provenance.json>"
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\annotate.py" check --image "<redacted.png>" --annotations "<screenshot.json>" --require-approved
macOS/Linux:
"<venv>/bin/python" "<skill-path>/scripts/capture.py" canonicalize --input "<capture>" --raw-output "<qa>/raw/create-task.capture" --canonical-output "<qa>/raw/create-task.png" --provenance-output "<qa>/create-task-capture.json" --capture-id "create-task-filter-open-01" --capture-kind "full-page" --viewport-width 1536 --viewport-height 864 --scroll-x 0 --scroll-y 640 --capture-state "<qa>/capture-state.json"
"<venv>/bin/python" "<skill-path>/scripts/redact.py" draw --image "<raw.png>" --manifest "<screenshot.json>" --output "<redacted.png>" --provenance-output "<provenance.json>"
"<venv>/bin/python" "<skill-path>/scripts/redact.py" check --image "<raw.png>" --redacted "<redacted.png>" --manifest "<screenshot.json>" --provenance "<provenance.json>" --require-checked
"<venv>/bin/python" "<skill-path>/scripts/annotate.py" check --image "<redacted.png>" --annotations "<screenshot.json>"
"<venv>/bin/python" "<skill-path>/scripts/annotate.py" draw --image "<redacted.png>" --annotations "<screenshot.json>" --output "<annotated.png>" --provenance-output "<annotation-provenance.json>"
"<venv>/bin/python" "<skill-path>/scripts/annotate.py" check --image "<redacted.png>" --annotations "<screenshot.json>" --require-approved
```

redaction adapter 以 `sourceImage`／`sourceSha256`／`redactions`／`protectedAreas`／`captureState` 處理 raw → redacted；annotation adapter 的 `--annotations` 參數直接接收**同一份整合 manifest**，以其中的 `annotations`、`redactedImage`／`redactedSha256` 和同一 `captureState` 處理 redacted → annotated。不要傳第二份 annotation-only JSON，也不要讓模型另寫第三份檔案。`capture.py` 缺少真實 viewport、scroll、capture id、capture kind 或 calibration 時只輸出 `metadataStatus: "incomplete"`，不以 PNG 尺寸或 0 冒充，正式 gate 會阻擋。`redact.py`／`annotate.py` 的 provenance 會綁定實際父圖與受像素影響的 bbox／method／id／cursor／badge input hash；review status 改變不會使圖失效，但父圖、bbox、id、cursor 或 badge 改變必須重建。輸出與 provenance 都是 immutable new paths，不能覆寫輸入或既有檔案。per-image validator 讀同一份整合 manifest 和上述三張圖，輸出新的驗證報告檔；它不回寫圖片或 manifest。

## 擷取、格式與座標綁定

每次重新擷取都建立新的 `captureState.id`、重新計算 raw hash，重新測量該張圖的 redaction／annotation bbox。即使尺寸相同，只要 raw hash 不同，也要重新看圖和測量。工具契約允許時，優先用當次 DOM 的 `getBoundingClientRect()` 或文字 `Range.getBoundingClientRect()` 取得數值 bbox；先確認 device pixel ratio、scrollbar、full-page 重排、fixed header 和 scroll 定義，再逐張校準。不能以 `pngWidth / viewportWidth` 或 `pngHeight / viewportHeight` 全局套用，更不能用全頁高度除以 viewport 高度當倍率。full-page calibration 必須提供 per-image 的 known control／explicit scale evidence；舊的 `pngHeight/viewportHeight` 值不能獨自當 DPR。

若 full-page 回傳 JPEG bytes，即使檔名是 `.png`，先保存未修改的原始 bytes、實際 MIME 和原始 hash；對副本解碼後以相同尺寸／像素資料寫 canonical PNG，不 resize、crop 或重新壓縮。解碼 canonical PNG 後逐像素比對，才可記錄 `captureProvenance.pixelEquality: "verified"`；原始捕獲檔只留在受限 QA 區。`capture.py canonicalize` 會先檢查所有輸入／輸出別名、既有 immutable paths、影像格式及 capture metadata，再一次產出 raw、canonical PNG 和 provenance，參數不合法時不留下半套輸出。

若截圖契約回傳 `Uint8Array`／明確允許的 Node `Buffer`，先依當前 CUA/browser API 的實際能力選擇保存分支；若同一 runtime 允許 `node:fs/promises`，在已綁定的 Tab 上直接以 `tab.getScreenshot({emit: false})` 取得 bytes，再用 `fs.writeFile` 保存到受限 QA 路徑，對落地 bytes 計 hash，最後才交給 `capture.py canonicalize`。下例的 `confirmedQaDirectory` 是 placeholder，執行前替換成已確認可寫入的絕對 QA 目錄；不要改成相對路徑。例如：

```js
const bytes = await tab.getScreenshot({emit: false});
if (!(bytes instanceof Uint8Array)) throw new Error("getScreenshot did not return bytes");
const {mkdir, writeFile} = await import("node:fs/promises");
const {join} = await import("node:path");
const confirmedQaDirectory = "<已確認可寫入的絕對 QA 目錄>"; // 執行前替換此 placeholder
await mkdir(confirmedQaDirectory, {recursive: true});
await writeFile(join(confirmedQaDirectory, "create-task.capture"), bytes, {flag: "wx"});
```

這不是自行發明 CUA API，也不能因 DOM 不可用而猜測座標。若 runtime 沒有 Node fs／`writeFile`，或 API 回傳型別不符，記錄 runtime、API、型別和保存路徑的具體錯誤並標為待補，不一律宣稱無法落地；不要繞 browser clipboard→PowerShell 或 `CopyFromScreen`，native capture disabled 時也不要改試另一套 native capture。`fullPage` 只有 browser 文件明示支援時才傳，否則使用實際支援的 viewport／sequence。

## 唯讀驗證與邊界

per-image validator 對同一份整合 manifest 檢查 source raw／redacted／annotated 的 hash、PNG 尺寸與格式、capture state／calibration、bbox 邊界、protected area overlap、annotation id／caption／status 和必要 source fields；正式 validator 要求 manifest 同時有 `redactedSha256`、`annotatedSha256`，並核對兩者與實際 PNG，缺漏或不符即 fail；以新輸出檔保存 `geometry_status`、`manifest_status`、`semantic_review: "not_performed"`。`geometry_status: "pass"` 仍不能取代 builder 100% 直接看圖；pending／blocked 不能報正式 manifest pass。若 validator CLI 的參數或報告欄位變動，以 lite skill 內該腳本的 `--help` 和現行 schema 為準，不虛構額外命令。

目前 lite validator 的固定命令是：

```text
Windows PowerShell:
& "<venv>\Scripts\python.exe" "<skill-path>\scripts\validate_screenshot_manifest.py" --manifest "<qa>\create-task.json" --output "<qa>\create-task-manifest-validation.json"
macOS/Linux:
"<venv>/bin/python" "<skill-path>/scripts/validate_screenshot_manifest.py" --manifest "<qa>/create-task.json" --output "<qa>/create-task-manifest-validation.json"
```

`--output` 必須是新檔，不能覆寫整合 manifest 或三張輸入圖片；exit 0 只表示 `manifest_status: "pass"` 的報告成功寫出，exit 1 仍要讀取已寫出的 `blocked`／`fail` 報告。

`redact.py`／`annotate.py`／validator 的機械結果不能證明已找出所有敏感值、紅框貼合 control、操作語意或內容可讀。builder 必須逐張直接看 raw／redacted／annotated，最終 reviewer 另依 [independent-delivery-review.md](independent-delivery-review.md) 審核；圖片或 manifest 改變後重算受影響 hash、重建 output 和 review。
