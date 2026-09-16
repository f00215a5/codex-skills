# 獨立交付審核規範

在準備交付或宣稱 UI 操作說明書完成前閱讀本規格。審核是產製（builder）之後的獨立關卡；產製者留下的 `verified`、`checked` 或自評 checklist 只能作為線索，不能作為通過依據。

## 審核者與輸入

可用獨立子代理時，交由未參與本次文件產製的 reviewer 讀取並檢查；reviewer 不得參與本次文件產製，且它讀取的內容與產製者分開提供。無法使用獨立 reviewer 時，明確記錄 **`independent review pending`**，不能填寫假身份或把 pending 當成 pass。應持續完成所有不依賴 reviewer 的已授權工作；若暫時交付目前產物，可在檔名、資料夾或交付對話清楚標示 `draft`，不能宣稱已完成審核。

reviewer 直接讀取下列輸入：

- 使用者需求、已確認的範圍與目前 `ui-guide` 規範。
- 最終 DOCX 與其最終 renderer 產生的頁面圖片。
- 交付文件中使用的 redacted／annotated 圖片及其 manifest。
- 受限 QA 工作區的原始證據，用來比對來源與遮蔽完整性。

原始圖片可供 reviewer 在受限工作區讀取，但不得複製到交付封裝、DOCX 或 review artifact 內容；敏感原值不得出現在 caption、替代文字、metadata、檔名或報告文字。報告只寫不含原值的類別、雜湊、檔案識別與定位資訊。

## 四類檢查

每一類都要有 `status`、`reason` 與 `evidence`。`status` 只能是 `pass`、`fail`、`blocked` 或 `na`；`na` 只在該要求明確不適用時使用，並在 `reason` 說明原因。

| 檢查 | reviewer 要直接確認的內容 |
| --- | --- |
| `requirements` | 需求、範圍、章節順序、入口、步驟、欄位表、成功影響與操作後檢核是否完整且相符。 |
| `redaction` | 實際畫面來源是否適用；身分 ID、地址、保單號、帳單號、合約號等預設敏感值是否逐一遮蔽；金額是否依預設保留或依明示要求遮蔽；欄名與操作目標仍可辨識。 |
| `visual` | 最終頁面中的字型、標題層級、表格與圖片相對關係、表格在容器可用內容區的置中、分頁、裁切與圖說是否符合視覺標準。 |
| `operation` | 每個紅框／編號／caption 是否指向正確控制項；步驟、畫面狀態、成功／失敗／取消行為與檢核方式是否可按實際畫面完成。 |

reviewer 依原始證據和成品逐項判斷，不把 OCR、像素差異、DOCX 結構或腳本 exit code 當成隱碼或視覺 pass 的替代品。發現任何一項 `fail` 時，overall result 為 `fail`；證據不足或無法檢視時為 `blocked`，不可用猜測補成 `pass`。

## 必測的回歸紅案例

下列情境直接判為紅（`fail` 或 `blocked`），用來攔下已知的產製偏差：

| 情境 | 判定 |
| --- | --- |
| 沒有使用者明示卻以重繪／生成 UI 取代實際截圖 | `redaction` 或 `requirements` 為 `fail`。 |
| 身分 ID、地址、保單號、帳單號或合約號在成品中可讀 | `redaction` 為 `fail`；金額依預設保留本身不是失敗。 |
| 表格寬度依內容變動，但仍以容器可用內容區置中 | `visual` 通過；產製器變動造成表格靠左則 `visual` 為 `fail`。 |
| builder 宣稱 `verified`、舊 artifact 或任一 reviewed file hash 與現檔不符 | `overall` 不得為 `pass`；證據不足或 reviewer 尚未完成時為 `blocked`。 |

## Review artifact schema

每次審核在 DOCX 之外保存一份 review artifact。artifact 本身不包含原始圖片或敏感值；`reviewed_files[].path` 使用相對於 review JSON 所在目錄的路徑，且不含敏感值。所有 `sha256` 都是實際讀取檔案後計算，不由產製者口頭聲稱。各任務使用同一個最小 schema，方便腳本驗證欄位與 hash。

```json
{
  "schema_version": 1,
  "artifact": {
    "sha256": "<sha256-of-final-docx>"
  },
  "builder": {
    "id": "builder:<task-or-session-id>"
  },
  "reviewer": {
    "id": "reviewer:<independent-agent-or-human-id>"
  },
  "reviewed_files": [
    {
      "kind": "page",
      "path": "render/page-001.png",
      "sha256": "<sha256-of-page>"
    },
    {
      "kind": "image",
      "path": "evidence/redacted-001.png",
      "sha256": "<sha256-of-image>"
    },
    {
      "kind": "support",
      "path": "evidence/requirements.md",
      "sha256": "<sha256-of-support-file>"
    }
  ],
  "checks": {
    "requirements": {
      "status": "pass",
      "reason": "已逐項比對確認範圍與文件章節",
      "evidence": ["evidence/requirements.md"]
    },
    "redaction": {
      "status": "pass",
      "reason": "敏感類別已遮蔽且未在成品文字或圖片中回顯",
      "evidence": ["evidence/redacted-001.png"]
    },
    "visual": {
      "status": "pass",
      "reason": "頁面與表格相對於容器內容區的版面通過檢視",
      "evidence": ["render/page-001.png"]
    },
    "operation": {
      "status": "pass",
      "reason": "紅框、caption、步驟和畫面狀態相符",
      "evidence": ["evidence/redacted-001.png"]
    }
  },
  "overall": "pass"
}
```

