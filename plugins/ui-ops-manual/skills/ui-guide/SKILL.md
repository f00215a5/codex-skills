---
name: ui-guide
description: Use when creating or revising a system UI 操作說明書, user manual, or DOCX guide that needs screen captures, annotated controls, field definitions, operation steps, and release-aware evidence.
---

# UI 操作說明書

建立可操作、可驗證的系統 UI 說明書。先確認畫面範圍與預設模板；用實機和來源證據描述畫面，而不是猜測控制項或後續影響。

## 產製路由與必要 gate

依序完成「範圍確認 → 單張完整截圖端到端實測 → 證據與隱碼 → 文件建置 → renderer／版面 QA → 獨立交付審核」。每一關留下可追溯結果；各模型可調整內容分段與版面細節，但不能跳過證據、隱碼、渲染或審核關卡。以下 refs 依階段必讀，不得只讀最新 review 訊息或只按關鍵字挑選：

整改也依此順序推進：每輪先判斷下一步是否能實質提高讀者完成主要流程的可用性；原始證據、隱碼或標註存在阻擋項時，不得進入文件建置／渲染。優先修正阻擋項並保留最近可用基底；連續同類返工沒有有效改善時停止相同策略，改做最小局部修復、依使用者已明示的範圍縮限，或如實回報阻擋，不得無限重建或把有阻擋的成品當成 pass。

- **取證前**閱讀 [references/screenshot-completeness-workflow.md](references/screenshot-completeness-workflow.md)、[references/screenshot-redaction-policy.md](references/screenshot-redaction-policy.md)、[references/screenshot-manifest.md](references/screenshot-manifest.md) 與 [references/incremental-qa-workflow.md](references/incremental-qa-workflow.md)。實際系統截圖是預設；示意／重繪 UI 只有在使用者明示時才可使用。身分 ID、地址、保單號、帳單號、合約號等預設遮蔽；金額預設保留。
- **開始排版／build 前**閱讀 [references/default-document-layout.md](references/default-document-layout.md) 與 [references/visual-consistency-standard.md](references/visual-consistency-standard.md)。plugin 規範決定文件結構；參照文件只提供可重用的視覺標準。表格以容器可用內容區為基準置中，寬高可依內容調整。
- **標註、renderer QA 前**閱讀 [references/render-and-annotation-qa.md](references/render-and-annotation-qa.md) 與 [references/safe-word-render-policy.md](references/safe-word-render-policy.md)。
- **準備交付／review 前**閱讀 [references/independent-delivery-review.md](references/independent-delivery-review.md)。reviewer 直接讀取需求、成品與原始證據，不採信 builder 的 `verified`；無獨立 reviewer 時明確標記 `independent review pending`，可繼續其他工作，檔名、資料夾或交付對話只能將產物標示 `draft`。

擷取前必讀 [references/screenshot-completeness-workflow.md](references/screenshot-completeness-workflow.md)：先跑通完整頁面擷取、隱碼、紅框／編號、嵌入及渲染，再依 [references/incremental-qa-workflow.md](references/incremental-qa-workflow.md) 由一張代表圖校準後按畫面與狀態小批次製作。完整頁面是主圖，局部放大只能補充；依已確認功能逐項驗收，不能以草稿或少量補圖結束尚可繼續的工作。

每張圖片的 raw／redacted／annotated 路徑、source SHA、capture state、座標與狀態，統一依 [references/screenshot-manifest.md](references/screenshot-manifest.md) 保存。使用者在目前任務已接受預設或明示略過範圍確認時，沿用該確認，不重複詢問同一授權。

QA record 同時記錄本次使用的 `ui-ops-manual` 版次（目前為 `0.5.0`）、實際讀過的相對 reference 路徑與適用 schema 版次；依 [references/incremental-qa-workflow.md](references/incremental-qa-workflow.md) 維護唯一累積 finding ledger、資產凍結與失效依賴，並保留回歸與實際整改輪次。每次 review 都保留前一輪未解缺陷清單，將新 findings 合併追蹤，優先修正阻擋項並記錄修正證據；不影響主要流程的措辭精緻度、次要欄位深度或輕微美觀可附 reason／evidence 記為 accepted limitation，不反覆退回，不能只以最後一則訊息取代歷史缺陷。

