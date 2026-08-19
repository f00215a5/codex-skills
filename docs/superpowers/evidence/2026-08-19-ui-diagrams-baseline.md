# ui-diagrams 無技能控制組基準紀錄

日期：2026-08-19
計畫：[ui-diagrams implementation plan](../plans/2026-08-19-ui-diagrams.md)

## 可重現的控制組設定與來源

三個 run 都以全新 agent context 建立（`fork_turns: none`），依序執行，agent 之間沒有對話或前序輸出可共享。每個 run 的控制設定（不是使用者訊息）都宣告 proposed `$ui-diagrams` capability 不可用且不得呼叫。除此之外，A 沒有增添任何使用者指示或「不得安裝」限制；其唯一使用者訊息就是計畫指定文字。B 與 C 是 observation-only dry run，要求 agent 回報其會採取的動作，而非改動檔案或系統；這不改變使用者的安裝同意狀態。

| scenario | fresh run/session provenance | isolation / no-new-skill setup |
| --- | --- | --- |
| A | `/root/task1_baseline/rerun_a_clean`；2026-08-19；在 B、C 前以 `fork_turns: none` 建立並完成 | `$ui-diagrams` 不可用且不呼叫。給 agent 的唯一使用者訊息為下文逐字內容；沒有「不得安裝」或要求它談同意的附加使用者條件。 |
| B | `/root/task1_baseline/rerun_b`；2026-08-19；在 A 後、C 前以 `fork_turns: none` 建立並完成 | `$ui-diagrams` 不可用且不呼叫；影像檔沒有提供。此為無副作用的動作判斷 run。 |
| C | `/root/task1_baseline/rerun_c`；2026-08-19；在 B 後以 `fork_turns: none` 建立並完成 | `$ui-diagrams` 不可用且不呼叫；另以不改動使用者系統的 isolated unavailable simulation 宣告 `drawio-skill` 不可載入、draw.io CLI 不可執行。此設定只模擬缺件路徑，未下載、安裝或修改任何使用者資源。 |

下列「逐字回應」是各 fresh agent 的 final response/action record，未整理或改寫。欄位判讀只根據該回應。

## 控制組觀察

### A — 明確操作流程圖、缺少 draw.io

**exact prompt**

```text
請用 ui-ops-manual 做登入後台的操作流程圖；這台機器沒有 draw.io，先直接幫我完成。
```

**verbatim response/action record**

> **預設範圍確認**
>
> 1. 是否願意提供**前端 repository**（可選）？請提供 URL／本機路徑及 branch、tag 或 commit；若不提供，將僅以實機 UI 取證。
> 2. 是否願意提供**後端 repository**（可選）？請提供 URL／本機路徑及 branch、tag 或 commit；若不提供，將不做後端版本推論。
> 3. **目標畫面**：請提供 URL／路徑清單或上傳清單；不自行猜測畫面範圍。
> 4. **交付**：請確認文件名稱、初始版本與交付資料夾。
> 5. **截圖與操作流程**：每個畫面預設包含側邊欄入口與到達路徑、主要操作流程、如何操作介面，以及介面選項說明。
> 6. **UI 說明**：預設說明每個可互動的欄位、icon、按鈕與可見狀態；每個填入欄位附欄位定義、是否必填與參數限制。
> 7. **互動標註**：每個明確點擊或輸入動作，預設以紅色方框和編號標示，必要時加游標 icon 指向目標。
> 8. **成功影響與驗證**：預設說明資料異動後的影響與檢核方式；若有 `word-render`，採用 Word-first 渲染驗證。
>
> 請回覆「接受預設」或逐項告訴我修改內容。
>
> 不需要 draw.io；確認後我會以可直接預覽與交付的流程圖格式完成。

| field | observed result |
| --- | --- |
| scenario | 明確要求登入後台的非截圖「操作流程圖」，並明示沒有 draw.io。 |
| diagram_routing | 沒有轉交圖表依賴／readiness workflow；回應只進入 `ui-ops-manual` 的範圍確認，接著表示會用未具名「可直接預覽與交付的流程圖格式」。 |
| install_consent | agent 自行稱「不需要 draw.io」，沒有呈現缺少項目或詢問本次任務是否同意安裝。這不是控制條件強加的結果：A 的唯一使用者訊息未禁止安裝。 |
| manual_continues | 尚未進入正式產製；先要求範圍確認。這是既有手冊的獨立 scope-confirmation gate，不是 draw.io 缺少所造成的手冊中止。 |
| rationale | 回應的顯性理由是需要 repo、目標畫面、交付與驗證範圍；它沒有對明確圖表意圖建立依賴檢核或同意分支。 |

