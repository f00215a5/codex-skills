# 增量取證、整改與回歸流程

在範圍盤點後、第一張代表圖前閱讀。本流程補充 [screenshot-completeness-workflow.md](screenshot-completeness-workflow.md)、[screenshot-manifest.md](screenshot-manifest.md) 與 [independent-delivery-review.md](independent-delivery-review.md)，不改變實機證據、隱碼、renderer、版型或獨立審核要求。它把重做限制在受影響依賴，並讓第二輪可以承接可驗證的既有結果；不新增重複審核關卡。

## 一份 QA record 與短執行 checklist

同一份 QA record 只維護下列相互連結的區塊，不另造重複的盤點表、語意表或資產審核結果。第一張圖前先建立骨架與候選列，取證後回填狀態／capture id，呼叫 builder 前才完成必要語意核對：

- `scopeMatrix`：功能 → 主／子配置區 → 造成獨特操作的條件／狀態 → 最小代表案例 → UI／來源證據。
- `fieldInventory`：控制項類型、必填狀態、值來源、作用條件、結果、`captureState.id`／manifest source 與 `confirmed`／`unknown` 狀態。
- `assetLedger`：raw、redacted、annotated、caption、manifest、文件／頁面、hash、依賴、checkpoint 與 review 狀態。

執行時只需照這份短表逐項回填，既有 gate 仍依引用的 reference 執行：

1. 盤點主功能、主／子配置區與獨特條件，先列候選的最小代表案例；共用流程寫一次，差異放表格，不以資料筆數、頁數或圖片張數判定完成。
2. 以實機和提供來源逐步回填唯一 `fieldInventory`；呼叫 builder 前完成控制項類型、必填、值來源與條件核對，仍不能確認時寫 `unknown`／`待確認`，不把本機碼當部署事實。
3. 先完成一張完整主圖的 raw／redacted／annotated／manifest，嵌入暫存文件並以最終 renderer 實際檢查可讀性；需要時補同一狀態的 detail。
4. 依畫面／狀態分小批；每批凍結資產、hash、依賴與 checkpoint，只讓受影響依賴失效。
5. 建置、渲染與 review 只重跑受影響工作；每輪仍做整份版面檢查，第二輪依本文件的 delta review 記錄承接與變更。
6. 在 QA record 記 phase 時間、等待與返工原因；同策略沒有新改善就停止，保留最近可用且如實標示限制的基底。

這份 checklist 是工作順序提示，不是額外的 pass 關卡；阻擋項仍依既有規範處理。

## 代表圖到小批次

1. 先選一張能代表實際操作、頁面上下文、畫面狀態與必要隱碼的完整主圖，完成 raw、redacted、annotated、manifest、機械檢查及直接看圖。記錄該張 `captureState.id`、source SHA、實際測得的控制項／敏感值 bbox，以及 viewport、捲動、full-page 重排或固定頁首的校準依據。
2. 將這張圖以最終預定的 renderer 嵌入暫存 DOCX（或相同容器），在實際縮放下檢查頁面定位、操作目標、caption 與文字可讀性；長頁保留完整主圖，只有讀者確實需要時才補同一狀態的 detail。嵌入不可讀時先修正圖片比例／分頁或 detail，再開始小批量。
3. 代表圖通過後，才按畫面與狀態分成小批次；每批仍逐張建立自己的 state、hash、bbox 與 manifest，通過同一組圖片關卡後才進下一批。不能把代表圖的列距、固定 `y` 或舊座標套到其他頁面或狀態。
4. 某一批發現共通缺陷時，先暫停該批，依依賴順序修正所有受影響資產與狀態，再重新檢視；不能只修最後一則訊息指出的那一張。未受影響且 hash／依賴相符的資產可沿用其 checkpoint。

## 唯一累積 finding ledger

QA 工作區只維護一份跨輪次、跨階段的累積 finding ledger，可用既有 QA record 的表格或 JSON 保存，不另造第二份審核結果。每筆至少記錄：`id`、`asset/state`、`stage`、`category`、`status`、`evidence`、`fix verification`。`evidence` 與修正驗證只引用不含敏感值的路徑、hash、capture id、報告或 reviewer 記錄。

