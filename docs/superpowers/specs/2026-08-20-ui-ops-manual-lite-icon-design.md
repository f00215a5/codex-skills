# UI 操作說明書（輕量版）圖標設計

## 目標

為 `ui-ops-manual-lite` 建立一個能在 Codex 外掛清單中與完整版明確區分的圖標，同時保留「UI 操作說明書」的產品語意。

## 已確認的視覺設計

- 使用靛藍綠色的圓角方形底色，與完整版的深綠系統介面圖示區分。
- 以白色單頁指南卡取代完整系統視窗，表達輕量、快速產製的使用情境。
- 卡片內有三列精簡清單與勾選記號，表示已整理的操作步驟。
- 右上加入青綠色閃光符號，傳達快速與低外部依賴；不使用文字、Python 標誌或產品名稱。
- 產出可編輯 SVG，並使用其產生等效 PNG；兩種尺寸沿用 manifest 既有 small／large 圖標欄位。

## 整合範圍

- 僅修改 `plugins/ui-ops-manual-lite` 的圖標素材、manifest 圖標路徑與對應結構驗證。
- 使用 `plugin-creator` cachebuster 更新既有外掛版本，並驗證 marketplace、plugin 與嵌入 skill。
- 完成後從既有 `codex-skills` marketplace 重新安裝 `ui-ops-manual-lite` 供使用者驗收。

## 非目標

- 不變更輕量版的 Python-only 文件產製、截圖標註、結構 QA 或 UI 圖表路由行為。
- 不變更完整版 `ui-ops-manual`、`ui-diagrams` 或 marketplace 的顯示名稱／排序。
