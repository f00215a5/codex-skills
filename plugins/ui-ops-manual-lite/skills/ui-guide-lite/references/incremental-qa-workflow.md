# 增量取證、整改與回歸流程（輕量版）

在代表圖端到端實測後、開始小批次或文件建置前閱讀。本流程補充 screenshot completeness、manifest、隱碼、標註和獨立 review；不取代逐張看圖或最終 DOCX 內容讀回。

## 代表圖、小批次與回歸

1. 選一張代表實際操作、頁面上下文、狀態與必要隱碼的主圖，完成 raw、redacted、annotated、每張 manifest、幾何／hash 檢查、100% 直接看圖、暫存 DOCX build 和輸出讀回。記錄 `captureState.id`、source hash、viewport、scroll、full-page／viewport 校準、控制項／敏感值 bbox。
2. 代表圖通過後，按畫面與狀態拆成小批次。每批逐張使用自己的 capture state、hash、bbox、caption 和 manifest，通過同一組圖片／結構關卡後再進下一批；不得把代表圖的列距、固定 y、舊 capture state 或舊座標套到另一張圖。
3. 某批出現共通缺陷時先暫停該批，按依賴修正所有受影響資產與 output，再回歸檢查；不能只修最新訊息點名的一張，也不能為取得 pass 刪減 assert 或縮小已確認範圍。

## 唯一累積 finding ledger

QA 工作區只維護一份跨輪次、跨階段的累積 finding ledger，不另造第二份互相矛盾的審核結果。每筆至少記錄：`id`、`asset/state`、`stage`、`category`、`status`、`evidence`、`fixVerification`。evidence 只引用不含敏感值的路徑、hash、capture id、報告或 reviewer 記錄。

每輪把上一輪未解項目與新 findings 合併，再區分阻擋與非阻擋；阻擋項和同類 open／blocked 項按依賴處理並重新檢查受影響清單。最新檔案、最新訊息或單一圖片通過不能清除歷史項目。阻擋項只有在有修正 evidence 且重新直接檢視後才可關閉。非阻擋的次要欄位深度、措辭精緻度和輕微美觀可寫為 `accepted limitation`，附 reason／evidence，不反覆退回。

## 可用性標準與無改善停止條件

阻擋項包括錯誤／誤導操作、主要流程或關鍵實圖缺失、敏感值漏遮、遮住 controls／labels 或使其無法辨識、內容不可讀。任一未解阻擋項都不得標 `pass`。builder 可先直接看圖建立 draft，但 draft／validator pass／舊成品不是完成條件。

「無改善」有明確定義：本輪指定缺陷在實際 output 未消失或影響未減；修正了錯的位置；只更新 source 而沒有更新／重建 output；或引入同級／更重回歸。第一次無改善要記錄 evidence 並診斷原因。同一策略連續兩次無改善是停止該無效策略的上限，不是必跑配額；若已有 evidence 顯示策略不再提高主要可用性，可更早改做定點最小修復、採用使用者已明示的範圍縮限，或如實回報部分 draft／blocked。主要漏遮、誤導、缺關鍵流程或內容不可讀仍不能 pass；不得僅更改狀態或刪減必要驗證。

## Freeze、checkpoint 與失效依賴

每個已通過階段 freeze source／output hash、`captureState`、builder 輸入、版本和下游依賴，並保留版本化、不可覆寫的 immutable checkpoint。不要複製舊 hash 或舊 capture state 到新檔案維持假通過狀態；後續更改寫新路徑並在切換 `current` 前通過既有 gates。

- raw／canonical source 改變：該張 redaction、annotation、caption、嵌入媒體、DOCX 與下游 review evidence 失效，回到該張重新測量。
- redacted 圖或 redaction bbox 改變：annotated 圖、annotation／caption、DOCX 媒體與 reviewer evidence 失效，重新產製與檢視。
- 只改與圖片狀態無關的文字：不需重拍，但要重建受影響章節、讀回 DOCX、更新 hash 並重做相應 checks。
- DOCX、manifest、需求證據或任何 reviewed file 改變：artifact／受影響 review hash 失效，不能只替舊 review 換 hash。

建置後固定讀回真正 output，確認主要流程、正文／表格文字、嵌圖與圖說；source 更新不等於 output 更新。`validate_screenshot_manifest.py`、`verify_docx.py` 和 `audit_delivery.py` 的 exit code 只代表各自報告／機械檢查結果，必須讀取 status 並保留直接看圖和獨立 review evidence。

## 建置前 inventory 與共用 builder

呼叫 builder 前，以原始 UI 證據逐項建立欄位／表頭／必填標記／可見選項 inventory，回指具體 `captureState.id` 和 manifest source。只寫實際觀察到的項目；必填狀態無法確認時寫「待確認」，不能填「否」或補未觀察欄位。每欄用途按該畫面具體描述，不能用同一句泛用文字代替不同 controls。

使用一個已檢查的 builder 套用頁面、表格、真正 Word numbering 和圖片尺寸規則；各章不能各自手寫不同格式。`chapter` 與相容的 `chapters[]` manifest 形狀依 builder 現行 schema，不能在文件中另造不受腳本支援的欄位。

## 回歸紀錄

QA record 另記錄同類 finding 是否再次出現、已知回歸、代表圖／批次數、完整重建次數、內容 preview 次數、實際整改輪次、freeze／checkpoint 路徑和 reviewer 狀態。沒有完成直接圖片檢視、整份最終讀回或獨立審核時，依規範標為 pending／blocked／draft；缺 renderer 不列入 blocker。
