# GitHub SSH 唯讀來源登錄

此檔是本 skill 安裝目錄的持久化唯讀來源登錄。僅在 gh CLI 無法讀取使用者確認的 GitHub Release／PR 資料時使用。它的目的是讓已驗證可用的 SSH 遠端在後續執行自動重用，直到過期或失效，不必再次詢問使用者。

## 安全邊界

- 只記錄 SSH host alias、Git remote、可讀取的 repository 範圍、驗證時間與狀態。
- 不得記錄或複製私鑰、passphrase、token、密碼、known_hosts 內容或完整 SSH 設定。
- 所有 GitHub 存取只可讀取。不得改動 GitHub 端資料，也不得修改使用者既有 repository 或 SSH 設定。
- 本檔不會被複製到 Excel、輸出檔或交付給使用者的工作成果。

## 目前登錄

目前沒有 active SSH 唯讀來源。

## 寫入與重用規則

第一次由使用者提供可用 SSH 來源時，將上方「目前登錄」改為一筆具備下列欄位的資料：

| 欄位 | 說明 |
| --- | --- |
| status | active 或 invalid |
| hostAlias | 使用者確認的 SSH host alias；沒有別名可留空 |
| remote | 使用者確認的 GitHub SSH remote |
| repositories | 允許唯讀的 repository 範圍 |
| addedAt / lastVerifiedAt | 建立與最近驗證時間 |
| expiresAt | 使用者有提供時才填寫 |
| invalidReason | 失效後的簡短原因 |

每次 SSH fallback 先驗證 active 項目的遠端 refs。驗證通過即使用並更新 lastVerifiedAt；不得再向使用者索取同一來源。驗證失敗、超過 expiresAt 或使用者撤銷時，改標為 invalid、更新 invalidReason，並改走使用者提供文件方案。只有使用者後續提供新的來源時，才新增或取代登錄。
