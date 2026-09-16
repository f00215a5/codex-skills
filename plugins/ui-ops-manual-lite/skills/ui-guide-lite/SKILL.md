---
name: ui-guide-lite
description: Use when creating or revising a 系統 UI 操作說明書, user manual, or DOCX guide that needs screen captures, annotated controls, field definitions, operation steps, release-aware evidence, and a Python-only document workflow.
---

# UI 操作說明書（輕量版）

建立可操作、可驗證的系統 UI 說明書。先確認畫面範圍與預設模板；用實機和來源證據描述畫面，而不是猜測控制項或後續影響。本版**僅依賴 Python 與本地 venv**（python-docx、Pillow）建立 DOCX、處理圖片與完成結構 QA，**不需要外部文件引擎**。本版沒有 DOCX renderer；渲染結果與限制只在對話中回報，不加入交付文件。即使不做 DOCX 渲染，隱碼、標註語意、文件結構與獨立交付審核仍是獨立關卡。

## 新任務第一輪回覆（強制）

對**每一個新建或修訂** UI 操作說明書的任務，無論使用者資訊看似是否完整，第一輪回覆都**必須先**輸出下列「預設範圍確認」表單，並明確要求使用者確認或改寫。不可只在資訊不足時才詢問；不可先開始擷取、登入、寫入系統或建立交付檔。

只有使用者在**目前任務**明確表示「略過範圍確認並接受既有預設」時，才可略過表單；仍須回覆已採用的預設範圍。

### 預設範圍確認（首次回覆的固定格式）

先輸出以下內容。使用者可修改、新增或移除任一項：

> **預設範圍確認**
>
> 1. 是否願意提供**前端 repository**（可選）？請提供 URL／本機路徑及 branch、tag 或 commit；若不提供，將僅以實機 UI 取證。
> 2. 是否願意提供**後端 repository**（可選）？請提供 URL／本機路徑及 branch、tag 或 commit；若不提供，將不做後端版本推論。
> 3. **目標畫面**：請提供 URL／路徑清單或上傳清單；不自行猜測畫面範圍。
> 4. **交付**：請確認文件名稱、初始版本與交付資料夾。
> 5. **截圖與操作流程**：每個畫面預設包含側邊欄入口與到達路徑、主要操作流程、如何操作介面，以及介面選項說明。
> 6. **UI 說明**：預設說明每個可互動的欄位、icon、按鈕與可見狀態；每個填入欄位附欄位定義、是否必填與參數限制。
> 7. **互動標註**：每個明確點擊或輸入動作，預設以紅色方框和編號標示，必要時加游標 icon 指向目標。
> 8. **成功影響與驗證**：預設說明資料異動後的影響與檢核方式；交付前以 `verify_docx.py` 結構驗證，本版不做渲染驗證。
> 請回覆「接受預設」或逐項告訴我修改內容。

使用 `request_user_input`（可用時）或簡短自由文字提問取得確認；不得把第 1、2 項隱藏在未說明用途的選項中。即使使用者已提供部分資訊，也要在表單中回填已知內容並讓使用者確認其餘預設。

## 初始化必問

首次表單中必須逐字主動詢問「是否願意提供**前端 repository**？」與「是否願意提供**後端 repository**？」；兩者均為**可選**，不提供不阻礙以實機 UI 製作手冊。

- 前端 repository／tag：用來找出新增或修改畫面、路由和互動規則，提出候選畫面後請使用者確認。
- 後端 repository／tag：用來確認資料儲存、成功後影響、鎖定條件與錯誤回饋；不得用後端名稱推測不存在的 UI。
- 只提供其中一方時，僅將它當作可驗證證據；未提供時省略對應版本推論。

## 預設範圍確認

在擷取畫面或撰寫前，依「新任務第一輪回覆」輸出固定表單，並用下列預設項目讓使用者確認、增列、移除或修改。未取得確認時，不開始產製。

| 項目 | 預設 | 需要確認的資訊 |
| --- | --- | --- |
| 前端 repository | 可選 | 是否願意提供 URL／本機路徑與 branch、tag 或 commit？ |
| 後端 repository | 可選 | 是否願意提供 URL／本機路徑與 branch、tag 或 commit？ |
| 目標畫面 | 必要 | 請提供**目標畫面 URL／路徑清單**，或**上傳清單**。未提供時先索取，勿自行猜測。 |
| 截圖 | 啟用 | 每個畫面含側邊欄入口、主要**操作流程**與**介面選項說明**。 |
| UI 覆蓋 | 啟用 | 說明**所有可互動**欄位、icon、按鈕與可見狀態；填入欄位附欄位定義、是否必填、參數限制。 |
| 標註 | 啟用 | 點擊或輸入處以**紅色方框**和編號標示；必要時加游標 icon。 |
| 成功影響 | 啟用 | 每一項會改變資料的操作，均說明**修改成功後的影響**與檢核方式。 |
| 交付 | 必要 | 文件名稱、初始版本與**交付資料夾**。未提供時詢問，勿將檔案寫到未授權位置。 |
| 結構驗證 | 啟用 | 組檔後以 `verify_docx.py` 驗證結構與 manifest 形式對應；內容語意另由獨立 reviewer 核對，視覺驗證範圍於對話回報。 |

