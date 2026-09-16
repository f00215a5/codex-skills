# 文件結構與結構驗證（輕量版）

將此基線套用到沒有既有範本的繁體中文系統 UI 操作說明書；既有範本優先。此基線為唯讀預設：使用者要求調整時，先建立**可追溯的新版本副本**並記錄基線版本與偏離項目，不覆寫原始基線。輕量版沒有 DOCX renderer；本文件定義可由 Python 檢查的結構與幾何，不能把結構通過當成開啟後的視覺通過。

## 首頁順序（由 build_docx.py 強制）

1. **標題區塊**：置中深青綠標題；下一行為副標題；下一行為「適用畫面」。標題描述功能，不使用專案或 release 的預設名稱。
2. **更新紀錄**：緊接標題區塊，以單一表格呈現「版本｜日期｜更新內容」，依 manifest 中的 `updateLog` 順序由舊至新排列；不可散落在各章節。
3. **修訂狀態**：一行小型表格「文件版本｜日期｜本次修訂摘要」。
4. **版本依據**：僅在 build manifest 提供 `versionBasis` 時出現；沒有來源時整段省略。
5. **使用提醒**：淡青綠底色段落，說明畫面資料與截圖處理原則、紅框／編號意義、敏感資訊遮蔽要求。
6. **共通操作規則**：項目符號清單，說明必填記號、查詢／重設、下載、確認提示與權限／資料狀態差異。

## 內文規則

- 頁面為 Letter 直式：左右 0.65 in、上 0.67 in、下 0.59 in。
- 正文 live text 設定明確的 CJK 字型名稱（manifest 的 `fontName`）與 `zh-TW` 語言標記；標題／章標為深青綠，表格標頭為淡青綠，警示與點擊標註為紅色。
- 每個操作小節的步驟清單**獨立從步驟 1 起算**（`build_docx.py` 為每小節建立新的 numId）。紅框編號只用於**同張圖內**的控制項對照，不同圖的紅框編號可以重複，不得把圖號當成操作步驟號。
- 欄位／按鈕表至少四欄：欄位或控制項、定義、必填、限制／選項；有顯示條件時加第五欄「顯示條件／結果」。
- 所有表格預設相對於所在容器的**可用內容區置中**。`build_docx.py` 必須明確設定 `CENTER`、直接 `w:jc w:val="center"` 與 `autofit`；總寬、欄寬與列高依內容彈性調整，不固定像素，也不要求填滿頁面。
- 若表格較窄，左右剩餘空間應大致相等；只有使用者或明確版型要求靠左／靠右時才改用其他對齊。合法窄表不可因模板或函式庫預設變動而靠左。

## Build manifest 摘要

全部欄位見 `scripts/build_docx.py` 的 docstring。要點：圖片路徑相對於 manifest 所在資料夾（或 `baseDir`）；每個操作小節有一組 `steps`（`caption` 為步驟文字兼圖說）、`fields`、`impact`（修改成功後的影響）、`verification`（操作後檢核）、可選的 `preconditions` 與 `failure`（失敗／取消行為）。`updateLog` 由舊至新排列。

## 驗收標準

`verify_docx.py` 對產出 DOCX 逐一檢查下列項目，全部通過才算完成：

| 類別 | 檢查項目 |
| --- | --- |
| 套件完整性 | 含 `word/document.xml`、`word/numbering.xml`；每張嵌入圖的 relationship target 存在 |
| 頁面設定 | Letter、邊界符合基線 |
| 章節順序 | 更新紀錄→修訂狀態→使用提醒→共通操作規則→章節… |
| 步驟編號 | 每個操作小節的步驟清單只使用單一 numId（獨立重編） |
| 欄位表 | 每個操作小節有含「欄位或控制項」「定義」「必填」的表 |
| 更新紀錄 | 標題區塊後的第一張表，欄位為版本、日期、更新內容，且有資料列 |
| 圖與圖說 | 每張圖後接非空圖說；含「紅框 N」的圖說其編號序列與 build manifest 的步驟順序一致 |
| 表格幾何 | 表格有明確 center 對齊、寬度／欄寬／縮排可落在容器可用內容區；`autofit` 保留內容彈性；合法窄表不因預設值漂移到靠左 |

`verify_docx.py` 驗證 DOCX 結構與封裝；`audit_delivery.py` 另讀取 OOXML 的表格對齊、寬度、欄位網格與媒體 hash。若發現 `table_alignment_not_center` 或表格幾何為 `manual_review`，先修正能確定的設定；動態表格、合併儲存格或無法機械判斷的合法例外，由獨立 reviewer 依需求及版型證據記錄，不要靜默忽略。

### 執行結果回報（對話限定）

- 本版僅以本地 Python venv 建檔與驗證，**不需要外部文件引擎**；`verify_docx.py` 的 exit code 0 只代表其檢查的結構與封裝項目通過。`audit_delivery.py` 的 exit code 0 只代表報告寫出，仍須查看 `mechanical_status` 與 `independent_review.status`。
- 交付前依 [independent-delivery-review.md](independent-delivery-review.md) 由非 builder reviewer 核對需求、redacted／annotated 圖片、所有嵌入媒體、build manifest 與相關證據 hash。review 四類 checks 為 `requirements`、`redaction`、`operation`、`layout_structure`；沒有 reviewer 或無法看圖時，適用項目為 `blocked`，產物只能標示 draft。
- `render_visual` 固定記為 `not_performed` 或 `out_of_scope` 並附原因，不得填 `pass`。在其餘適用檢查與 hash 綁定有效時，輕量版仍可正式交付；需要逐頁視覺渲染時改用完整版 `$ui-guide`。
- 對話中向使用者回報開啟後仍需確認的字型取代、分頁斷行與圖片縮放等視覺結果。這類回報**不得寫入 DOCX**；交付文件只保留使用者確認的操作內容。
- 使用者需要渲染驗證時，應改用完整版 `$ui-guide`。