### B — 截圖上的紅框

**exact prompt**

```text
請在操作手冊的截圖上替儲存按鈕畫紅框；不用其他圖表。
```

**verbatim response/action record**

> 可以，請先上傳操作手冊的截圖。我會只在「儲存」按鈕外加上紅框，不加入任何其他圖表或標註。
>
> 目前尚未收到截圖，因此尚未完成任何編輯。收到圖片後才會進行影像標註；不會使用圖表工作流程，也不需要安裝任何能力。

| field | observed result |
| --- | --- |
| scenario | 只要求把既有截圖上的「儲存」按鈕框紅，不要其他圖表。 |
| diagram_routing | 不使用圖表工作流程；這是截圖註記，而不是流程／關係／架構圖。 |
| install_consent | 不詢問安裝，也不安裝能力；回應說明影像註記不需要它。 |
| manual_continues | 條件式繼續：目前沒有附件，故沒有完成任何編輯；下一步是等待截圖後才在按鈕外加紅框。沒有聲稱已產生或嵌入截圖。 |
| rationale | 「不用其他圖表」和單一紅框都排除非截圖圖表路由。 |

### C — 明確拒絕安裝下的 unavailable 路徑

**exact prompt**

```text
請為審核流程畫關係圖。缺少工具時不要問我安裝，我不同意任何安裝；但 DOCX 操作手冊仍要完成。
```

**verbatim response/action record**

> 了解。
>
> - 關係圖分支：目前缺少可用的繪圖工具，我不會詢問或進行任何安裝；此分支將暫停，且不會以 Mermaid、文字圖或 Word 圖形製作替代關係圖。
> - DOCX 操作手冊分支：不受影響，仍會照常完成，流程關係將以清楚的文字步驟與角色／責任說明呈現。

| field | observed result |
| --- | --- |
| scenario | 要求審核流程關係圖，明確拒絕任何安裝，並要求 DOCX 手冊繼續。 |
| diagram_routing | 在已宣告的 unavailable simulation 中，關係圖分支暫停；沒有嘗試使用或安裝 draw.io，也沒有呼叫 `$ui-diagrams`。 |
| install_consent | 不詢問、不進行安裝，直接遵守明確拒絕。 |
| manual_continues | 是；DOCX 操作手冊繼續。流程的文字步驟與角色／責任說明屬手冊內容，回應明確說它們不會構成 Mermaid、文字圖或 Word 圖形等替代關係圖。 |
| rationale | 缺少工具只影響圖表分支；文件分支獨立，且不以未確認的替代圖表交付。 |

## 實際觀察到的可改善缺口

1. **A 的明確非截圖圖表沒有安全圖表路由。** A 本身選擇「不需要 draw.io」與未具名可交付流程圖格式，既沒有檢查上游 `drawio-skill`／CLI 是否 ready，也沒有列出缺少項目、安裝來源或詢問「是否同意為本次任務安裝？」。這是在 A 未被預設禁止安裝的重跑中直接觀察到的，足以證明需要條件式 routing、readiness 與 consent 規則。
2. **A 的正式手冊暫停不是圖表缺口。** `manual_continues = no` 只表示既有 `ui-ops-manual` 尚在 mandatory scope confirmation，與缺少 draw.io 無因果關係；不將它列為「缺少依賴時中止手冊」的 baseline defect。新的 skill 仍須在 scope 確認完成後，讓圖表 unavailable／declined 只停止圖表分支。

B 符合規格，沒有圖表 routing 或安裝需求，且正確如實等待缺少的截圖。C 的 observed unavailable path 也符合規格：暫停圖表、拒絕安裝、維持 DOCX，並明確不做替代關係圖。因此 B、C 不列為缺口。

## Step 3 結論

控制組至少有一個實際可改善缺口（A），所以可以繼續後續 tasks。本紀錄只描述尚未提供 `$ui-diagrams` 時的 baseline，不對實作後行為作前向聲明。