每輪把上一輪未解項目與新 findings 合併，先分出阻擋項與非阻擋項，再按階段依賴處理阻擋項和所有同類的 open／blocked 項目，重新檢查受影響清單；最新訊息、最新檔案或單一圖片通過不能清除歷史項目。阻擋項只有在有修正證據並重新檢視後才可關閉；非阻擋項可附 reason／evidence 記為 accepted limitation，不要求反覆退回。

## 可用性優先與停止條件

阻擋項包括錯誤或誤導操作、主要流程或關鍵實圖缺失、敏感值漏遮、遮住控制項或使其無法辨識，以及內容不可讀；只要有未解阻擋項，成品不得標為 pass。每輪先評估修正是否能實質提高讀者完成主要流程的可用性，聚焦阻擋項並保留最近可用基底；不影響操作的措辭精緻度、次要欄位深度與輕微美觀可記為 accepted limitation。

連續同類返工沒有有效改善時，停止相同策略，改做最小局部修復、依使用者已明示的範圍縮限，或如實回報阻擋；不得無限重建，也不得用 `checked`、validator pass 或舊成品掩蓋阻擋項。模型或操作者的差異只按本輪實際 evidence 記錄，不推算一般錯誤率。

## 通過資產的凍結與失效

每個已通過階段凍結其 raw／redacted／annotated 路徑、caption 內容、manifest、各自 hash、`captureState`、下游依賴與不可覆寫的 checkpoint，並把這些值寫入同一 QA record。`caption` 可對正規化 UTF-8 文字計 `captionSha256`；checkpoint 要能回指產物與輸入 hash。資產凍結只表示該版本可回溯，不代表獨立 review 已通過。依賴變更時按下列規則回退，只有列出的下游失效：

- raw 或 canonical source 改變：該張 redaction、annotation、caption 與引用它們的文件／渲染證據全部失效，回到該張重新測量。
- redacted 圖或隱碼 bbox 改變：annotated 圖、圖說、嵌入媒體與引用文件須重建並重新檢視。
- annotated 圖或 caption 改變：嵌入媒體、受影響文件頁面及其 review 證據失效；raw／redacted 可在 hash 不變且依賴記錄相符時承接。
- 控制項語意 inventory、畫面狀態或來源證據改變：該欄位、步驟、差異表、caption 與其圖片／章節失效；不影響的其他案例不必重做。
- 只改與圖片狀態無關的文字：不需重拍；但重新建置受影響章節並重跑相應結構、版面與 reviewer checks。
- 版型、builder、margin、字型或其他全域版面設定改變：所有渲染頁都是受影響頁面，須重新做整份版面檢查；不要以未變圖片 hash 代替像素與版面檢視。

不要把舊 hash 或舊 capture state 複製到新檔案來保留通過狀態。機械驗證只能證明檔案、hash、尺寸與 bbox 等可檢查欄位，不能替代逐張真實圖片檢視、整份版面檢查或語意 review。

通過階段的成品以版本化、不可覆寫的 checkpoint 保留，並記錄 builder 與輸入 hash；後續更改另寫新路徑。手動修成品須同步 builder，或記錄唯一可重放的 patch，不得用舊 builder 重跑覆寫通過物。取代 `current` 指標前先驗既有 hash，候選版本須通過受影響資產關卡與整份版面檢查，再依獨立 review 結論切換。

## 第二輪 delta review

第二輪或後續輪次先指定唯一 baseline：上一輪獨立 review artifact 中個別 `status: pass` 且沒有未解 finding 的語意項目，或使用者明確接受的範圍／限制；artifact 的 `fail`、`blocked`、`pending` 與未解項目不可作為 baseline。使用者接受的範圍／限制只能按明示內容承接，不得冒充獨立 reviewer pass；沒有可驗證 baseline 時按首輪完整語意 review。baseline 只讀保存，不能假造 reviewer、修改舊 review hash 或把舊結果改寫成新輪次結果。

