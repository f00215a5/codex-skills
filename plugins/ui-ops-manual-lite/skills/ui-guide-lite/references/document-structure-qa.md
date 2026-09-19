# 文件結構與結構驗證（輕量版）

將此基線套用到沒有既有範本的繁體中文系統 UI 操作說明書；既有範本優先。此基線為唯讀預設：使用者要求調整時，先建立**可追溯的新版本副本**並記錄基線版本與偏離項目，不覆寫原始基線。輕量版沒有 DOCX renderer；本文件定義可由 Python 檢查的結構與幾何，不能把結構通過當成開啟後的視覺通過。版面細節另見 [default-document-layout.md](default-document-layout.md)。

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
- 每個操作小節的步驟清單**獨立從步驟 1 起算**（`build_docx.py` 為每小節建立新的 numId）。紅框編號只用於**同張圖內**的控制項對照，不同圖的紅框編號可以重複，不得把圖號當成操作步驟號。`verify_docx.py` 只分析有編號內容的非空區段；空的 Heading 2 或每節內容是否完整仍須由 DOCX 讀回與 reviewer 核對。
- 文件規範要求每個操作小節提供至少四欄：欄位或控制項、定義、必填、限制／選項；有顯示條件時加第五欄「顯示條件／結果」。目前 `verify_docx.py` 只能機械確認全文件至少有一張表的表頭含「欄位／控制項」，並確認該表有「定義」與「必填」欄，不能以 exit 0 證明每節都有完整四欄，需由 DOCX 讀回與 reviewer 補核。
- 所有表格預設相對於所在容器的**可用內容區置中**。`build_docx.py` 必須明確設定 `CENTER`、直接 `w:jc w:val="center"` 與 `autofit`；總寬、欄寬與列高依內容彈性調整，不固定像素，也不要求填滿頁面。
- 表格總寬、`tblGrid` 欄寬總和與每列 `tcW` 必須一致，且不得超過 section 扣除左右 margin 的容器可用寬；固定列高／固定像素高度和超出容器的圖片／表格是結構風險，不用內容縮小掩蓋。
- 圖片若由 manifest 指定 `display.width`／`display.height`，必須正值、保持來源比例並落在容器可用寬高；預設最大高度只是可機械攔截的版面風險門檻，不是實際分頁或可讀性保證。
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
| 欄位表 | 全文件至少有一張表頭含「欄位或控制項」的表，且該表含「定義」「必填」；每節是否都有完整四欄由 DOCX 讀回／reviewer 核對 |
| 更新紀錄 | 標題區塊後的第一張表，欄位為版本、日期、更新內容，且有資料列 |
| 圖與圖說 | 每張圖後接非空段落；至少一個圖說可擷取「紅框 N」，使用 `--manifest` 時擷取到的紅框號碼序列與 manifest 中有紅框號碼的圖片順序一致；不證明每張圖的 control id 或語意相符 |
| 表格幾何 | 表格有明確 center 對齊、寬度／欄寬／縮排可落在容器可用內容區；`autofit` 保留內容彈性；合法窄表不因預設值漂移到靠左；固定列高或超寬欄網格須失敗／人工覆核 |
| 圖片幾何 | 每張嵌圖 relationship target 存在；顯示寬高正值、比例一致且不超出容器；不把超高圖縮到不可讀 |
| Numbering | 每個有編號內容的操作區段使用獨立 `abstractNum`／`num`、唯一 `nsid`／id、有效引用與 `startOverride=1`；不能以普通文字 `1.` 代替；空區段與實際流程完整性仍需讀回／reviewer 核對 |

`verify_docx.py` 驗證 DOCX 結構與封裝；`audit_delivery.py` 另讀取 OOXML 的表格對齊、寬度、欄位網格、嵌圖尺寸與媒體 hash。若發現 `table_alignment_not_center`、超寬／超高、固定列高、numbering 定義錯誤或表格幾何為 `manual_review`，先修正能確定的設定；動態表格、合併儲存格或無法機械判斷的合法例外，由獨立 reviewer 依需求及版型證據記錄，不要靜默忽略。

build 後要讀回真正 DOCX，檢查主要流程文字、表格／圖說順序、所有嵌入圖片 relationship、媒體 hash 和 manifest 對應。Pillow 的實際嵌圖尺寸 preview 可輔助直接看圖，但只證明內容預覽；不證明 Word 分頁、字型替代、換行或最終視覺 pass。

### 執行結果回報（對話限定）

- 本版僅以本地 Python venv 建檔與驗證，**不需要外部文件引擎**；`verify_docx.py` 的 exit code 0 只代表其檢查的結構與封裝項目通過。`audit_delivery.py` 的 exit code 0 只代表報告寫出，仍須查看 `mechanical_status` 與 `independent_review.status`。
- 交付前依 [independent-delivery-review.md](independent-delivery-review.md) 由非 builder reviewer 核對需求、redacted／annotated 圖片、所有嵌入媒體、build manifest 與相關證據 hash。review 四類 checks 為 `requirements`、`redaction`、`operation`、`layout_structure`；沒有 reviewer 或無法看圖時，適用項目為 `blocked`，產物只能標示 draft。
- `render_visual` 固定記為 `not_performed` 或 `out_of_scope` 並附原因，不得填 `pass`。在其餘適用檢查與 hash 綁定有效時，輕量版仍可正式交付；需要逐頁視覺渲染時需另選具備 renderer 的工作流程，本版不安裝或呼叫 Documents、Word 或 LibreOffice。
- 對話中向使用者回報開啟後仍需確認的字型取代、分頁斷行與圖片縮放等視覺結果。這類回報**不得寫入 DOCX**；交付文件只保留使用者確認的操作內容。
- 使用者需要渲染驗證時，需另行選擇具備 renderer 的工作流程；不得把本版內容 preview 寫成 renderer pass。
