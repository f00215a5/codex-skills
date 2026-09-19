# 截圖標註與圖片 QA（輕量版）

本流程把「可產生預覽的幾何檢查」和「由能看圖的人確認語意」分開。輕量版不渲染 DOCX，但仍須在圖片層級核對隱碼與標註；`verify_docx.py` 或任何 exit code 都不能取代這項核對。

## 標註 manifest

標註應套用在已完成隱碼的 redacted PNG。raw 只供受限 QA 對照，不嵌入 DOCX。每張圖使用 [screenshot-manifest.md](screenshot-manifest.md) 的整合 JSON manifest；`redact.py` 與 `annotate.py` 消費同一份檔案，annotation 仍須回指 raw `captureState` 和 redacted hash。完整欄位與唯一示例以該 reference 為準；本頁不另抄一份 annotation-only schema。座標從當次 DOM 邊界按比例校準，人工只做最終微調並留下 provenance：

`provenance` 可使用 `dom-derived`、`manual-adjusted`、`captured`、`provided` 或 `reused`。`manual-adjusted` 只記錄人為微調來源，**不是批准**。

編號 badge 預設放在框外左上並在邊界內 fallback；若會遮住鄰近 control，可在同一 annotation item 以 `badgePosition`／`badge` 指定 `{ "x": ..., "y": ... }`，或指定 `anchor`（`top-left`／`top-right`／`bottom-left`／`bottom-right`）及 `offset`。工具會拒絕超出圖片的 badge，仍由 reviewer 直接確認沒有遮住旁邊 control。這是同一份 manifest 的可選欄位，不另造座標 schema。

能取 DOM 時，先用 `getBoundingClientRect` 取得控制項邊界，再依當張實際 PNG、device pixel ratio、scrollbar、full-page 是否重排和 scroll 定義校準。一般 viewport 只有在確認縮放模型後才可按 `x = rect.left × pngWidth / viewportWidth` 等比例換算；full-page 不可用 `pngHeight / viewportHeight` 當全局倍率，必須以該張圖的 known control／explicit calibration 重新測量並記錄。不要假設截圖倍率為 1。

## 先預覽，再核對，再批准

先以 `annotate.py check` 做幾何與 manifest 硬檢查。它會檢查整合 manifest 的來源 hash、原圖尺寸、座標邊界、正數寬高、重複 id、caption 的「紅框 N」與 id 一致性、cursor 邊界及狀態／provenance 值；沒有 `--require-approved` 時，允許 `proposed`、`pending` 與 `manual-adjusted`。錯誤即停止，修正後重跑。

接著產生可審閱的圖片預覽：

```text
Windows PowerShell:
& "<venv>\Scripts\python.exe" "<skill>\scripts\annotate.py" check --image "<redacted>.png" --annotations "<screenshot.json>"
& "<venv>\Scripts\python.exe" "<skill>\scripts\annotate.py" draw --image "<redacted>.png" --annotations "<screenshot.json>" --output "<annotated>.png" --provenance-output "<annotation-provenance.json>"
macOS/Linux:
"<venv>/bin/python" "<skill>/scripts/annotate.py" check --image "<redacted>.png" --annotations "<screenshot.json>"
"<venv>/bin/python" "<skill>/scripts/annotate.py" draw --image "<redacted>.png" --annotations "<screenshot.json>" --output "<annotated>.png" --provenance-output "<annotation-provenance.json>"
```

`draw` 可以處理 `proposed` 預覽；不能為了讓它執行而先填 `verified`。預覽完成後，能直接看圖的獨立 reviewer 將 redacted 與 annotated 以 100% 並排核對：

1. 紅框完整框住指定控制項，不框到鄰近控制項或不相關空白。
2. 紅框編號、manifest id、caption 編號與畫面上的實際控制項名稱一致。
3. 框線、編號與 cursor 不遮蔽控制項文字、輸入值、訊息或必要的已保留金額。
4. 截圖狀態與操作步驟相符，控制項的可用／鎖定狀態沒有被誤述。
5. 圖片已依 [screenshot-redaction-policy.md](screenshot-redaction-policy.md) 完成敏感資訊遮蔽，且 raw 不在交付包。

確認後才將每筆狀態改為整合 validator 支援的 `verified` 或 `checked`，再執行：

```text
Windows PowerShell:
& "<venv>\Scripts\python.exe" "<skill>\scripts\annotate.py" check --image "<redacted>.png" --annotations "<screenshot.json>" --require-approved
macOS/Linux:
"<venv>/bin/python" "<skill>/scripts/annotate.py" check --image "<redacted>.png" --annotations "<screenshot.json>" --require-approved
```

`--require-approved` 只是建置前的狀態門檻；它不能證明 reviewer 看過正確的控制項。builder 的 `verified` 也不能代替獨立交付審核。若圖片無法檢視，標註 `operation` 與隱碼相關 review 保持 `blocked`，不要填 pass；可繼續其他已授權工作並交付 draft。

`annotate.py draw --provenance-output` 會記錄 redacted 父圖、annotated 輸出和由 `id`、bbox、cursor、badge、stroke、font size 組成的 drawing-input hash。`pending`／`verified` 等 review status 不在 drawing input；改變父圖、bbox、id、cursor 或 badge 時，validator／正式 review 必須攔截舊 annotated artifact。獨立 review 的 `imageEvidence` 和 `reviewed_files` 也要列出並 hash 綁定這個自動產出的 annotation provenance。

## 交給 DOCX 與後續審核

正式交付的 annotated PNG 必須完成隱碼、標註 preview 與上述批准。為取得可審閱的成品，可以先在受限工作區組裝包含候選圖片的 draft，並清楚記錄待審狀態；不得將此草稿當成已審核交付物。`build_docx.py` 會拒絕明顯 raw／unredacted 圖片路徑，但不會從一個檔名推定隱碼或控制項語意；圖片與 manifest 仍由 reviewer 直接檢查。

`verify_docx.py` 只驗證 DOCX 結構、章節順序、編號、欄位表、圖片封裝與圖說相鄰性；它不能檢查像素、隱碼完整性、框線是否貼合控制項、字型替代或實際視覺可讀性。完成 DOCX 後依 [independent-delivery-review.md](independent-delivery-review.md) 綁定最終 DOCX、所有嵌入圖片、build manifest、整合 screenshot manifest／provenance、需求證據與 hash。更新紀錄位於標題區塊正下方的第一張表，不在文末。