同時確認登入／測試資料的授權範圍。只用於取證；遮蔽密碼、權杖、個資與不應外流的業務資料。遇到會寫入、送出、刪除或觸發排程的 UI 動作，先取得當下確認。

## 初始化：venv（一次性）

首次使用本技能時，建立並安裝相依套件（僅 python-docx、Pillow；都是 Python 套件，無任何系統工具）：

```text
python3 "<skill-path>/scripts/bootstrap.py"
```

預設 venv 位於 `~/.codex/venvs/ui-ops-manual-lite`；bootstrap 為冪等操作，可重複執行。之後**所有**本技能的腳本都用該 venv 的 python 執行：`<venv>/bin/python "<skill>/scripts/<script>.py" ...`。不得改用系統 pip 全域安裝，也不得在任務中臨時建立其他 venv。

腳本測試（skill 目錄下）：

```text
<venv>/bin/python -m unittest discover -s . -v
```

## 取得目標與版本依據

1. 以使用者提供的 URL／清單為準。若沒有清單，先請使用者提供，不以選單名稱推測範圍。
2. 若提供**前端 repository 或 tag**，閱讀變更與路由／頁面元件，找出可能的**前端新增／修改畫面**；提出候選 URL／畫面清單並**請使用者確認**後才納入手冊。若另提供後端 repository 或 tag，僅用其確認資料異動與下游影響。
3. 若只提供 repository，詢問比較基準；若只提供 tag，確認可用的來源與比較對象。將版本、日期、commit 或 release note 僅寫入可驗證的事實。
4. **不提供 repository 或 tag**時，照樣以 UI 實機取證製作手冊，但**省略版本依據**章節與任何版本推論。

不要採用任何特定專案的 release 工作流；這是通用技能。

## 擷取與說明

每個目標畫面建立一份**覆蓋清單**，再寫入文件。對每個互動元素記錄：名稱／icon、用途、觸發結果、顯示或可用條件、欄位定義、是否必填、格式與參數限制、錯誤或成功回饋。無法從 UI 或來源確認時標為「待確認」，不要捏造限制。

每個操作流程使用下列順序：

1. 側邊欄／導覽入口截圖和到達路徑。
2. 操作前置條件與可修改／鎖定條件。
3. 主畫面操作截圖，按實際順序列步驟。
4. 填寫或選擇欄位的說明表。
5. 成功、失敗、取消／關閉行為與**修改成功後的影響**。
6. 操作後檢核。

**各操作小節獨立使用步驟編號，從步驟 1 開始**；不要讓新章節延續成「步驟 25」。圖說的紅框編號與同張圖的標註一致，不要把圖號當成操作步驟號。

截圖先取原始證據，再產生遮蔽與標註副本。若同一畫面有多個動作，使用較少但可讀的截圖，不要用一張過度標註的全景圖取代流程。

## 來源與隱碼

截圖預設保留實際系統畫面；只有使用者明確要求示意圖、重繪圖或簡化圖時，才可對指定範圍使用 `schematic`。每張圖記錄 `sourceKind`：`captured`、`provided`、`reused` 或獲明示核准的 `schematic`。無法取得適用的實際畫面時，標為待補證據或 draft，不自行重繪後冒稱為 screenshot。詳細範圍見 [references/screenshot-redaction-policy.md](references/screenshot-redaction-policy.md)。

預設遮蔽姓名、身分 ID、客戶／會員／員工 ID、地址、電話、電子郵件、保單號、帳單號、合約號、交易／案件識別碼、密碼、權杖、API key、session 值及不應外流的內部帳號。**金額預設保留**；只有使用者或資料政策明確要求時才列入遮蔽。不得以抽象圖代替精準遮蔽，也不得把敏感原值寫入 manifest、caption、檔名或交付包。

固定採「raw → redacted → annotated → DOCX」順序。用 `redact.py draw` 以不透明色塊（`opaque-rectangle`）或像素化（`pixelate`）精準覆蓋敏感區域，保留來源與輸出 SHA-256；再以 `redact.py check --require-checked` 作為證據關卡。raw 僅存於受限 QA 工作區，不能嵌入 DOCX 或交付。座標／雜湊檢查只能證明列出的矩形與檔案相符，不能證明已找出所有敏感值；這仍須由能直接看圖的獨立 reviewer 核對。