## 新任務第一輪回覆（強制）

對**每一個新建或修訂** UI 操作說明書的任務，無論使用者資訊看似是否完整，第一輪回覆都**必須先**輸出下列「預設範圍確認」表單，並明確要求使用者確認或改寫。不可只在資訊不足時才詢問；不可先開始擷取、登入、寫入系統或建立交付檔。

只有使用者在**目前任務**明確接受既有預設（例如表示「都用預設配置」）且已提供必要的目標畫面與交付資訊時，才可略過表單；仍須回覆已採用的預設範圍。缺少必要目標或交付資訊時，仍須只詢問缺少的項目。

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
> 8. **成功影響與驗證**：預設說明資料異動後的影響與檢核方式；若有 `word-render`，採用 Word-first 渲染驗證。
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
| 渲染驗證 | 啟用 | 若已安裝 `word-render`，依其 Word-first 流程渲染並逐頁檢視。 |

同時確認登入／測試資料的授權範圍。只用於取證；遮蔽密碼、權杖、個資與不應外流的業務資料。遇到會寫入、送出、刪除或觸發排程的 UI 動作，先取得當下確認。

## 初始化：CJK renderer 預檢

範圍確認後、擷取畫面與建立正式 DOCX 前，若文件會包含繁中、簡中、日文或其他 CJK **live text**，必須閱讀 [references/cjk-render-preflight.md](references/cjk-render-preflight.md) 並完成其初始化關卡。

- 先依本技能的 [安全 Word renderer 政策](references/safe-word-render-policy.md) 執行 `word-render --check-only`，確認本次最終 renderer；Word-first 不等於已證明 CJK 可讀。
- 選定一個**明確且可驗證**的 CJK 字型名稱，並用本外掛的 `create_cjk_probe.py` 產生含 `eastAsia` 字型與 `zh-TW` 語言標記的暫存 probe。
- 以**同一條** Word 或 LibreOffice renderer 路徑渲染 probe、逐頁 100% 檢視；PDF／PNG 存在或 exit code 0 都不足以代表通過。
- 僅當最終 renderer 為 LibreOffice 且 probe 有方框／缺字時，才向使用者索取已核准的字型目錄，使用 `create_fontconfig_config.py` 建立**任務限定**的 `FONTCONFIG_FILE` 後重試。不得安裝字型或修改永久環境變數。
- Word probe 失敗時，確認 Word 可使用的字型或改選另一個已驗證字型；不要套用 Fontconfig。

未通過 CJK glyph 預檢時，不得宣稱文件已完成視覺渲染驗證；可繼續結構檢查，但須明確回報限制。

## 初始化：安全 Word renderer 政策（僅本技能）

完成範圍確認後、首次 renderer 預檢前，必須閱讀 [references/safe-word-render-policy.md](references/safe-word-render-policy.md)。此政策只作用於本機目前使用者的 `ui-ops-manual` 任務；不改變使用者直接呼叫 `word-render` 或其他技能時的 fallback 行為。

- 所有由本技能發出的 Word probe 與 Word render，均使用同一個持久工作根目錄 `~/.codex/tmp/word-render`，並以 `--work-dir` 傳入。不可改成每個專案、每個文件或每個任務各自要求新的目錄權限。
- 預設安全模式是 `--fallback-policy deny`：Word 或固定工作根目錄遇到權限失敗時，先在已授權的本機互動環境重試；仍失敗才停止 renderer，**不得**自行切換 LibreOffice。
- 僅在首次實際失敗且尚未記住偏好時，才詢問使用者是否本次使用 LibreOffice，以及下次要再詢問或沿用本次選項；不可在一般任務初始化時預先詢問。
- 偏好僅保存 `allow`／`deny` 這個 renderer policy，不保存文件路徑、repository、帳號、字型或畫面內容。設定不存在、損毀或不合法時一律視為「再次詢問」。
- 使用者明確說「重設 UI 操作說明書渲染政策」時，依參考流程移除該偏好；下次實際失敗會再次詢問。

