# Apply-Fix Workflow

## 目標

在使用者輸入 `\apply-fix` 後，讀取報告中的 ` ```diff ` 區塊並自動套用到對應檔案。

## 啟動條件（必用）

<!-- - context 出現 `# /apply-fix — 自動套用審查修正` -->
- `--include-warning` 才允許套用 Warning⚠️
- `--from <report_path>` 時改讀指定報告檔

## 核心流程（必用）

1. 決定報告來源：預設 `Code_review_result.md`；有 `--from` 則使用該路徑。
2. 讀取報告並擷取所有 ` ```diff ` block。
3. 解析目標檔案路徑（`--- a/<path>` / `+++ b/<path>`）。
4. 執行安全檢查。
5. 依檔案分組後，以單次 `apply_patch` 套用該檔所有 hunks。
6. 回報成功/失敗與下一步。

## Fail / Warning 篩選（必用）

- 依 diff block 上方最近標題判斷嚴重度（Fail❌ / Warning⚠️）。
- 預設只套用 Fail❌。
- 若無法判斷，保守視為 Warning⚠️。

## unified diff 轉 apply_patch（必用）

### 1) 解析目標檔案

- 必須同時存在且一致：
  - `--- a/<path>`
  - `+++ b/<path>`
- 若路徑不一致：拒絕該 block。
- 若出現 `/dev/null`：拒絕（不建立、不刪除檔案）。

### 2) 轉換 hunk

- 忽略檔頭行與 `No newline` 標記。
- context 行（空白前綴）→ V4A 原文行
- 刪除行（`-`）→ V4A 刪除行
- 新增行（`+`）→ V4A 新增行

### 3) 套用策略

- 同檔案 hunks：一次 `apply_patch` 套用，避免半套用。
- 套用失敗（context mismatch）：不得猜測或手改，回報失敗並建議重跑 `\code-review`。

## 安全檢查（必用）

- 僅允許 repo 相對路徑
- 拒絕：`..`、絕對路徑（Windows/Unix/UNC）
- 目標檔案不存在即拒絕（不建立新檔）

### `--from` 安全限制

- `report_path` 必須是 repo 相對路徑
- 禁止 `..`、絕對路徑（Windows/Unix/UNC）
- 檔案不存在即拒絕

## 失敗處理（必用）

- 報告不存在或無 diff：不修改檔案，提示先跑 `\code-review`
- 任一檔案套用失敗：回報檔案與原因，建議重新產生 diff

## 輸出要求（必用）

回覆需包含：

- 讀取到的 diff block 數量
- 成功套用的檔案清單
- 失敗檔案清單與原因
- 套用完成後，詢問使用者是否執行 `\code-review` 重新驗證修正結果。
