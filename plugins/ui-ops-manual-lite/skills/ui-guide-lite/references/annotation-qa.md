# 截圖標註與結構 QA（輕量版）

本技能的 QA 有兩道關卡：**標註語意 QA**（在組 DOCX 之前）與 **DOCX 結構 QA**（`verify_docx.py`）。本版以 Python 完成建檔與驗證，紅框座標的正確性必須在圖片層級完成，不能靠後續文件處理來「補救」。

## 1. 標註語意 QA（先於 build_docx.py）

每張要放進文件的原圖建立一份標註 manifest（JSON），與 raw、annotated PNG 一起保存。每筆記錄：

```json
{
  "sourceImage": "raw/create-task.png",
  "originalImageSize": { "width": 1920, "height": 1080 },
  "annotations": [
    {
      "id": "1",
      "controlName": "儲存",
      "caption": "紅框 1：儲存按鈕。",
      "bbox": { "x": 1050, "y": 670, "width": 92, "height": 40 },
      "cursor": { "x": 900, "y": 700 },
      "status": "verified"
    }
  ]
}
```

能取 DOM 時，先以 `getBoundingClientRect` 取得控制項邊界，把 CSS viewport 座標按原始 PNG 寬高**比例換算**成候選框座標：`x = rect.left × pngWidth / viewportWidth`、`y = rect.top × pngHeight / viewportHeight`（全頁截圖另加捲動位移）。人工操作只做**最終微調**並把來源改為 `manual-adjusted`。座標寫入 manifest 的 `bbox`，`annotate.py` 不會幫你重新對齊。

**在組 DOCX 之前**，把 raw + annotated 以 **100%** 並排檢視，逐筆通過以下清單才把 `status` 設為 `verified`：

1. raw 圖確實有 manifest 指定的控制項，且紅框完整框住它、不框到鄰近控制項或空白。
2. 紅框編號、manifest id 與圖說編號三者一致；圖說使用畫面上的實際名稱。
3. 框線、編號和游標不遮蔽控制項文字、輸入值或錯誤訊息。
4. 截圖顯示的狀態與步驟相符（例如按鈕可用、對話框已開啟、成功訊息已出現）。

每次組檔前執行硬檢查：

```text
<venv>/bin/python "<skill>/scripts/annotate.py" check \
  --image "<raw>.png" --annotations "<image>.json"
<venv>/bin/python "<skill>/scripts/annotate.py" draw \
  --image "<raw>.png" --annotations "<image>.json" --output "<annotated>.png"
```

`check` 對越界框、重複 id、圖說編號不一致、未驗證 status 一律**fail closed**；`draw` 畫出紅框與編號徽章（必要時依 manifest 的 `cursor` 畫游標箭頭）。徽章預設放在紅框左上角外側，空間不足時改置於框內角落，避免遮住控制項文字。

**紅框、編號、圖說三者一致是獨立的交付條件**。若 raw 座標就錯，嵌入 DOCX 只會把同一個錯誤等比帶進文件，必須在組檔前修正。

## 2. DOCX 結構 QA（組檔後）

`build_docx.py` 組出 DOCX 後，以 `verify_docx.py` 做可程式化的結構與語意檢查：章節順序、圖說順序與 build manifest 一致、每個操作小節獨立編號、欄位表欄位齊全、更新紀錄在文末、頁面與邊界符合基線、每張嵌入圖在套件內可解析、圖後必接圖說。檢查項目詳見 [document-structure-qa.md](document-structure-qa.md)；任何一項失敗即回傳非零 exit code，**不得宣稱文件通過驗證**。

`verify_docx.py` 不檢查、也不能檢查開啟後的字型取代、分頁斷行或版面美觀——這些屬於使用者的開啟端檢視，不屬於本技能的驗證範圍。
