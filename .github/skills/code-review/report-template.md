# Code Review Report Template

> 內容只反映本次審查的實際檔案與現況，強制使用 zh-tw。

## 檔案

- `Code_review_result.md`

## 固定章節順序

**程式碼審查報告**

## Overall

- Status: <Fail❌ / Pass⚠️ / Pass✅>
- Reason: <簡要說明>
- 觸發到的場景（若有）

## Scope/Exclude

- Scope 來源：<來源描述>
- In Scope：<Python / SQL 等>
- Exclude：<排除項或 None>
- Exclude Rules：<glob/類型/明確條件>
- Exclude Reasons：<reason_code + 原因>
- Excluded Count：<數量>

## Coverage

- Total_files: <N>
- Reviewed_files: <R>
- Unreviewed files: <U>
- Coverage: <R/N 或 N/A>
- Coverage Reason: <分母來源、枚舉方式、排除規則、缺漏原因>
- Global Progress（僅分批）：
  - Global Denominator Type
  - Global Total (N)
  - Global Reviewed (R)
  - Global Coverage
  - Completed Batches
  - Next

> Coverage < 100% 或 Coverage = N/A 視為 Fail(Coverage)：
> 仍需輸出 Overall / Scope-Exclude / Coverage，但**不得**輸出 Rules / Fail diff / CTA。

## Rules

> Coverage=N/A 時，此章節僅輸出：「因 Coverage=N/A，不輸出 Rules 表格」。

### Python 規則

| 規則類別 | 規則等級 | 狀態 | 詳細說明與修正建議 |
| :--- | :---: | :---: | :--- |
| **[Python][規則名稱]** | MUST / SHOULD / MAY | Pass✅ / Fail❌ / Warning⚠️ | [簡潔描述] |

> 規則名稱與判定條件僅可引用 `coding-standards.md`，本模板不可新增、覆寫、或細化任何規則條件。

> 若本次審查無 Python 相關規則：填入「本次審查無相關規則」。

### SQL 規則

| 規則類別 | 規則等級 | 狀態 | 詳細說明與修正建議 |
| :--- | :---: | :---: | :--- |
| **[SQL][規則名稱]** | MUST / SHOULD / MAY | Pass✅ / Fail❌ / Warning⚠️ | [簡潔描述] |

> 若本次審查無 SQL 相關規則：填入「本次審查無相關規則」。

### Checkmarx 規則

| 規則類別 | 規則等級 | 狀態 | 詳細說明與修正建議 |
| :--- | :---: | :---: | :--- |
| **[Checkmarx][規則名稱]** | MUST / SHOULD / MAY | Pass✅ / Fail❌ / Warning⚠️ | [簡潔描述] |

> 若本次審查無 Checkmarx 相關規則：填入「本次審查無相關規則」。

---

## Fail diff

- 修改建議：Pythonic Thinking，並實踐 The Zen of Python（如：Simple is better than complex）
- 格式：一律使用 Markdown 的 unified diff（請用 ```diff 程式碼區塊）。
- 檔案路徑（必用：diff header 必須使用 repo 相對路徑，且採用 `--- a/<path>` 與 `+++ b/<path>`。
  - 禁止輸出 Windows/Unix/UNC 絕對路徑（避免 `/apply-fix` 因安全限制拒絕）。
- 對應關係：每個 **Fail❌ 規則**都必須輸出修正內容。
  - 同一規則若影響 **多個檔案**：允許在表格同一列列出多個檔案，但修正區塊必須 **每個檔案各輸出一個 diff block**（同一規則可有多個 diff block）。
- Context 行數固定：每個 diff hunk 需保留變更行 **前後各 2 行**的 context（等效 `-U2`）。
- 允許省略：可省略與該 Fail 無關的區段/其他 hunks，但必須在 diff block 中插入固定格式的省略標註行：
  - `# ... 省略：<函式/區塊名稱>（原因）...`

**規則（Fail❌）：[規則名稱]**

**檔案：[請填寫原始的檔案名稱，例如 application/main.py]**

```diff
--- a/application/main.py
+++ b/application/main.py

@@ -1,9 +1,9 @@

 def example_function():
  existing_line_1 = 1
  existing_line_2 = 2
- old_behavior = do_old_thing()
+ new_behavior = do_new_thing()
  existing_line_3 = 3
  existing_line_4 = 4
  existing_line_5 = 5

# ... 省略：example_function（略過不相關區段）...

 def another_function():
  existing_line_a = "a"
  existing_line_b = "b"
  existing_line_c = "c"
  existing_line_d = "d"
-   return legacy_value
+   return improved_value

```

---

## CTA

- Coverage=N/A：不得輸出 CTA
- Coverage=100% 且有 diff：
  - 若要自動套用修正，請使用 `\apply-fix`
  - 若要包含 Warning⚠️，請使用 `\apply-fix --include-warning`
- Coverage=100% 且僅提供 Diff Index：
  - `\apply-fix --from .code-review-batches/batch-<NN>.report.md`
  - `\apply-fix --include-warning --from .code-review-batches/batch-<NN>.report.md`
