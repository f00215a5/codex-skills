# 截圖標註與渲染 QA

在有截圖、紅框、游標標註或 DOCX 渲染時閱讀本規格。標註語意 QA 與 DOCX 版面 QA 是兩個必經關卡。

## 0. 結果回報邊界

所有 renderer 偵測結果、權限問題、fallback 與未完成的視覺驗證，必須**對話中向使用者回報**。它們**不得寫入 DOCX**；交付文件只保留使用者確認的操作內容，不得在使用提醒、表格、圖說或更新紀錄加入執行環境警語。

## 1. 標註語意 QA（先於 DOCX 建置）

每張標註圖建立**結構化 manifest**，並與 raw、redacted（如有隱碼）、annotated PNG 一起保存於受限 QA 工作區。raw 圖只作來源比對，不得進入交付封裝、DOCX 媒體或 reviewer 報告；每筆至少記錄：

```json
{
  "sourceImage": "raw/create-task.png",
  "originalImageSize": { "width": 1920, "height": 1080 },
  "viewportCssSize": { "width": 1536, "height": 864 },
  "annotations": [
    {
      "id": "1",
      "controlName": "儲存",
      "caption": "紅框 1：儲存按鈕。",
      "bbox": { "x": 1050, "y": 670, "width": 92, "height": 40 },
      "source": "dom",
      "status": "verified"
    }
  ]
}
```

manifest 必須保留**原始截圖尺寸**、控制項名稱、座標、caption 編號、標註來源與驗收狀態。每個紅框／游標對應一筆資料；圖說只能使用已驗收項目的 id 與控制項名稱。

能取 DOM 時，先以 `getBoundingClientRect` 取得控制項邊界。把 CSS viewport 座標按原始 PNG 的寬／高**比例換算**為候選框座標；不要假設截圖倍率為 1。一般 viewport 截圖可依序換算 `x = rect.left × pngWidth / viewportWidth`、`y = rect.top × pngHeight / viewportHeight`；全頁截圖還要把捲動位移納入 y 座標。人工操作只做**最終微調**，並將來源改為 `manual-adjusted`。

在 **DOCX 建置前**，將 raw + annotated 以 **100%** 並排檢視。逐筆通過以下清單才將 `status` 設為 `verified`：

1. raw 圖中確實有 manifest 指定的控制項，且紅框完整框住該控制項，不框到鄰近控制項或空白。
2. 紅框編號、manifest id 與 caption 編號三者一致；caption 使用畫面上的實際名稱。
3. 框線、編號和游標不遮蔽控制項文字、輸入值或錯誤訊息。
4. 截圖顯示的狀態與步驟相符（例如按鈕可用、對話框已開啟、成功訊息已出現）。

**紅框、編號、caption 三者一致**是獨立的交付條件。Word／LibreOffice 會驗證圖片是否被裁切、縮放或排版錯誤，**不能取代標註語意檢核**；若 raw 圖上的座標就錯，最終 DOCX 等比嵌入也無法修正它。

上述 manifest 的 `verified` 是標註製作階段的狀態，不代表獨立交付審核已通過；交付前仍須依 [independent-delivery-review.md](independent-delivery-review.md) 由 reviewer 直接檢查成品、需求與原始證據。

## 2. 渲染環境與錯誤分類

UI 操作說明書的 renderer 工作根目錄、Word／LibreOffice fallback 與政策記憶，統一依 [safe-word-render-policy.md](safe-word-render-policy.md) 執行。該政策要求 `word-render` 的 `--work-dir` 使用 `~/.codex/tmp/word-render`；不要在專案內另建一個 renderer 根目錄，也不要自行放寬 fallback。渲染輸出與只供本次程序使用的設定檔仍可放在已授權的任務工作區：

- `TEMP/TMP`、`WORD_RENDER_TEMP_DIR` 指向本次任務的可寫入輸出／暫存子目錄。
- 需要使用者設定檔的 renderer，將 `XDG_CONFIG_HOME`、`XDG_CACHE_HOME`（及適用的 HOME／profile 路徑）指向同一可寫入工作區下的子目錄；不修改使用者的永久環境變數。
- 不自行建立或預先初始化 LibreOffice 工作區。只有安全政策取得明確的本次／已記住 `allow` 後，才可由政策允許的 fallback 建立所需暫存資料。

若 DOCX 含 CJK live text，先依 [cjk-render-preflight.md](cjk-render-preflight.md) 用與正式文件相同的 renderer 驗證最小 glyph probe。PDF／PNG 產生成功但 probe 出現方框、替代字元或不可讀文字時，分類為 **CJK glyph 預檢失敗**；不可宣稱渲染驗證已通過。只有 LibreOffice 路徑可使用任務限定的 `FONTCONFIG_FILE` 重試；Word 路徑需改用 Word 可讀的已驗證字型。

依 `word-render` 先跑 `--check-only`，再渲染最終 DOCX。預檢失敗時使用下表與安全政策，不把一次受限環境的錯誤誤報為 Word 未安裝；safe policy 的 `deny`／`ask` 優先於一般 renderer fallback 說明。

| 類別 | 可觀察證據 | 後續處理與回報 |
| --- | --- | --- |
| **沙箱／路徑權限受限** | TEMP/TMP、XDG 設定檔或 profile 不可寫；存取拒絕；受限沙箱中的 COM 事件啟動失敗，例如「Word 無法開始事件」。 | 先以可寫入工作區路徑重試；仍受限時，在**已核准的本機互動環境**重試。記錄初次限制與重試結果；不得宣稱 **Word 不可用**。 |
| **Word 不可用** | 已設定可寫入路徑後，互動環境仍無法建立 Word COM 或 `word-render` 的 evidence 明確回報 Word route 不可用。 | 依 [safe-word-render-policy.md](safe-word-render-policy.md) 的 policy：`allow` 才可採用 `documents`／LibreOffice fallback；`deny` 或尚未取得本次選擇時停止 fallback，執行結構檢查並回報原因。 |
| **CJK glyph 預檢失敗** | 最終 renderer 產生 PDF／PNG，但 live CJK probe 出現方框、替代字元或不可讀文字。 | Word：使用 Word 可讀的已驗證 CJK 字型重跑。LibreOffice：取得使用者確認的字型目錄，建立任務限定 Fontconfig 後重跑。兩者均不可把 exit code 0 當成通過。 |
| **文件或其他渲染失敗** | Word 可啟動，但特定 DOCX 匯出／轉檔失敗。 | 保留 evidence，修正文件或依 `word-render` 記錄 fallback reason；不要歸因為紅框座標問題。 |

交付時在對話或外部 QA 紀錄記錄**最終實際 renderer**、engine、Word／Office 版本（若有）、頁數、是否有 fallback，以及與初次失敗相關的路徑處理。只描述最後成功的 renderer；不要將 review environment、權限或備援工具資訊寫入 DOCX。

## 3. DOCX 版面 QA（在標註驗收後）

使用 `word-render` 產生最終 PNG，逐頁 100% 檢查頁面裁切、截圖縮放、框線可讀性、caption 與圖像相鄰性、表格與分頁；表格置中與尺寸彈性判準見 [visual-consistency-standard.md](visual-consistency-standard.md)。DOCX 版面 QA 發現圖片框線偏移時，先回到 raw + redacted + annotated manifest 判斷是原圖座標、圖片裁切，還是文件版面問題；修正後重新執行兩道驗收。