## 標註

對每張要標註的遮蔽後截圖建立一份標註 manifest（JSON），內容與格式見 [references/annotation-qa.md](references/annotation-qa.md)。座標從 DOM 邊界按比例換算，人工操作只做微調，並記錄 `provenance: "manual-adjusted"`。

- 先以 `annotate.py check` 通過幾何、尺寸、來源 hash、重複 id 與圖說編號硬檢查；它允許 `proposed`／`pending`／`manual-adjusted`，供預覽流程使用。再以 `annotate.py draw` 產生可審閱的標註 PNG。
- 在**正式交付前**，將 redacted + annotated 以 **100%** 並排檢視，逐筆通過 [references/annotation-qa.md](references/annotation-qa.md) 的清單後，才可由 reviewer 確認為 `approved`／`verified`／`checked`，並以 `annotate.py check --require-approved` 核對批准狀態。`manual-adjusted` 是來源／修改 provenance，永遠不等於批准；不能為了讓 draw 通過而預填 `verified`。
- 紅框、編號、圖說三者一致是獨立的交付條件；沒有渲染器也不能事後修正原圖上錯誤的座標。可在受限工作區先組裝含已遮蔽候選 PNG 的 draft 供 reviewer 核對，保留待審狀態；正式交付只能使用完成隱碼與標註驗收的 PNG。

## 操作圖表（條件式）

只有使用者**明確要求**流程圖、關係圖、架構圖、狀態圖或泳道圖等非截圖圖表時，才呼叫共用技能 `$ui-diagrams`；由該技能處理圖表的就緒檢查與後續交接。本技能不自行重複 draw.io 的圖表生成。

截圖、紅框、游標等畫面證據與互動標註，仍依本 UI 操作說明書流程處理，**不呼叫 $ui-diagrams**。

若 `$ui-diagrams` 回報婉拒或無法使用，只停止圖表分支，繼續沒有該圖表的手冊工作流程；僅在對話中向使用者回報此限制，**不得寫入 DOCX**。

## 文件結構與版面（build_docx.py）

開始排版前閱讀 [references/document-structure-qa.md](references/document-structure-qa.md) 與 [references/visual-consistency-standard.md](references/visual-consistency-standard.md)（版面基線與驗收標準）。把擷取結果整理成 build manifest（JSON），結構與全部欄位見 `scripts/build_docx.py` 的 docstring。文件順序固定為：

1. 標題區塊：標題、副標題、適用畫面。
2. **更新紀錄**：標題區塊正下方的單一表格，集中列出所有版本。
3. 修訂狀態：版本、日期、本次修訂摘要。
4. 版本依據：僅在有可驗證 repository／tag／release 資訊時出現。
5. 使用提醒與共通操作規則。
6. 一個目標功能一章：入口、前置條件、操作流程、UI 說明、成功影響、檢核。

組檔：

```text
<venv>/bin/python "<skill-path>/scripts/build_docx.py" \
  --manifest "<workspace>/manual.json" --output "<deliverable>/<file>.docx"
```

既有 DOCX 修訂必須先建立新版本副本；保留前版和不在範圍內的內容。使用者要求**修正預設**（範圍、章節、截圖規格、版面或基線）時，先在任務工作區以目前基線建立**可追溯的新版本**副本並記錄基線版本與偏離項目；使用者個案副本**不覆寫**已安裝的預設基線。

## 文件驗證與交付

1. 依 [references/screenshot-redaction-policy.md](references/screenshot-redaction-policy.md) 檢查每張圖的 `sourceKind`、敏感欄位清單、金額處理、raw／redacted／annotated provenance 與交付包內容。先以 `redact.py check --require-checked`、`annotate.py check --require-approved` 完成圖片關卡。
2. 以 `build_docx.py` 組檔；它會拒絕未獲明示核准的 `schematic` 圖與 raw／unredacted 圖片路徑。組檔前確認 build manifest 只引用 redacted／annotated PNG。
3. 檢查章節、圖說、紅框標註、每章編號重設、欄位表，以及更新紀錄是否齊全；檢查表格明確相對容器可用內容區置中且尺寸可彈性調整。
4. 檢查所有資料變更操作都有成功影響、鎖定條件、失敗／取消行為與操作後檢核。
5. 以 `verify_docx.py` 執行結構驗證：

```text
<venv>/bin/python "<skill-path>/scripts/verify_docx.py" \
  --docx "<deliverable>/<file>.docx" --manifest "<workspace>/manual.json"
```

結構檢查通過（exit code 0）後才進入交付審核；任何一項失敗，修正後重新組檔再驗證。**exit code 0 只代表程式列出的結構與 manifest 形式對應檢查通過**，不能證明內容語意、隱碼完整性或視覺可讀性，也不代表已完成獨立審核。

