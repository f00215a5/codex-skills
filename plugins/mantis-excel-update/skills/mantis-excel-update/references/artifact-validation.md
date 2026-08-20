# Artifact 驗證契約與報告

本文件是 `scripts/validate_artifact.py` 的 contract、preflight snapshot、report 與 exit code 單一真相來源。只在建立／檢視契約，或解讀驗證報告時讀取。

## 執行時點與最小呼叫

Validator 只接受已 export/save 的 artifact 路徑。執行前必須釋放所有 workbook writer handle；writer 在獨立 process 時，必須等待該 process 結束。Validator 會以獨立的 raw OOXML reader 從磁碟重新開啟該檔案，不接受 writer 記憶體狀態。

從 skill 目錄執行：

```bash
python3 scripts/validate_artifact.py "<artifact.xlsx>" --contract "<contract.json>" --renderer auto --visual-verdict not-run
```

`--renderer auto` 只探測現有的 LibreOffice／`soffice`；不安裝 renderer。已確定環境沒有可用 renderer 時才使用 `--renderer none`，這會明示記錄真實渲染不可用。`--visual-verdict` 預設 `not-run`：僅在能實際檢視每個工作表、且已完成該檢視時才使用 `pass`；檢視發現問題時使用 `fail`。PDF 產出成功本身不是視覺檢視結果。

## Contract JSON

Contract 必須是單一 JSON object，`schema_version` 為 `1`。以下欄位必填：

| 欄位 | 契約 |
| --- | --- |
| `mapping.issues.sheet` | 已確認的問題單工作表名稱。 |
| `mapping.issues.header_row` | 正整數標題列。 |
| `mapping.issues.issue_id_column` | 已確認的問題單號欄位標題。 |
| `mapping.issues.status_column` | 已確認的狀態欄位標題。 |
| `mapping.issues.required_columns` | 非空白字串 array；每個標題在指定標題列必須唯一。 |
| `mapping.summary.sheet` | 已確認的摘要工作表名稱；輸出必須存在且可見，所有 `formula_cells` 都必須位於此工作表。 |
| `csv.path` | 本次已確認的 CSV 路徑。 |
| `csv.issue_id_column` | CSV 的問題單號標題。 |
| `csv.status_column` | CSV 的狀態標題。 |
| `status_groups` | Key set 必須剛好為 `in_progress`, `pending_release`, `resolved`, `unknown`；值為字串 array，且一個狀態不得出現在兩組。JSON key 順序不影響驗證。 |
| `expected_statistics` | Key set 必須剛好為 `in_progress`, `pending_release`, `resolved`, `unknown`, `total`；值為非負整數。JSON key 順序不影響驗證。 |
| `updated_range.sheet` | 必須等於 `mapping.issues.sheet`。 |
| `updated_range.range` | 從左上到右下的有效 A1 範圍；開始列必須在確認標題列之後，並覆蓋本次確認欄位與 CSV 問題單列。 |
| `preflight_snapshot.path` | 本次 preflight snapshot JSON 路徑。 |

`csv.path` 與 `preflight_snapshot.path` 的相對路徑都以 **contract JSON 所在目錄**解析。

Contract 的 mapping、status groups、statistics 與 range 必須來自本次使用者確認的 CSV 與作用中工作簿。`tests/fixtures/synthetic-*` 只是 schema 與測試資料，不是 production 的預設工作表、欄位、狀態 mapping 或統計值。

## Preflight snapshot JSON

Preflight snapshot 也必須是單一 JSON object，`schema_version` 為 `1`，並包含：

