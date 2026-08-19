# GitHub Release／PR 唯讀流程

只在 CSV 已偵測到至少一筆待過版問題單、使用者已確認要更新待過版工作表，且已提供本次 Release 的 URL 或可定位 repository、tag、版本範圍後，才讀取 GitHub 資料。本流程所有 GitHub 存取都是唯讀；不得建立、修改或刪除 Release、PR、Issue、留言、branch、tag、repository 設定或 GitHub 認證。

## 來源與版號對照

1. 先由使用者提供的 Release 確定 repository、tag、發布時間與 Release body。Release 範圍有多個 tag 時，依使用者指定的起訖範圍處理；範圍不明先詢問，不能自動選最新版本。
2. 從 Release body 擷取 PR 參照，逐一讀取 PR title、body、merge commit、branch 與必要時的變更檔案。
3. 用問題單號、摘要、系統模組與 PR 證據建立對照。只有可明確支持的對照才填版本；如果 PR body 是預設文字，改以 title、branch、merge commit 與變更檔案輔助判斷，仍無法確認則列為待確認。
4. 將 Release tag 依已確認的後端／前端欄位填入待過版工作表。保留原表的格式與人工欄位，並在可用備註欄附上 Release／PR URL 或編號作為追溯依據。

## 取得順序

### 1. gh CLI（優先）

先檢查 gh 是否存在及目前登入是否具有讀取指定 repository 的權限。僅可使用讀取命令，例如 release list/view、pr view、repo view，以及明確指定 GET 的 API 查詢。不得執行 auth login、auth refresh、auth logout，或任何建立、編輯、合併、關閉、刪除、標籤、留言或上傳命令。

若 gh 不存在、未登入、沒有權限或讀取失敗，記錄失敗原因並轉入 SSH fallback；不要要求使用者在本流程中登入或變更權限。

### 2. 已登錄的 GitHub SSH 唯讀來源

僅在 gh CLI 無法取得資料時，讀取 [SSH 唯讀來源登錄](github-ssh-read-only.md)。若存在狀態為 active 的來源，先以唯讀的 GitHub Git 操作驗證它；驗證成功即沿用，毋須再次詢問使用者。

可透過 SSH 讀取 tag、遠端 refs、commit、branch 與 PR refs；可在獨立暫存工作區下載唯讀的 Git 資料，但不得修改使用者既有 repository、remote、branch、tag、SSH 設定或 GitHub 端資料。GitHub 的 SSH Git protocol 無法保證提供 Release body 或 PR description；因此只有從可讀 refs／commit 資料得到足夠證據時才填版號。缺少 PR 內容時，必須標示證據不足，改走第三方案。

若沒有 active 登錄，第一次才請使用者提供可讀取的 GitHub SSH remote 或既有 SSH host alias；取得後依登錄檔格式記錄。若已登錄來源在驗證時失效，更新其狀態與失效原因為 invalid，不再反覆詢問同一來源，並轉入第三方案。

### 3. 使用者提供文件

請使用者直接提供 Release notes、PR URL／清單、匯出的 Markdown／文字或其他可讀文件。依文件中的 tag 與 PR 內容進行相同的證據式對照；文件沒有足夠資訊時保留版號空白並列出待確認項目。

## 無法取得 GitHub 資訊

三種來源都無法提供足夠資訊時，在對話中明確說明不可用的方式與原因、哪些待過版問題單因此未填版號，然後繼續完成 CSV、問題單清單、概要及所有其他已確認可執行的工作。不得為了補版號而中止整份 Excel，也不得猜測版號。

