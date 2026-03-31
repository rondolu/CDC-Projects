---
name: code-review
description: 當使用者輸入 \code-review 或 \apply-fix，或當上下文明確包含程式碼規範和套用修正的相關章節時，請使用此技能。此技能將引導您完成程式碼審查流程，確保遵守定義的程式碼規範，並根據審查報告有效套用必要的修正。
---

# Code Review Skill

## 觸發時機（嚴格）

本 skill 僅在以下情況啟用：

1. 使用者輸入 `\code-review` 或 `\apply-fix`

若不符合上述條件，禁止輸出審查報告與 diff，並引導使用者改用 `\code-review`。

## Quick Reference

| Task | Guide |
|------|-------|
| 執行 code review | `coding-standards.md` + `review-workflow.md` |
| 套用報告 diff | `apply-fix-workflow.md` |
| 產生報告格式 | `report-template.md` |

## Chat 輸出政策

- 每次review報告的結果必須先用「內容覆蓋」方式更新 [Code_review_result.md](../../Code_review_result.md)，嚴禁殘留歷史內容。
- chat 介面不得輸出審查報告明細（包含 rules table、fail diff、coverage 明細、檔案清單等）。

## 執行順序（必用）

1. 先讀取本檔，確認觸發條件。
2. `\code-review`：依序讀取 `coding-standards.md`、`review-workflow.md`、`report-template.md`。
3. `\apply-fix`：讀取 `apply-fix-workflow.md`，並依報告來源解析 `diff` 套用。

## 執行後互動（必用）

- `\code-review` 完成後：在 chat 輸出一行確認訊息，詢問使用者是否執行 `\apply-fix` 套用 Fail❌ 修正。
- `\apply-fix` 完成後：在 chat 輸出一行確認訊息，詢問使用者是否執行 `\code-review` 驗證修正結果。