| 欄位 | 契約 |
| --- | --- |
| `sheet_order` | 非空白、不重複的工作表名稱 array，順序必須與預期輸出一致。 |
| `expected_output_view.active_sheet` | 預期交付時的作用中工作表。 |
| `expected_output_view.active_cell` | 該工作表預期選取的有效 A1 儲存格。 |
| `expected_issue_ids` | 預期輸出中的完整問題單號字串 array，包含 CSV 問題單與必須保留的既有非 CSV 問題單；不得空白、正規化後不得重複，筆數必須等於 `expected_statistics.total`。驗證會精確核對完整集合與顯示文字，因此前導零也是契約的一部分。 |
| `formula_cells` | 非空 object。每個命名 entry 都有 `sheet`, `cell`, `formula`；`cell` 是有效 A1 儲存格，`formula` 除了可選的開頭 `=` 外，必須與 persisted OOXML `<f>` 文字一致。五個基礎統計公式以 `statistic` 指向一個 `expected_statistics` key，且五個 key 各需剛好一次。其餘摘要公式（例如前次／本次異動比例）使用 numeric `cached_value` 指定預期快取；一個 entry 只能使用 `statistic` 或 `cached_value` 其中之一。所有儲存格座標不得重複。 |
| `source_artifacts` | 非空 array；每個 entry 包含 `path` 與 64 個十六進位字元的 `sha256`。至少必須以解析後的同一路徑及 digest pin 住 contract 的 `csv.path`；也列出本次需確認未被 validator 改動的其他來源／seed artifact。 |
| `preservation` | 有未授權保留範圍時必填。包含 `source_workbook`（更新前副本，且必須已列在 `source_artifacts`）、`protected_sheets`（唯一字串 array）、`preserve_rule_comments`（boolean）與 `forbidden_drawing_names`（唯一字串 array）。三種檢核至少啟用一種。`protected_sheets` 以來源／輸出間正規化的 worksheet 語義比較；`preserve_rule_comments` 比較去重後的 legacy/threaded `MANTIS_RULE_V1` 規則位置與 payload；`forbidden_drawing_names` 僅用於已確認應移除的浮動物件。 |

`source_artifacts[*].path` 的相對路徑以 **preflight snapshot JSON 所在目錄**解析，不是以 contract 或當前 working directory 解析。

## 固定 report schema

Validator 在有效呼叫時將 JSON report 寫到 stdout。Top-level keys 為：

| Key | 內容 |
| --- | --- |
| `schema_version` | `1` |
| `outcome` | `PASS`, `PARTIAL` 或 `FAIL` |
| `artifact` | 解析後的絕對 `path` 與 `sha256`；無法讀取 artifact 時 hash 可為 `null`。 |
| `layers` | 依序且剛好為 `data_correctness`, `visibility`, `formula_cache`, `rendering`。 |

每個 layer 的 keys 依序固定為：

1. `heading`：`data_correctness` 為「資料正確性」、`visibility` 為「可見性」、`formula_cache` 為「公式快取」、`rendering` 為「真實渲染」。
2. `status`：`data_correctness`、`visibility`、`formula_cache` 只有 `PASS|FAIL`；`rendering` 可為 `PASS|FAIL|NOT RUN`。
3. `summary`：包含 `checks`, `passed`, `failed`, `not_run` 計數。
4. `evidence`：array；每個 entry 依序包含 `check`, `status`, `source`, `expected`, `actual`，其 `status` 為 `PASS|FAIL|NOT RUN`。
5. `reasons`：失敗或未執行原因的字串 array。

以 layer key 與 `status` 做程式判斷；`heading` 是人類可讀標籤。

## Outcome 與 exit code

| Outcome | Exit | 語意 |
| --- | ---: | --- |
| `PASS` | `0` | 四個 layers 均為 `PASS`，包含已明確記錄的實際視覺檢視；可稱 artifact 獨立驗證完整成功。 |
| `PARTIAL` | `2` | 前三個 layers 為 `PASS`，`rendering` 為 `NOT RUN`。代表非視覺的檔案驗證已通過，但 renderer 或視覺檢視未完成；只能回報已通過的範圍與限制，不得稱完整成功。 |
| `FAIL` | `1` | 任一 layer 為 `FAIL`。從該 layer 的 `reasons` 與 `evidence` 找出原因，修正產出 artifact 的流程後重跑。 |
| CLI usage error | `64` | 參數缺少、選項無效等呼叫錯誤；這不是 artifact 驗證 outcome。 |

## 四層範圍與安全邊界