## 取得目標與版本依據

1. 以使用者提供的 URL／清單為準。若沒有清單，先請使用者提供，不以選單名稱推測範圍。
2. 若提供**前端 repository 或 tag**，閱讀變更與路由／頁面元件，找出可能的**前端新增／修改畫面**；提出候選 URL／畫面清單並**請使用者確認**後才納入手冊。若另提供後端 repository 或 tag，僅用其確認資料異動與下游影響。
3. 若只提供 repository，詢問比較基準；若只提供 tag，確認可用的來源與比較對象。將版本、日期、commit 或 release note 僅寫入可驗證的事實。
4. **不提供 repository 或 tag**時，照樣以 UI 實機取證製作手冊，但**省略版本依據**章節與任何版本推論。

不要採用任何特定專案的 release 工作流；這是通用技能。

## 擷取與說明

每個目標畫面建立一份覆蓋清單，再寫入文件。對每個互動元素記錄：名稱／icon、用途、觸發結果、顯示或可用條件、欄位定義、是否必填、格式與參數限制、錯誤或成功回饋。無法從 UI 或來源確認時標為「待確認」，不要捏造限制。

呼叫 builder 前，逐項以實際畫面的 `captureState.id` 和 manifest `source` 對照盤點可互動欄位、表頭、必填標記與可見選項。每欄用途要按畫面具體描述，不能用同一句泛用模板代替；未在證據中觀察到的欄位不得為湊完整度新增；必填狀態無法確認時寫「待確認」，不能預設為否。

每個操作流程使用下列順序：

1. 側邊欄／導覽入口截圖和到達路徑。
2. 操作前置條件與可修改／鎖定條件。
3. 完整頁面的主畫面操作截圖（長頁依完整性規格擷取），在操作區加紅框與編號，按實際順序列步驟；局部圖只能補充。
4. 填寫或選擇欄位的說明表。
5. 成功、失敗、取消／關閉行為與**修改成功後的影響**。
6. 操作後檢核。

**各操作小節獨立**使用真正的 Word 編號清單，並從**步驟 1**開始；不要讓新章節延續成「步驟 25」。圖說的紅框編號要與同張圖的標註一致，同一張圖不可重複，且必須與目前 annotated manifest 的 id 一一對齊；不要把圖號當成操作步驟號。

先依 [references/screenshot-redaction-policy.md](references/screenshot-redaction-policy.md) 判定來源與隱碼範圍，再取原始證據並產生 redacted／標註副本。操作截圖預設保留實際系統畫面；除非使用者明示，不得用重繪或生成 UI 取代它。身分 ID、地址、保單號、帳單號、合約號等識別資訊精準遮蔽，金額依預設保留。每個需互動的紅框應緊貼目標控制項，不遮蔽文字；圖說寫明紅框編號、控制項名稱與用途。若同一畫面有多個動作，拆成可讀的完整頁面操作圖，分別標示當步操作區；不得以局部裁切取代完整主圖。

若 CUA screenshot 契約回傳 `Uint8Array`，可在同一 Node runtime 以 `fs/promises.writeFile` 保存到受限 QA 路徑後計算 hash；不可杜撰 API、把瀏覽器替代控制當成保存限制，或用生成 UI 取代實機來源。工具契約允許時，優先以該次 capture 的 DOM element／文字 `Range.getBoundingClientRect()` 取得實際 bbox；DOM 不可用時不可猜測座標，也不可跨圖沿用固定 y range。

對任何紅框或游標標註，先閱讀 [references/render-and-annotation-qa.md](references/render-and-annotation-qa.md)。以 manifest 管理每個控制項、redaction 和 caption；在 DOCX 建置前完成標註語意檢核。不要把 Word 的最終渲染當成紅框位置正確的證明。