6. 以 `audit_delivery.py --docx <final.docx> --output <qa>/structure.json` 產生唯讀封裝／結構／媒體 hash 報告，再由非 builder 的 reviewer 建立獨立 review artifact。review 固定包含 `requirements`、`redaction`、`operation`、`layout_structure` 四類 checks，以及 `render_visual`；本版的 `render_visual.status` 只能是 `not_performed` 或 `out_of_scope` 並附原因，不得填 `pass`。
7. reviewer 的 `artifact.sha256` 必須綁定最終 DOCX；`reviewed_files` 必須逐筆列出最終 DOCX 所有嵌入圖片、build manifest、需求／需求 snapshot 與相關 redaction／annotation manifests，且每筆 hash 與實際檔案一致。`builder.id` 與 `reviewer.id` 必須明確且不同；不能由 builder 改名自審。文件、圖片、manifest 或需求證據變更後，重新計算受影響 hash 並重做相應 checks，不能只替舊 review 換 hash。
8. 以不同輸出檔執行 review 驗證：

```text
<venv>/bin/python "<skill-path>/scripts/audit_delivery.py" \
  --docx "<deliverable>/<file>.docx" \
  --review "<qa>/review.json" \
  --manifest "<workspace>/manual.json" \
  --output "<qa>/review-validation.json"
```

`audit_delivery.py` 的 exit code 0 只代表報告成功寫出；同時檢查 `mechanical_status` 與 `independent_review.status`。若沒有 reviewer、無法檢視圖片、證據缺失／過期或任一必要 check 未完成，狀態為 `blocked`，可繼續不依賴審核的已授權工作，但目前產物只能標示 `draft`，不得正式宣稱通過。若四類適用 checks、所有 hashes 與 review artifact 均有效，即使 `render_visual` 為 `not_performed`／`out_of_scope`，仍可依本輕量版範圍正式交付。
9. 將下列六步交接清單寫入對話或外部 QA 紀錄，逐項標示證據與狀態：**隱碼、標註、結構、獨立審核、證據雜湊、交付範圍**。不得把 renderer、權限、reviewer 或 fallback 警語寫入 DOCX；使用者需要 DOCX 視覺渲染時，改用完整版 `$ui-guide`。
10. 交付前確認新檔版本、檔名、目標資料夾和副本未覆寫來源；回報代表性變更、驗證結果與未解限制。

## 常見錯誤

| 情況 | 正確處理 |
| --- | --- |
| 未提供目標畫面 | 先索取 URL／路徑清單或上傳清單。 |
| repository/tag 有變更但未列出畫面 | 從前端差異提出候選清單，再由使用者確認。 |
| 畫面找不到欄位限制 | 明列待確認，勿自行補上。 |
| 成功儲存後就結束 | 加入資料、下游流程、鎖定規則與回查步驟。 |
| 敏感識別資料仍可見 | 回到 raw／redacted 對照補足精準色塊或像素化；身分 ID、地址、保單號、帳單號、合約號等預設遮蔽，金額依預設保留。 |
| 紅框座標在圖上就不對 | 回到 redacted 圖與 manifest 做 100% 檢核後重畫；組 DOCX 前修正，勿指望嵌入後自動變對。 |
| 想在 preview 前填 verified | 使用 `proposed`／`pending` 先通過 `annotate.py check` 並 `draw` 預覽；`manual-adjusted` 只記 provenance，須完成語意核對後再用 `--require-approved`。 |
| 只靠 Pillow 或 DOM 宣稱隱碼／標註通過 | 機械檢查只證明座標、尺寸與 hash；改由能看圖的獨立 reviewer 核對完整性與語意。 |
| 昨日 review 後替換圖片、manifest 或 DOCX | 使受影響 review 失效，重算實際 hash 並重做相關 checks；不可只替舊紀錄換 hash。 |
| 缺少獨立 reviewer | 繼續可做的已授權工作，交付狀態標為 draft／blocked；不得自換 reviewer 身分或宣稱 pass。 |
| 新章步驟續號 | 每個操作小節獨立編號（build_docx.py 每次建立新 numId），從 1 起算。 |
| 更新紀錄插在章節末 | 維持標題區塊正下方的單一表格。 |
| 宣稱「渲染驗證通過」 | 本版不做 DOCX 渲染；只陳述結構／封裝與獨立 review 範圍，需渲染時改用完整版 `$ui-guide`。 |
| 將執行環境或驗證範圍寫入文件 | 只在對話中向使用者回報；DOCX 保留操作內容。 |
| 未建立 venv 就直接跑腳本 | 先執行 `bootstrap.py`，一律使用 `~/.codex/venvs/ui-ops-manual-lite/bin/python`。 |