- `data_correctness`：用獨立 raw OOXML 讀取結果核對 CSV、確認欄位、`expected_issue_ids` 的完整問題單集合與顯示文字（含前導零）、狀態分類、預期統計與 source hashes。若 contract 有 `preservation`，同一層也會以來源工作簿比較未授權工作表的值、公式、可見性、列欄尺寸、篩選、合併、驗證與 view；比較會把 cell／row／column 的 style ID 轉成 cell-XF 描述，避免純 style ID 重編造成假陽性。它也會比對版本化規則備註，並檢查已確認禁止的 drawing 名稱不存在。
- `visibility`：核對工作表順序、摘要與作用中工作表是否可見、作用中儲存格的 `activeCell`/`sqref`，以及 `tabSelected` 不得衝突（可沒有 selected sheet，或只能是作用中工作表）、問題單工作表、標題列與所有 populated issue rows 的有效可見性與總數，以及每個 required column 存在、未隱藏且有效欄寬（含 `defaultColWidth`）大於零。含標題或 issue cells 的 explicit `<row>` 在沒有 `hidden=true` 且有效列高大於零時可見；有 row-level `ht` 時以它為準，否則才使用已宣告的 `sheetFormatPr.defaultRowHeight`。`sheetFormatPr.zeroHeight` 只預設隱藏未寫出／unused rows，不會否定上述 explicit row 例外；contract 沒有可豁免 populated issue row 的例外。
- `formula_cache`：核對 preflight 列出的公式都位於確認摘要工作表、公式文字與儲存快取；基礎統計會同時比對 `expected_statistics`，其餘已確認公式以 `cached_value` 比對。快取必須是 OOXML 數值型別，空白、錯誤、文字、非數字或過期快取都失敗。
- `rendering`：`auto` 只使用現有 LibreOffice，將 artifact 複製到臨時目錄，使用隔離的臨時 profile 產生 PDF。PDF 檔案大小大於零只會證明 renderer 執行成功；還必須有 `--visual-verdict pass` 的實際逐工作表檢視，layer 才是 `PASS`。臨時副本與輸出會刪除，不回存原 artifact；`none` 則明示記錄 renderer 不可用。

Validator 是唯讀驗證器：不建立 workbook writer，不修復或改寫 hidden/view/formula/cache，也不修改來源檔、seed 或待驗證 artifact。需修正時，回到 workbook authoring 流程完成修正與 save/close，再對新的 persisted artifact 重跑。

Raw OOXML reader 會在讀取任何 part 前拒絕重複的 ZIP entry 名稱，並限制 ZIP entry 數與總解壓縮大小。每個 XML part 會先依 ZIP metadata 檢查大小，再以 bounded stream 讀取，最後才解析；parse 前仍會拒絕 DTD／entity 宣告。驗收 artifact 不得依賴重複 OOXML part、DTD 或 entity expansion。

待驗證 artifact 路徑必須與 `source_artifacts` 中每個來源／seed 路徑不同；同一路徑會使 `data_correctness` 失敗。

資料正確性、可見性、公式快取是必做的、完全不依賴視覺化能力的三層驗證。Rendering 是補強層而不是唯一檢核：沒有 Spreadsheets 或視覺化能力時，仍可使用 runtime 當下可用的 writer 產出工作簿，再安全地執行前三層並得到 `PARTIAL`；不可偽稱完整視覺驗證成功。writer 不在 validator 的信任邊界內：無論實際使用何種工具寫入，都必須保留來源副本、關閉 writer 後回讀輸出 artifact，並通過 contract 的資料、可見性、公式快取與保留範圍檢查。

`rendering: PASS` 代表 renderer 已產生非空 PDF，且呼叫者已明確記錄 `--visual-verdict pass`；沒有該 verdict 時，一律為 `NOT RUN`，即使 PDF 存在。這個 verdict 不是由檔案大小推論，不能取代 Spreadsheets skill 要求的逐工作表檢視；contract 未列出的格式、註解、drawing 與其他交付要求也仍需依主流程驗證。

## 測試

從 repository root 執行：

```bash
python3 plugins/mantis-excel-update/skills/mantis-excel-update/tests/run_tests.py
```
