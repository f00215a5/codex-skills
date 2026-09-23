# 輕量版 plugin 開發驗收基準

本文件只用於 `ui-ops-manual-lite` plugin 的版本開發、回歸和 release candidate 驗收；一般製作 UI 手冊時不要求每次啟動三個模型。

## 固定模型與隔離

正式模型基準為：

| 模型 | 預設 reasoning | 用途 |
| --- | --- | --- |
| gpt-5.6-terra | medium | 與其他基準模型相同的完整驗收維度 |
| gpt-5.6-sol | low | 與其他基準模型相同的完整驗收維度 |
| gpt-6-astra | medium | 與其他基準模型相同的完整驗收維度 |

每次 plugin 回歸使用乾淨隔離的模型執行者：`fork_turns: "none"`、獨立工作資料夾／瀏覽器頁籤、相同的原始需求、凍結 plugin／原始碼和驗收規範。各模型獨立建立自己的需求骨架與 `scopeMatrix`／`fieldInventory`，不得共享前次對話、prompt 追加內容、截圖／DOCX、finding、修正建議、既有盤點或父任務產物；共用登入狀態與 runtime 若無法避免，須在 QA record 明確記錄。等待其他模型或文件工具的時間只計一次共享 wall time，不能重複累計。

## Luna 的範圍

Luna 排除於正式驗收基準。可以保留 Luna 的結果作能力觀察，但結果只能標為 `reference-only`，不得用來宣稱版本通過，也不得為了讓 Luna 達標而無限重建整份文件。若 Luna 失敗，仍要依同一 finding ledger 記錄證據與原因；正式決策只依 Terra、Sol 和 Astra。

## 驗收維度

每個模型只在 plugin 變更需要回歸時執行。驗收採文件可用程度與製作時間的平衡，不以「一輪完成」或圖片／頁數數量作為單一指標：

1. `scopeMatrix` 是否先覆蓋已確認的主／子配置區、獨特條件和最小代表案例；完整需求骨架與實際建置頁面分開記錄，不能用少量成品假裝完整範圍。
2. `fieldInventory` 是否只記錄實機／可追溯來源已確認的控制項、必填、值來源、條件與結果；未知項目明確標為 `unknown`／「待確認」。
3. raw → redacted → annotated → DOCX 的每條證據鏈是否可回溯，敏感值未漏遮且沒有遮住控制項／labels。
4. 主圖是否保留整個頁面上下文，標註框和編號是否貼合實際控制項；DOM 座標若無可驗證 viewport／clip transform，必須 `blocked`。
5. DOCX 是否通過 Python-only 結構／封裝／媒體 hash 檢查；`render_visual` 一律為 `not_performed`／`out_of_scope`，不能冒稱 Word 視覺 pass。
6. 同一缺陷同一策略連續兩次沒有改善，或已有證據顯示再整份重建不會提高主要可用性時，停止該策略，改做定點修正、明示範圍縮限或交付 draft／blocked；不得藉更改 status、刪除必要案例或沿用舊成品製造 pass。

正式結果至少保留每個模型的輸入 fingerprint、產物／證據 hash、實際 active／等待時間、finding ledger 和獨立 review 結論。`pass` 代表所有適用阻擋項已由獨立 reviewer 關閉；不能把 validator exit 0、DOCX 可開啟或 renderer 缺席當成完整驗收。