## 操作圖表（條件式）

只有使用者**明確要求**流程圖、關係圖、架構圖、狀態圖或泳道圖等非截圖圖表時，才呼叫共用技能 `$ui-diagrams`；由該技能處理圖表的就緒檢查與後續交接。本技能不自行重複 draw.io 的圖表生成。

截圖、紅框、游標等畫面證據與互動標註，仍依本 UI 操作說明書流程處理，**不呼叫 $ui-diagrams**。

若 `$ui-diagrams` 回報婉拒或無法使用，只停止圖表分支，繼續沒有該圖表的手冊工作流程；僅在對話中向使用者回報此限制，**不得寫入 DOCX**。

## 文件結構與版面

製作 DOCX 時使用 `documents` 技能，並在開始排版前閱讀 [references/default-document-layout.md](references/default-document-layout.md) 與 [references/visual-consistency-standard.md](references/visual-consistency-standard.md)。plugin 規範決定文件結構；預設基線或既有參照文件只提供可重用的視覺標準，不攜帶任何特定系統名稱、畫面或資料。

開始呼叫 builder 前，先依 default-document-layout 核對實際 builder 配置（頁面與 margin、容器可用寬、表格寬度／欄寬、真正 Word 編號與 renderer）；把與 defaults 的偏離記入同一份 QA record，未核對不得進入批量建置。依 [references/incremental-qa-workflow.md](references/incremental-qa-workflow.md) 使用同一個已受檢查 builder 套用各章格式，不逐章手寫不同格式。

若本次接受 plugin 預設且沒有自訂版型，執行 `audit_delivery.py` 時加上 `--require-default-layout`，讓它只核對 body 第一個資料表首列的三欄 `版本`／`日期`／`更新內容`；它只回報機械 failure code，不證明完整格式或內容語意。只有使用者明示自訂並改變更新紀錄位置或表頭時才省略 flag，並在 QA record 記錄理由。flag 只跳過前置的單格表格且該表格內確實有巢狀表格；沒有巢狀表格的單格首表仍是候選表並明確失敗，不猜測其用途。

文件順序預設如下；使用者在範圍確認中明示調整時依確認結果執行：

1. 標題區塊：標題、副標題、適用畫面。
2. **更新紀錄**：標題區塊正下方的單一表格，集中列出所有版本；不要將更新紀錄散落在各章。
3. 修訂狀態：版本、日期、修訂摘要；放在更新紀錄和版本依據之間。
4. 版本依據：僅在有可驗證 repository／tag／release 資訊時出現。
5. 使用提醒與共通操作規則。
6. 一個目標功能一章：入口、前置條件、操作流程、UI 說明、成功影響、檢核。

既有 DOCX 修訂必須先建立新版本副本；保留前版和不在範圍內的內容。沿用既有視覺版面，除非使用者要求改版；章節順序與必要內容仍依目前 plugin 規範，不能因參照文件的舊結構而改變。

使用者要求**修正預設**（範圍、章節、截圖規格、版面或基線）時，先在任務工作區以目前基線**建立副本**並命名為可追溯的**新版本**，記錄基線版本與偏離項目。使用者個案的副本**不覆寫**已安裝的預設基線；只有使用者明確要求更新共用基線時，才另行建立新的基線版本。

## 文件驗證與交付

