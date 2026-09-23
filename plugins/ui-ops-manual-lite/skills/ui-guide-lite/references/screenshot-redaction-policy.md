# 截圖來源與隱碼政策（輕量版）

在擷取、選用或嵌入 UI 畫面時閱讀本規格。輕量版沒有 DOCX renderer，但圖片層級的隱碼與語意檢查仍然必須完成；沒有 renderer 不等於可以略過圖片核對。

## 來源模式

操作畫面預設使用實際系統截圖，保留真實欄位、控制項、狀態、位置與版面關係。只有使用者明確要求示意圖、重繪圖或簡化圖時，才可對明示的圖或範圍使用 `sourceKind: "schematic"`，並在 manifest 以 `schematicApproved: true`（或 `allowSchematic: true`／來源物件的 `approved: true`）留下批准依據。時間壓力、版面方便或截圖尚未處理都不構成明示。

每張圖記錄下列其中一個 `sourceKind`：

- `captured`：本次從實機擷取。
- `provided`：使用者提供的截圖。
- `reused`：舊文件沿用，且已確認畫面版本與流程仍適用。
- `schematic`：使用者明示並已記錄批准的示意圖。

取得不到適用的實際畫面時，將該畫面標為待補證據或 draft，並說明缺少的證據；不得把重繪圖標成 screenshot。`build_docx.py` 會拒絕未獲明示核准的 schematic 圖。

## 預設敏感資料邊界

除非使用者或資料政策明確修改範圍，下列值一律遮蔽：

- 姓名、身分 ID、客戶／會員／員工 ID 及其他可識別人的識別資料。
- 地址、電話、電子郵件及其他可定位或聯絡個人的資料。
- 保單號、帳單號、合約號，以及同類交易、案件或文件識別碼。
- 密碼、權杖、API key、session 值及不應外流的內部帳號或業務識別值。

`redact.py`／validator 接受的類別就是上述識別資料的有限集合：`name`、`identity-id`、`customer-id`、`member-id`、`employee-id`、`address`、`phone`、`email`、`policy-number`、`bill-number`、`contract-number`、`transaction-id`、`case-id`、`password`、`token`、`api-key`、`session-value`、`internal-account` 和（有明示政策時）`amount`。類別名稱本身不是遮蔽理由；每個 bbox 仍須有該任務的資料依據。

`internal-account` 只指可識別的帳號、內部識別碼或不可外流的業務識別值。看到「科目」、「帳」或 `IFRS4` 不代表整欄都要遮；日期、金額、科目分類、欄名等非識別操作資訊預設保留，確需遮蔽時要記錄具體任務／政策依據，不能因關鍵字命中就過度遮蔽。

**金額預設保留**，以免破壞操作、計算或結果說明。只有使用者或資料政策明確要求時，才在 manifest 記錄 `amountPolicy: "mask"` 並新增 `amount` 遮蔽項目；圖說不得把仍可見的金額宣稱為已遮蔽。重複出現在頁首、彈窗、通知或其他畫面的同一識別值也要遮蔽。

欄名、button／icon labels、操作提示和必要 controls 預設保留並可讀。`protectedAreas` 只框住不可遮蔽的 controls／labels；敏感值與操作 control 相鄰時縮小 redaction bbox 到實際值，不用整欄或整列黑條遮住用途。

manifest 只記錄類別、座標、方法、狀態與檔案雜湊，不記錄原始值、明文文字或可反推出原值的替代文字。`redact.py` 會拒絕 `value`、`raw_value`、`plaintext` 等敏感值欄位。

## raw 到可交付圖片

保留 raw 原圖於受限 QA 工作區，使用 [screenshot-manifest.md](screenshot-manifest.md) 的整合 manifest，依下列順序產生可交付圖片：

1. 建立整合 screenshot manifest，至少包含 `schema_version`、`sourceKind`、`captureKind`、`sourceImage`、`sourceSha256`、`captureState`、`originalImageSize`、`redactedImage`、`annotatedImage`、`protectedAreas`、`redactions`、`annotations` 和 `reviewStatus`。每筆 `redactions` 包含 `category`、`bbox`、`method` 和 `status`；`method` 使用 `opaque-rectangle` 或 `pixelate`，`status` 初始可為 `pending`。同一張圖的 annotation 直接放在這份 manifest，不另造第三套來源。
2. 以 `redact.py draw` 產生扁平化 PNG；輸出不得覆寫 raw 或 manifest，可另寫 `--provenance-output`。provenance 保存 `sourceSha256`、`redactedSha256`、來源分類與安全的遮蔽清單。
3. 先用 `redact.py check --image <raw> --redacted <redacted> --manifest <screenshot.json> --provenance <provenance.json>` 檢查來源 hash、尺寸、PNG 格式、capture state、protected area 和座標邊界；此時允許 pending，不預填 checked。
4. builder 先以 100% 直接檢視 raw／redacted 對照，自查識別資料真的不可讀、遮蔽範圍沒有漏掉或誤遮操作資訊，確認後更新為 checked，再執行同一 check 命令並加上 `--require-checked` 以繼續 draft／建置；這個 checked 只是 builder 自查，不能當成獨立 pass。最終交付仍須由能直接檢視圖片、且不同於 builder 的獨立 reviewer 重新檢視並完成 review。狀態更新不可改寫既有來源／圖片 hash；若同時更動座標或圖片，先重新產圖並核對。
5. 只以 redacted PNG 進入標註和 DOCX；raw、未扁平化原圖與包含敏感值的中間檔不得進入 DOCX 或交付資料夾。reviewer 可在受限 QA 工作區讀取原始證據作對照；審核紀錄只保存不含敏感值的定位與 hash，不內嵌或複製原圖。

`redact.py` 的矩形與 hash 檢查只證明列出的座標和檔案相符，不能證明敏感資料清單完整，也不能證明像素化結果在語意上足夠。若環境或 reviewer 無法看圖，`redaction` 與相關 `operation` review 必須保持 `blocked`；可繼續不依賴圖片審核的已授權工作，產物標為 draft。

## 與標註的交接

遮蔽完成後在同一整合 manifest 更新 annotation 欄位。標註流程見 [annotation-qa.md](annotation-qa.md)：先讓 `proposed`／`pending`／`manual-adjusted` 產生可檢視 preview，再做語意審核；`manual-adjusted` 是 provenance，不是批准。整合 manifest、provenance、redacted／annotated PNG 的 hash 必須在獨立 review 的 `reviewed_files` 中列出，圖片或 manifest 改動後重新審核。
