# 截圖完整性與缺件處理（輕量版）

在第一張畫面取證前閱讀。此規格適用整本或局部修訂手冊，沿用目前已確認的範圍；已接受的預設不重複索取。每張圖的 manifest、capture state、座標校準和唯讀檢查見 [screenshot-manifest.md](screenshot-manifest.md)；代表圖、小批次、finding ledger、freeze 和 checkpoint 見 [incremental-qa-workflow.md](incremental-qa-workflow.md)。

## 代表圖先行

先選一張包含實際操作目標、頁面上下文和需隱碼資料的代表性頁面，完成 raw、redacted、annotated、整合 screenshot manifest、`redact.py`／`annotate.py`／`validate_screenshot_manifest.py` 圖片檢查、暫存 DOCX build 與輸出讀回。讀回只驗證內容／封裝／結構範圍；lite 沒有 DOCX renderer，不把 preview 或 exit code 說成 Word 分頁或字型通過。端到端流程未跑通前先修正，不能先大量產生缺圖文件。

每張圖都重新保存 `captureState.id`、source SHA-256、原始尺寸、viewport／scroll／full-page 校準和各自 bbox。不要把代表圖或前一個狀態的座標、列距或固定 y 套到下一張圖。

## 完整頁面主圖

- 主圖預設是整個應用程式頁面，保留頁首／標題、導覽或側邊欄、主要內容及操作區的相對位置。瀏覽器網址列和作業系統桌面不是必要內容。
- 短頁使用完整 viewport。長頁使用工具支援的 full-page，或使用有順序、scroll offset、重疊區域及每張個別 manifest 的 `viewport-sequence`。內部捲動面板要確認沒有漏段、重複、錯位或浮層覆蓋。
- full-page 可能重排、改變 lazy content 或讓固定頁首覆蓋內容。每張 raw 拍完後以實際輸出尺寸和已知控制項重新校準；不能用 `pngHeight / viewportHeight` 當全頁倍率，也不能把拍攝前 DOM 座標直接當成 PNG 座標。校準依據要寫進該張 manifest／QA record。
- 彈窗保留其所在頁面背景和完整彈窗；內容過長時依連續 viewport 規則補齊。欄位、按鈕、錯誤訊息的 detail 圖只能補充，不能取代主圖。
- 使用者未明示時保留實際系統截圖，不生成或重繪 UI。取得不到適用實圖時標為待補證據／draft，列明缺件；不得以示意圖冒稱 screenshot。

覆蓋表逐項列出功能 ID、章節、必要操作／狀態、主圖、detail 圖、manifest、最終文件位置、隱碼／標註／讀回／review 狀態與缺件原因。每個必要操作／狀態都必須能回指某張完整主圖；少量代表圖、圖片數量或只檢查嵌入圖片不代表整體完成。

代表圖先在文件實際顯示尺寸閱讀；若 6in 左右的全頁主圖讓文字縮到約 4–5px、無法操作或辨識，先補能指出該操作的 detail 圖，再批量取證。detail 是可讀性補充，不取代完整主圖，也不要求把主圖改成局部裁切。

## 失敗與停止

| 失敗點 | 處理 |
| --- | --- |
| 截圖未落地或檔案不可讀 | 先讀當前 CUA/browser capability；若 API 實際回傳 bytes 且同一 runtime 允許 Node `fs.writeFile`，直接保存後再 canonicalize、重算 hash。沒有 fs 或 bytes 型別不符時，記錄具體 runtime／API／型別錯誤並待補；不走 clipboard→PowerShell 或 `CopyFromScreen`，native capture disabled 也不換另一套 native capture。 |
| full-page 座標錯位 | 以該張 raw 實際尺寸、scroll 定義及校準 controls 重新測量，不能套用固定比例。 |
| 敏感值過多或遮蔽影響閱讀 | 精準遮蔽值，保留 labels、controls 和金額；可改用已授權的測試資料，但不能改成空白／無結果狀態冒充成功。 |
| 嵌入／讀回不一致 | 回到已通過的圖片與 build manifest 查依賴，重建受影響 output 並重算 hash。 |

「目前無法隱碼」或「只有代表圖」不是縮小已確認範圍的授權。若外部證據確實阻擋，保持 draft／blocked，列出已完成數量、缺件和 evidence；不要停止可獨立完成的工作，也不要把 blocker 當 accepted limitation。