1. 先依 screenshot-completeness-workflow 的覆蓋表逐項比對已確認範圍、完整頁面主圖、必要操作／狀態與最終文件位置；每張圖片在 DOCX 建置前執行：`<bundled-python> "<skill>/scripts/validate_screenshot_manifest.py" --manifest "<qa>/one.json" --base-dir ".." --output "<qa>/one-manifest-validation.json"`。再檢查章節、圖說、紅框標註、每章編號重設、欄位表及更新紀錄。缺圖返回取證補齊，不以少量示例或 draft 當成完成。
2. 依 [references/screenshot-redaction-policy.md](references/screenshot-redaction-policy.md) 檢查來源分類、預設敏感值遮蔽、金額處理、redacted／annotated 圖片與媒體清理；原始圖與敏感原值不得進入交付品。validator 的 `geometry_status`／`manifest_status` 只代表 hash、尺寸、bbox 與明示狀態，不能代替逐張圖片檢視或 independent review。
3. 檢查所有資料變更操作都有成功影響、鎖定條件、失敗／取消行為與操作後檢核。
4. 依 [references/render-and-annotation-qa.md](references/render-and-annotation-qa.md)、[references/default-document-layout.md](references/default-document-layout.md) 與 [references/safe-word-render-policy.md](references/safe-word-render-policy.md) 使用固定的安全 Word 工作根目錄，先分類「Word 不可用」或「沙箱／路徑權限受限」，再決定重試、停止或經使用者確認的備援；含 CJK live text 時，CJK glyph 預檢必須先通過。
5. 若已安裝 `word-render`，必須使用其 Word-first `--check-only` 與最終渲染流程，逐頁檢視 PNG，並回報**最終實際 renderer**。本技能不可在 Word 權限失敗時自行使用 `documents`；依安全 renderer 政策取得本次或已記住的明確允許後，才可採用 LibreOffice。沒有 `word-render` 時，先說明無法執行 Word-first 驗證並取得使用者確認，再使用可用的 `documents` 渲染流程；無論哪條路徑，不能以 exit code 0 取代 CJK glyph 檢視。
6. 渲染失敗或工具不存在時，執行結構／封裝檢查並明確說明限制；Word／瀏覽器在 sandbox access denied 時，先在已授權的本機互動環境重試，不把權限拒絕當成 fallback；**不得宣稱已完成渲染驗證**。
7. 依 [references/independent-delivery-review.md](references/independent-delivery-review.md) 執行獨立交付審核。reviewer 直接讀取需求、最終 DOCX／頁面、redacted 圖片與受限原始證據；不採信 builder 的 `verified`。依固定 review artifact schema 保存 artifact sha256、builder／reviewer id、reviewed files 與四類 checks；任何 `fail` 或未解阻擋項為 `overall: fail`，證據不足或無 reviewer 為 `overall: blocked`，非阻擋 limitation 可在 reason／evidence 中記錄並保留 `overall: pass`。
8. 無獨立 reviewer 時，在對話和外部審核紀錄明確標示 `independent review pending`；應持續完成所有不依賴 reviewer 的已授權工作，若交付目前產物則在檔名、資料夾或交付對話清楚標示 `draft`，不得宣稱審核通過。review environment、工具可用性、權限失敗與 fallback **不得寫入 DOCX**；交付文件只保留使用者確認的操作內容。
9. 交付前確認新檔版本、檔名、目標資料夾和副本未覆寫來源；回報代表性變更、驗證結果與未解限制。

## 常見錯誤

| 情況 | 正確處理 |
| --- | --- |
| 未提供目標畫面 | 先索取 URL／路徑清單或上傳清單。 |
| repository/tag 有變更但未列出畫面 | 從前端差異提出候選清單，再由使用者確認。 |
| 畫面找不到欄位限制 | 明列待確認，勿自行補上。 |
| 成功儲存後就結束 | 加入資料、下游流程、鎖定規則與回查步驟。 |
| Word 預檢在沙箱失敗 | 使用固定 `~/.codex/tmp/word-render` 根目錄重試；仍失敗時依安全 renderer 政策停止或詢問，權限錯誤不等於 Word 不可用。 |
| 紅框在渲染後跑版 | 先在原始／redacted PNG 與標註 PNG 做 100% 語意檢核；DOCX 渲染只驗證版面與縮放，完成後仍須獨立 reviewer 審核。 |
| 新章步驟續號 | 為每個操作小節建立獨立編號定義，從 1 起算。 |
| 更新紀錄插在章節末 | 維持標題區塊正下方的單一表格。 |
