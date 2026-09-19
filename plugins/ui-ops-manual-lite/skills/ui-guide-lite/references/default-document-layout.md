# 預設 DOCX 版面基線（輕量版）

將此基線套用到沒有既有範本的繁體中文系統 UI 操作說明書。plugin 規範決定章節、步驟和證據要求；既有文件只提供視覺參照，不把專案名稱、畫面或資料帶入共用基線。此基線是唯讀預設；使用者要求調整時，先建立可追溯的新版本副本並記錄基線版本與偏離，不覆寫原始基線。

## 文件順序與版面

1. 標題、副標題、適用畫面。
2. 標題區塊正下方的單一「更新紀錄」表，依舊至新排列 `版本`／`日期`／`更新內容`。
3. 修訂狀態，再是可選的版本依據、使用提醒、共通操作規則和功能章節。

預設 Letter 直式，左右約 0.65 in、上約 0.67 in、下約 0.59 in；`fontName` 和 East Asian／`zh-TW` 設定依 manifest 與本版 builder。文字、圖片、圖說和表格依其容器對齊。這些是結構／builder 基線，不代表字型、分頁或換行已實際渲染驗證。

表格相對所在容器的可用內容區置中；由 section page width 扣除左右 margin 計算可用寬。`tblW`、`tblGrid` 欄寬總和和每列 `tcW` 必須一致，不超過可用寬；合法窄表可依內容彈性調整但不能漂到左側。不要用固定像素寬度或固定列高；欄寬、總寬和列高應由內容與版型彈性決定。圖片未指定 display 尺寸時，`build_docx.py` 以 6 in 寬度起算並保持來源比例；寬度仍須落在容器可用寬，7.5 in 高度是保守的結構風險門檻。圖片若有明確 `width`／`height`，必須落在容器範圍並保留比例；不得以 7.5 in 或任何預設高度宣稱內容一定可讀或已通過分頁。

## 真正的 Word numbering

每個操作小節建立獨立的 `abstractNum` 與 `num`；`nsid`、`abstractNumId`、`numId` 不重複，使用 level 加 `w:lvlOverride`／`w:startOverride w:val="1"`。步驟段落以 `w:numPr` 指向該節 num；不要把 `1.` 寫成普通文字，也不要只換 numId 而共用會續號的 definition。`numbering.xml` 中所有 `abstractNum` 應位於 `num` 前，引用必須存在。

lite 可用 OOXML／結構檢查攔截 numbering 定義缺失、引用不存在或重啟設定缺失；沒有 renderer 時，不能宣稱畫面上實際從 1 顯示到最後。若未來由使用者在 Word 中開啟發現續號，回到 numbering definition 修正並重跑結構與獨立 review。

## 結構風險門檻

`verify_docx.py`／`audit_delivery.py` 應攔截或明確標示下列可機械判定風險：表格／圖片超出可用容器寬高、固定列高／固定像素高度、表格欄網格與 cell 寬度不一致、錯誤對齊、缺圖說、relationship 遺失、raw／未遮蔽圖片、嵌圖尺寸或 hash 失配，以及 numbering 結構問題。動態寬度、合併儲存格或無法機械推斷的合法例外交由獨立 reviewer 依 evidence 判讀，不靜默忽略。

完成 build 後必須讀回真正 DOCX，走讀主要流程、文字、表格、嵌圖、圖說、媒體 hash 和結構；可用 Pillow 依實際嵌入尺寸產生內容預覽。內容預覽、`verify_docx.py` exit 0 或 `audit_delivery.py` exit 0 都不證明 Word renderer、分頁、字型替代、換行或最終視覺 pass。`render_visual` 只能是 `not_performed`／`out_of_scope`，並在對話或 QA record 說明。
