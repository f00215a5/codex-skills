# CJK DOCX 渲染預檢

在繁體中文、簡體中文、日文或其他含 CJK **live text** 的 DOCX 任務中，於範圍確認後、擷取畫面與建立正式文件前執行本預檢。嵌入的 UI 截圖是像素，不可用來證明 DOCX 正文、圖說或表格字型可讀。

## 初始化關卡

1. 依 `word-render` 的 `--check-only` 判定本次最終 renderer；記錄 `word` 或 `libreoffice`、engine 與 fallback reason。
2. 為本次文件選擇一個**明確的 CJK 字型名稱**，並在 live text run 設定 `w:rFonts/@w:eastAsia` 與 `w:lang/@w:eastAsia="zh-TW"`。不得將「或等效字型」寫成未經驗證的實作。
3. 使用本外掛的 `scripts/create_cjk_probe.py` 產生暫存 probe DOCX。probe 包含 `繁體中文／臺灣／龜麵／險別管理／儲存／取消／欄位說明` 等 live text；不得以截圖取代。
4. 用與正式文件**相同的 renderer、環境變數、`--work-dir` 與 fallback policy** 渲染 probe，產生 PNG 並以 100% 檢視。若本技能採用 Word renderer，固定工作根目錄與 fallback 決策必須遵守 [safe-word-render-policy.md](safe-word-render-policy.md)。

範例（`<skill-path>` 為本 `SKILL.md` 所在目錄）：

```text
<bundled-python> "<skill-path>/scripts/create_cjk_probe.py" \
  --font-name "<confirmed CJK font name>" \
  --output "<workspace>/tmp_docx_render/cjk-probe.docx"
```

候選字型名稱可包含 Microsoft JhengHei、PingFang TC 或 Noto Sans CJK TC，但這些只是**候選**，不是跨平台預設。只有 probe 在本次 renderer 可讀後，才能選用。

## LibreOffice 字型發現失敗

若最終 renderer 是 `libreoffice`，probe 的 PDF／PNG 雖產生但 live text 出現方框、替代符號或不可讀文字，這是 **CJK glyph 預檢失敗**，不是成功的渲染驗證。

1. 請使用者提供或確認本機可存取、已核准的 CJK 字型目錄；不可自行安裝、複製或下載字型。
2. 在本次可寫入工作區建立 Fontconfig 設定與快取：

```text
<bundled-python> "<skill-path>/scripts/create_fontconfig_config.py" \
  --font-dir "<approved-font-directory>" \
  --cache-dir "<workspace>/tmp_docx_render/font-cache" \
  --output "<workspace>/tmp_docx_render/fontconfig-cjk.xml"
```

3. 僅對本次 renderer 子程序設定 `FONTCONFIG_FILE` 為輸出的 XML，並將 `XDG_CACHE_HOME` 指向同一任務工作區；不可修改使用者永久環境變數。以相同 probe、字型名稱與 renderer 重跑。
4. 若仍不可讀，停止宣稱「渲染驗證通過」。回報 renderer、字型名稱、已核准字型目錄、錯誤的 sample glyph 與已嘗試的 Fontconfig 路徑；可交付結構檢查結果，但須清楚標為未完成視覺渲染驗證。

`create_fontconfig_config.py` 只產生單次使用的 XML 與快取目錄，不會安裝字型或改動全域 Fontconfig 設定。

## Word 路徑

若最終 renderer 是 `word` 而 probe 不可讀，不要設定 Fontconfig。改為確認 Word 所在的互動桌面能使用指定字型；選擇另一個已確認的 CJK 字型後，重新產生並渲染 probe。

## 通過與記錄

僅在 live text 的每個 probe glyph 都可讀、沒有方框或替代字元，且 PNG 的版面正常時通過。記錄：最終 renderer、engine／版本（可得時）、CJK 字型名稱、probe 結果、是否使用單次 Fontconfig、字型目錄（不揭露敏感路徑時使用一般化描述）與最終 PDF／PNG 頁數。