`reviewed_files[].kind` 僅使用 `page`、`image` 或 `support`；`page` 必須列出最終 renderer manifest 的每一頁，`image` 必須列出成品嵌入的每一張圖片（有 raw／redacted 證據時也列其實際檔案），`support` 至少列需求 snapshot，必要時列 manifest 或規範；**每一筆** `reviewed_files` 都必須有與實際檔案相符的 hash。`evidence` 只引用 `reviewed_files[].path` 的完整相對路徑，定位或頁內說明寫在 `reason`，不要加入未列出的 `artifact:` 或帶 fragment 的別名。`builder.id` 與 `reviewer.id` 是紀錄欄位，不是由腳本證明的身分驗證機制；腳本只能驗證欄位存在、檔案雜湊、列舉項目與狀態值。`checks` 固定包含 `requirements`、`redaction`、`visual`、`operation` 四個鍵，每個值固定包含 `status`、`reason`、`evidence`。

`requirements` 與 `visual` 是 UI 操作說明書的必要檢查，不得填 `na`；`redaction` 與 `operation` 只有在使用者明確確認該任務不含相應畫面或操作時才可填 `na`，並在 `reason` 留下依據。至少要有一個 `page`；只要 DOCX 內嵌圖片，就必須列出每張 `image`。

### Pending 與結果規則

- `overall: "pass"`：reviewer id 已填入，四項適用檢查均為 `pass` 或有明確 `na`，artifact 與所有 `reviewed_files` hashes 相符。
- `overall: "fail"`：任一檢查為 `fail`，或驗收後發現成品仍含敏感值、錯誤標註或版面缺陷。
- `overall: "blocked"`：reviewer 尚未完成、原始證據不可讀、必要頁面／圖片缺失或任一雜湊無法比對。無 reviewer 時將 `reviewer.id` 設為 `pending`，並在報告及交付對話寫明 `independent review pending`。
- 審核 pending 時，應持續完成所有不依賴 reviewer 的已授權工作；若需要交付目前產物，將檔名、資料夾或交付對話清楚標示 `draft`。`draft` 是交付狀態，不是 `overall` 值，也不得宣稱已完成審核。

交付文件或任一 `reviewed_files`（`page`、`image`、`support`）改動後，重新計算 artifact 與所有 reviewed files hashes，受影響檢查回到 `blocked` 或待審核狀態，再由 reviewer 重跑。不要沿用舊 artifact 的 `pass`。

## 人工與程式檢查邊界

使用 [audit_delivery.py](../scripts/audit_delivery.py) 產生唯讀結構報告，再交給 reviewer 與其他證據一起判讀：

```text
<bundled-python> "<skill>/scripts/audit_delivery.py" --docx "<final.docx>" --output "<qa>/structure.json"
```

reviewer 完成上述 review JSON 後，再檢查紀錄與檔案是否一致：

```text
<bundled-python> "<skill>/scripts/audit_delivery.py" --docx "<final.docx>" --review "<qa>/review.json" --output "<qa>/review-validation.json"
```

第二次輸出使用不同檔名，不能覆寫已被 review JSON 引用及計算雜湊的 `structure.json`。工具的 `mechanical_status` 表示結構檢查結果，`independent_review.status` 表示審核紀錄的完整性與檔案綁定檢查；兩者都不等於工具親自完成內容或視覺審核。`manual_review` 項目交由 reviewer 判讀，`failed` 項目需修正，或由 reviewer 核實是否屬使用者／版型已明示的合法例外並記錄依據。例如動態表寬與合法合併儲存格不應僅因無法機械判定就永遠卡住交付。

正式交付由 reviewer 綜合需求及全部 findings 作成結論；不得僅因腳本 exit code 0 或紀錄驗證 `pass` 就宣稱完成。所有頁面是否齊全、是否與最終 DOCX 的 render manifest 相符，仍由 reviewer 核對。

程式可檢查 DOCX 是否能開啟、章節／表格／圖片是否存在、表格對齊屬性、包裝內容、雜湊和 schema；它不能證明 reviewer 身分真實，也不能單獨證明圖片中識別資料已不可辨識、紅框語意正確或渲染視覺可讀。人工或獨立 reviewer 對內容的直接檢視才是這些判斷的 evidence。review environment、工具版本、權限與 fallback 結果留在對話或外部審核紀錄，**不得寫入 DOCX**。
