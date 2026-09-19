# 增量取證、整改與回歸流程

在第一張代表圖完成端到端實測後、開始小批次取證或文件建置前閱讀。本流程補充 [screenshot-completeness-workflow.md](screenshot-completeness-workflow.md)、[screenshot-manifest.md](screenshot-manifest.md) 與 [independent-delivery-review.md](independent-delivery-review.md)，不取代其中的圖片、隱碼、渲染或獨立審核關卡。

## 代表圖到小批次

1. 先選一張能代表實際操作、頁面上下文、畫面狀態與必要隱碼的圖，完成 raw、redacted、annotated、manifest、機械檢查及直接看圖。記錄該張 `captureState.id`、source SHA、實際測得的控制項／敏感值 bbox，以及 viewport、捲動、full-page 重排或固定頁首的校準依據。
2. 代表圖通過後，才按畫面與狀態分成小批次；每批仍逐張建立自己的 state、hash、bbox 與 manifest，通過同一組圖片關卡後才進下一批。不能把代表圖的列距、固定 `y` 或舊座標套到其他頁面或狀態。
3. 某一批發現共通缺陷時，先暫停該批，依依賴順序修正所有受影響資產與狀態，再重新檢視；不能只修最後一則訊息指出的那一張。

## 唯一累積 finding ledger

QA 工作區只維護一份跨輪次、跨階段的累積 finding ledger，可用既有 QA record 的表格或 JSON 保存，不另造第二份審核結果。每筆至少記錄：`id`、`asset/state`、`stage`、`category`、`status`、`evidence`、`fix verification`。`evidence` 與修正驗證只引用不含敏感值的路徑、hash、capture id、報告或 reviewer 記錄。

每輪把上一輪未解項目與新 findings 合併，先分出阻擋項與非阻擋項，再按階段依賴處理阻擋項和所有同類的 open／blocked 項目，重新檢查受影響清單；最新訊息、最新檔案或單一圖片通過不能清除歷史項目。阻擋項只有在有修正證據並重新檢視後才可關閉；非阻擋項可附 reason／evidence 記為 accepted limitation，不要求反覆退回。

## 可用性優先與停止條件

阻擋項包括錯誤或誤導操作、主要流程或關鍵實圖缺失、敏感值漏遮、遮住控制項或使其無法辨識，以及內容不可讀；只要有未解阻擋項，成品不得標為 pass。每輪先評估修正是否能實質提高讀者完成主要流程的可用性，聚焦阻擋項並保留最近可用基底；不影響操作的措辭精緻度、次要欄位深度與輕微美觀可記為 accepted limitation。

連續同類返工沒有有效改善時，停止相同策略，改做最小局部修復、依使用者已明示的範圍縮限，或如實回報阻擋；不得無限重建，也不得用 `checked`、validator pass 或舊成品掩蓋阻擋項。模型或操作者的差異只按本輪實際 evidence 記錄，不推算一般錯誤率。

## 通過資產的凍結與失效

每個已通過階段凍結其資產 hash、`captureState` 與下游依賴關係，並把這些值寫入 QA record。依賴變更時按下列規則回退：

- raw 或 canonical source 改變：該張 redaction、annotation、caption 與引用它們的文件／渲染證據全部失效，回到該張重新測量。
- redacted 圖或隱碼 bbox 改變：annotated 圖、圖說、嵌入媒體與引用文件須重建並重新檢視。
- 只改與圖片狀態無關的文字：不需重拍；但重新建置受影響章節並重跑相應結構、版面與 reviewer checks。

不要把舊 hash 或舊 capture state 複製到新檔案來保留通過狀態。機械驗證只能證明檔案、hash、尺寸與 bbox 等可檢查欄位，不能替代逐張真實圖片檢視或整份最終文件閱讀。

通過階段的成品以版本化、不可覆寫的 checkpoint 保留，並記錄 builder 與輸入 hash；後續更改另寫新路徑。手動修成品須同步 builder，或記錄唯一可重放的 patch，不得用舊 builder 重跑覆寫通過物。取代 `current` 指標前先驗既有 hash，候選版本須通過所有既有 gate 後才可切換。

## 修正完成的證據

本輪修正要在 QA record 固定 source 與 output 的絕對路徑及 hash；build 後讀回真正輸出，重新確認缺陷消失，不能把 source 已更新當成產物已更新。回歸檢查失敗時不得刪除 assert 或縮小檢查範圍來取得通過；若檢查本身有錯，記錄依據與修正後再跑。manifest validator 的 exit 0 代表 `manifest_status` 為 `pass`，exit 1 代表報告已寫入但為 `blocked`／`fail`；`audit_delivery.py` 的 exit 0 不保證各 gate pass。兩者都必須讀取相應 status，且不代表視覺或語意審核通過；批次重建只更新受影響圖片，並先核對凍結 hash，避免舊腳本覆寫已通過資產。

## 建置前內容與共用 builder

呼叫 builder 前，使用原始 UI 證據逐項建立欄位／表頭／必填標記／可見選項 inventory，並回指具體 `captureState.id` 與 manifest source。只寫實際觀察到的內容；必填狀態無法確認時標為「待確認」，不能預設為否，也不能為湊完整度新增未觀察到的欄位。每欄用途要按畫面具體描述，不能以整表相同的泛用句代替。

文件格式由一個共用且已受檢查的 builder 套用頁面、表格、真正 Word numbering 與其他版面設定；各章不要手寫或複製不同格式。開始批量建置前依 [default-document-layout.md](default-document-layout.md) 核對 builder 實際配置，並在 QA record 記錄偏離；builder 或格式基線變更後，重建並重新檢查其所有受影響依賴。

## 回歸紀錄

QA record 另記錄同類 finding 是否再次出現、已知回歸、完整重建次數、渲染次數與實際整改輪數。這些是實際工作紀錄，不是要求一輪通過、零錯誤或任何自動語意判定；沒有完成直接圖片檢視、整份最終閱讀或獨立審核時，仍依既有規範標為 pending／blocked／draft。
