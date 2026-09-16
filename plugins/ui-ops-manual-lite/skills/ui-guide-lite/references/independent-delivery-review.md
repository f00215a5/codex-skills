# 獨立交付審核（輕量版）

在組檔後、正式交付前閱讀本規格。它把文件內容、圖片隱碼、操作語意、版面結構與證據新鮮度交給另一個 reviewer 核對；本版沒有 DOCX renderer，因此不要求也不宣稱逐頁渲染通過。

## Reviewer 與交付狀態

reviewer 必須是 builder 以外的人工或獨立執行者。`builder.id` 與 `reviewer.id` 必須明確且不同；JSON 中填一個新名字、讓 builder 自己改名或只靠腳本欄位，不能形成獨立審核。腳本只能檢查欄位、檔案與狀態值，不能替使用者驗證真實身分。

沒有 reviewer、reviewer 不能讀取圖片、需求證據或相關檔案，或任何必要證據缺失／過期時，狀態為 `blocked`。繼續完成不依賴 reviewer 的已授權工作；目前產物只能標為 draft，不得宣稱通過。輕量版不因缺少 renderer 自動 blocked：只要其餘適用檢查已完成，仍可正式交付。

## Review artifact

review JSON 至少包含下列欄位（完整可接受值以 `scripts/audit_delivery.py` 現行 schema 為準）：

```json
{
  "schema_version": 1,
  "artifact": {"sha256": "<final-docx-sha256>"},
  "builder": {"id": "builder:..."},
  "reviewer": {"id": "reviewer:..."},
  "reviewed_files": [
    {"kind": "image", "path": "annotated/step1.png", "sha256": "<sha256>"},
    {"kind": "support", "role": "build_manifest", "path": "manual.json", "sha256": "<sha256>"},
    {"kind": "support", "role": "requirements", "path": "requirements.json", "sha256": "<sha256>"},
    {"kind": "support", "role": "redaction_manifest", "path": "qa/redaction.json", "sha256": "<sha256>"},
    {"kind": "support", "role": "annotation_manifest", "path": "qa/annotation.json", "sha256": "<sha256>"}
  ],
  "checks": {
    "requirements": {"status": "pass", "reason": "...", "evidence": ["requirements.json"]},
    "redaction": {"status": "pass", "reason": "...", "evidence": ["annotated/step1.png", "qa/redaction.json"]},
    "operation": {"status": "pass", "reason": "...", "evidence": ["annotated/step1.png", "manual.json"]},
    "layout_structure": {"status": "pass", "reason": "...", "evidence": ["manual.json"]}
  },
  "render_visual": {"status": "out_of_scope", "reason": "輕量版沒有 DOCX renderer。"},
  "overall": "pass"
}
```

`reviewed_files` 的路徑相對於 review JSON 所在資料夾，且每筆都必須是實際存在的檔案並與 SHA-256 相符。支援檔案要以語義 role 或腳本現行支援的頂層 evidence 引用標示用途，不要靠檔名子字串猜測需求或 manifest。至少綁定：

- 最終 DOCX 的 `artifact.sha256`。
- DOCX 所有嵌入圖片的 hash；raw／未遮蔽圖片不可列為交付圖片。
- 最終 build manifest 與需求／需求 snapshot。
- 會影響圖片或操作內容的 redaction manifest、redaction provenance、annotation manifest 及其他相關證據。

四類 checks 固定為 `requirements`、`redaction`、`operation`、`layout_structure`。每一類要有 `status`、非空 `reason` 與只引用 `reviewed_files[].path` 的 `evidence`。`requirements` 與 `layout_structure` 不可填 `na`；`redaction` 或 `operation` 只有在本任務明確不含相應內容時才可填 `na`，並說明理由。圖片已嵌入時，`redaction` 與 `operation` 的 pass 必須有圖片 evidence。任何缺證據、無法核對或語意尚未完成都填 `blocked`，發現錯誤填 `fail`。

`render_visual.status` 只能填 `not_performed` 或 `out_of_scope`（另依腳本規格使用 `blocked`／`fail`），並提供原因；**不能填 `pass`**。`overall: "pass"` 只在 reviewer 確實完成、四類適用 checks 通過、artifact／所有 reviewed files hash 相符且 render_visual 仍明確在輕量版範圍外時使用。

## 執行順序

先產生機械結構報告：

```text
<venv>/bin/python "<skill>/scripts/audit_delivery.py" \
  --docx "<final.docx>" \
  --output "<qa>/structure.json"
```

reviewer 讀取需求、最終 DOCX、所有嵌入圖片、redacted／annotated 圖片與支持檔案，完成上面的 review JSON。再用不同輸出檔驗證其綁定：

```text
<venv>/bin/python "<skill>/scripts/audit_delivery.py" \
  --docx "<final.docx>" \
  --review "<qa>/review.json" \
  --manifest "<workspace>/manual.json" \
  --output "<qa>/review-validation.json"
```

檢查 `mechanical_status` 與 `independent_review.status`，不能只看 exit code；exit code 0 代表報告已寫出，不代表 DOCX、圖片或 review 自動通過。若 audit 提示 `manual_review`，由 reviewer 依實際文件與使用者已明示的版型例外判讀；不要把它靜默當作 pass。

## 四類核對內容

- `requirements`：需求範圍、目標畫面、版本依據（若有）與目前文件內容相符。
- `redaction`：實際檢視 redacted 圖，身分 ID、地址、保單號、帳單號、合約號等不可辨識；金額依使用者要求處理，預設可見。確認 raw 僅在受限區，沒有進入 DOCX 或交付包。
- `operation`：紅框、編號、caption、控制項與狀態相符；操作流程、欄位限制、成功影響、失敗／取消與操作後檢核均有證據。Pillow 或 DOM 結果只能作輔助。
- `layout_structure`：`verify_docx.py` 的章節、更新紀錄位置、清單重編、欄位表、圖片封裝與圖說關係，以及表格相對容器可用內容區置中、寬度／欄寬／縮排合理。這不是 DOCX 渲染結果。

文件、嵌入圖片、build／redaction／annotation manifest 或需求證據任何一項改動，都使受影響的 review 失效：重算 artifact 與相關 reviewed files hash，重新完成受影響 checks。不能只替舊 review 換 hash，也不必為未受影響的內容無故全部重寫。

交接紀錄固定列出六項並逐項附證據與狀態：**隱碼、標註、結構、獨立審核、證據雜湊、交付範圍**。renderer、權限、reviewer 身分與 fallback 狀態留在對話或外部 QA 紀錄，不寫入 DOCX。
