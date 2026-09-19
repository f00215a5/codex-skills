# 每張截圖 manifest 合約

在建立或驗收任何 raw／redacted／annotated 截圖前閱讀。每一張截圖各自保存一份 JSON；不要把不同頁面、不同狀態或不同擷取批次共用同一組座標。資產凍結與變更失效依賴見 [incremental-qa-workflow.md](incremental-qa-workflow.md)。`schema_version` 目前固定為 `1`。

## 最小格式

路徑以 manifest 的 `--base-dir` 為根（未指定時為 manifest 所在目錄）。先對已落地且不可變的 raw PNG 計算 `sourceSha256`，再寫入 manifest；redacted／annotated 完成後由 validator 重新讀檔檢查尺寸和 hash，不需要先把它們的 hash 寫回 manifest。`captureState.rawSha256` 必須等於該張 raw PNG 的 `sourceSha256`，用來把目前畫面狀態和這次擷取綁在一起。

```json
{
  "schema_version": 1,
  "sourceImage": "raw/create-task.png",
  "sourceSha256": "<sha256 of this raw PNG>",
  "redactedImage": "redacted/create-task.png",
  "annotatedImage": "annotated/create-task.png",
  "sourceKind": "captured",
  "captureKind": "full-page",
  "captureState": {
    "id": "create-task-filter-open-01",
    "rawSha256": "<same sha256 of this raw PNG>"
  },
  "originalImageSize": { "width": 1920, "height": 1080 },
  "reviewStatus": "pending",
  "redactions": [
    {
      "category": "policy-number",
      "method": "opaque-rectangle",
      "bbox": { "x": 840, "y": 248, "width": 240, "height": 32 },
      "status": "pending"
    }
  ],
  "annotations": [
    {
      "id": "1",
      "controlName": "儲存",
      "caption": "紅框 1：儲存按鈕。",
      "bbox": { "x": 1050, "y": 670, "width": 92, "height": 40 },
      "source": "dom-manual-adjusted",
      "status": "pending"
    }
  ],
  "protectedAreas": [
    { "bbox": { "x": 1038, "y": 660, "width": 120, "height": 60 } }
  ]
}
```

`sourceKind` 使用 `captured`、`provided`、`reused` 或經使用者明示的 `schematic`；`captureKind` 使用 `full-page`、`viewport-sequence` 或 `detail`。`detail` 必須另有同一狀態的完整主圖。`source` 是標註的來源／provenance 字串，允許 `dom`、`dom-manual-adjusted` 或其他能說明實際來源的非空值，不可用它代替人工檢視。

每個 manifest 都必須有 `redactions` 和 `annotations` 陣列。沒有敏感資料時可以使用空的 `redactions`，但必須加入不含原值的 `noSensitiveDataReason`，例如：

```json
{
  "redactions": [],
  "noSensitiveDataReason": "此狀態的實機畫面沒有敏感值。"
}
```

`reviewStatus` 不可省略，也不會由工具預填為核可：`pending` 表示尚待逐張檢視，`checked` 表示 builder 已直接檢查，`blocked` 表示不能驗收。每筆 redaction 使用 `pending`、`checked` 或 `blocked`；每筆 annotation 使用 `pending`、`verified`、`checked` 或 `blocked`。只有在 builder 以 100% 並排檢視 raw、redacted、annotated 後，才可改成 `checked`／`verified`。任何 pending 或 blocked 都不能產生 manifest `pass`。

`protectedAreas` 是可選的，只放不可被遮住的標籤、欄名、按鈕或其他操作定位區域。工具會拒絕 redaction bbox 和這些 bbox 的正面積交疊；不要把包含待遮敏感值的整個 input 或整列誤列為 protected area。碰到實際敏感值和操作目標相鄰時，縮小到真實值的邊界並由 builder 直接檢查。

## 擷取和座標綁定

每次重新擷取都要為該張圖建立新的 `captureState.id`、重新計算 `sourceSha256`，並重新測量該張圖的 redaction／annotation bbox。不能把前一張圖的固定 y range、列距或舊座標批量套用到另一個頁面、日期狀態、空白表單或捲動位置；即使尺寸相同，raw hash 不同也代表需要重新看圖和重新測量。

工具允許且畫面仍是該次 capture 的目前 DOM 時，優先以 `getBoundingClientRect()` 或目前文字的 `Range.getBoundingClientRect()` 取得控制項／敏感值的實際邊界，再依截圖與 CSS viewport 寬高比例換算。文字範圍可以只用來取得位置與尺寸，不要把文字值寫進 manifest、圖說或報告：

```javascript
const node = /* 目前頁面中已觀察到的欄位文字節點 */;
const range = document.createRange();
range.selectNodeContents(node);
const rect = range.getBoundingClientRect();
return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
```

