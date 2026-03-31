# AINative

這個資料夾集中放置以 BDD + SDD 為核心的專案知識與工件：
- 1-business-requirements.md：業務需求與成功標準（Business-Driven）
- 2-specs-and-acceptance-tests.md：可驗證規格與驗收情境（Spec-Driven）
- 3-automation-tests-plan.md：自動化測試計畫（單元、整合、資料/輸出斷言）
- 4-implementation-traceability.md：需求 ↔ 規格 ↔ 實作的對應關係

目的：
- 讓需求與程式碼維持可追蹤、可驗證、可維護
- 在需求變更時，有明確調整點與迴歸保護

維護建議：
- 新增/變更需求時，先更新 1 與 2，再調整程式與測試
- PR 應附上哪些 BR（Business Requirement）被影響、哪些 Spec 更新
- CI 可逐步導入針對 SQL/輸出格式的 spec 斷言（如以工具或自製測試實作）