在同一 QA record 記錄：`baseDocxSha256`、`baseReviewArtifactSha256`（若有）、baseline 來源、承接的是哪個已通過語意項目／明示接受項目、`changed`、`affected`、`inherited` 資產／頁面與每項理由。`inherited` 只有在目前資產 hash、capture state 與依賴均和 baseline 相符，且沒有全域版面變更時才可承接原語意結論；任一值不符就列入 `changed`／`affected` 重審。hash 只能證明檔案與依賴相符，不能當成像素或操作語意 pass。

每輪保留整份最終文件的 layout check（全部渲染頁、分頁、圖片／caption、表格容器位置與裁切）；若 builder、字型、margin、圖片尺寸規則或其他全域版面設定變更，所有頁面都列為 `affected` 並重新做版面與必要語意檢查。局部文字或資產變更只擴大到依賴圖譜所列頁面。新 review artifact 仍要列出實際 reviewer id 與現檔 hash，不能用承接清單替代 reviewer。

## 修正完成的證據

本輪修正要在 QA record 固定 source 與 output 的絕對路徑及 hash；build 後讀回真正輸出，重新確認缺陷消失，不能把 source 已更新當成產物已更新。回歸檢查失敗時不得刪除 assert 或縮小檢查範圍來取得通過；若檢查本身有錯，記錄依據與修正後再跑。manifest validator 的 exit 0 代表 `manifest_status` 為 `pass`，exit 1 代表報告已寫入但為 `blocked`／`fail`；`audit_delivery.py` 的 exit 0 不保證各 gate pass。兩者都必須讀取相應 status，且不代表視覺或語意審核通過；批次重建只更新受影響圖片，並先核對凍結 hash，避免舊腳本覆寫已通過資產。

## 建置前內容與共用 builder

呼叫 builder 前，使用同一 QA record 的唯一 `fieldInventory` 與原始 UI 證據逐項建立欄位／表頭／必填標記／可見選項 inventory，並回指具體 `captureState.id` 與 manifest source。提供的本機原始碼可作候選或語意線索，但不能證明目前部署畫面；與實機衝突時保留 `unknown`／「待確認」。只寫實際觀察到的內容；必填狀態無法確認時不能預設為否，也不能為湊完整度新增未觀察到的欄位。每欄用途要按畫面具體描述，不能以整表相同的泛用句代替。

文件格式由一個共用且已受檢查的 builder 套用頁面、表格、真正 Word numbering 與其他版面設定；各章不要手寫或複製不同格式。開始批量建置前依 [default-document-layout.md](default-document-layout.md) 核對 builder 實際配置，並在 QA record 記錄偏離；builder 或格式基線變更後，依依賴圖譜重建受影響頁面，並按 delta review 保留整份 layout check。

## QA phase 與返工紀錄

最少記錄下列 phase：`scope/inventory`、`capture`、`image-processing`、`writing/build`、`render`、`review` 與 `rework`。每筆記 `startedAt`、`endedAt` 或可重現的 elapsed、`active`／`wait`、`parallelGroup`（如有）、受影響資產與 `reason`；返工原因至少分類為 `scope-gap`、`semantic-mismatch`、`capture/state`、`redaction`、`annotation`、`embed/layout`、`renderer` 或 `review-finding`。並行 phase 共用同一 wall-time 區間時只計一次總 elapsed，等待另記且不加到 active；不要用硬性時間配額要求一輪完成。

## 回歸紀錄

QA record 另記錄同類 finding 是否再次出現、已知回歸、完整重建次數、受影響局部重建次數、渲染次數、實際整改輪數與返工原因計數。這些是實際工作紀錄，不是要求一輪通過、零錯誤或任何自動語意判定；沒有完成必要的直接圖片檢視、整份最終版面檢視或本輪適用的語意審核（含有效承接）與獨立審核時，仍依既有規範標為 pending／blocked／draft。