上例只在目前工具契約允許 evaluate／DOM 讀取時使用；回傳值應是數值 bbox，不是原始文字。`getBoundingClientRect()` 得到的是 viewport 座標，不能直接假定 PNG／CSS 是 1:1，也不能全局機械套用 `pngWidth / viewportWidth`：先確認 device pixel ratio、scrollbar 是否裁除、full-page 是否重新排版、固定 header 是否覆蓋，以及工具對 scroll 位移的定義，再依該張圖的已知控制項逐張校正。連續 viewport 或內部捲動區要逐張納入捲動位移；每張 raw／redacted／annotated 都要在 100% 做 pixel-level 位置檢查。不能以 DOM 不可用為由猜測固定座標，也不能在網頁內執行遮罩；先取得 raw，再在受限 QA 工作區的離線副本完成 redacted 和 annotated PNG。

若 CUA 截圖契約回傳 `Uint8Array`（或該契約明確允許的 Node `Buffer`），這些 bytes 可以在**同一個 runtime** 用 Node 的 `fs/promises.writeFile` 寫入本機受限 QA 路徑，再用該落地檔計算 hash：

```javascript
const { writeFile } = await import("node:fs/promises");
await writeFile(localQaPath, screenshotBytes);
```

這不是瀏覽器替代控制，也不代表可以猜測 CUA API；只使用實際工具契約回傳的 bytes 和已核准的本機路徑。不要因為回傳型別是 `Uint8Array` 就判定無法保存，也不要自行生成或重繪 UI 來替代實機截圖。

### fullPage bytes 的實際格式

CUA 的 `fullPage` 可能回傳 JPEG bytes，即使呼叫端使用 `.png` 檔名；檔名不能當成 MIME 或格式證據。先把**未修改的原始 bytes**保存到受限 QA 路徑，保留實際 MIME 與原始 bytes 的 SHA256，禁止直接改寫這份原始證據。若交付流程要求 PNG，對副本解碼後以相同尺寸、相同像素資料寫成 PNG，不 resize、crop 或重新壓縮 JPEG；再解碼 canonical PNG，逐像素比較（例如在同一色彩模式下比較 `tobytes()`）確認與原始 bytes 的解碼結果相等。

manifest 的 `sourceImage` 應指向這份 canonical PNG，`sourceSha256`／`captureState.rawSha256` 應是 canonical PNG 的 hash；原始捕獲檔則用 provenance 保留，不拿它冒充 PNG：

```json
{
  "sourceImage": "raw/create-task.png",
  "sourceSha256": "<sha256 of canonical source PNG>",
  "captureProvenance": {
    "originalFile": "raw-original/create-task.capture",
    "originalMime": "image/jpeg",
    "originalSha256": "<sha256 of untouched original bytes>",
    "decodedSourceImage": "raw/create-task.png",
    "pixelEquality": "verified"
  }
}
```

`originalMime` 必須依 bytes 的實際格式判定；`pixelEquality: "verified"` 只能在完成解碼後的尺寸與像素比較時填入。validator 的 PNG/hash 檢查針對 `sourceImage` canonical PNG，不能取代這項 provenance 與像素相等性檢查。

## 唯讀驗證命令與邊界

在 DOCX 建置前，對**每一份** per-image manifest 執行：

```text
<bundled-python> "<skill>/scripts/validate_screenshot_manifest.py" --manifest "<qa>/create-task.json" --base-dir ".." --output "<qa>/create-task-manifest-validation.json"
```

`--base-dir` 是相對於 manifest 所在目錄的圖片根目錄；報告輸出必須是新檔，不能覆寫 manifest 或三張輸入圖片。工具驗證：

- source raw 的實際 SHA256 是否等於 `sourceSha256`，以及 `captureState.rawSha256` 是否相同；
- `originalImageSize` 是否等於 raw PNG 實際尺寸，raw／redacted／annotated 是否都是 PNG、檔案路徑不同且尺寸一致；
- 每筆 redaction、annotation、protected area bbox 是否為正值且完整落在 PNG 範圍；redaction 是否碰到 protected area；
- `sourceKind`、`captureKind`、annotation `id`／`caption`／`source`／status 和所有必填狀態是否存在且合法。

報告的 `geometry_status` 是上述機械幾何／hash 檢查，`manifest_status` 是加上宣告 review state 後的 manifest gate；`semantic_review` 固定為 `not_performed`。預覽資料可以有 `geometry_status: "pass"`，但只要仍 pending 就不能有 `manifest_status: "pass"`。工具不讀取影像像素、OCR、caption 內容或 UI 語意，輸出不回顯 caption、圖中文字、原始敏感值或任意路徑值。builder 仍必須直接檢視每一張 raw／redacted／annotated，並依 [independent-delivery-review.md](independent-delivery-review.md) 完成獨立交付審核；validator 的 pass 不能取代這兩道人工 gate。
