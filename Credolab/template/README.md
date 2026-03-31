# Credolab 範本（Template）總覽

此資料夾提供以本專案為基礎的「API 與批次處理」公版範本文件，協助其他開發者快速複製架構，只需依業務需求調整 SQL 與對外 API 發查端點，其餘流程與非功能性邏輯保留不變。

- 可調整的部分：
  - SQL 取數與轉換（`sql/` 目錄）
  - 對外 API 發查端點（路由與 Service 介面）
- 保留不變的部分：
  - 批次分頁與回呼（Recall）協作流程
  - GCS 上傳、BigQuery 插入、Cloud Logging 與 BigQuery 日誌寫入
  - Pub/Sub 訊息協作模式

快速導覽：
- TEMPLATE_OVERVIEW.md：架構概觀與責任切分
- CUSTOMIZATION_GUIDE.md：如何只改 SQL 與發查端點
- SQL_CUSTOMIZATION.md：SQL 參數與檔案說明
- API_ENDPOINTS.md：既有 API 規格與擴充方式
- CONFIG_REFERENCE.md：`config.yaml` 與程式使用的設定鍵
- DEVELOPMENT_WORKFLOW.md：開發與驗證流程（僅列出與程式一致的要求）
- LOGGING_AND_METRICS.md：日誌、指標與記錄位置
- ADOPTION_CHECKLIST.md：導入檢查清單

---

本範本內容皆以程式碼實際實作為準，文件內引用的類別/方法/檔名可於專案對應路徑中查核。
