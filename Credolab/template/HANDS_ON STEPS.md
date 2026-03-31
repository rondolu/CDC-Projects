# HANDS-ON STEPS：新 API 專案使用步驟（只改 SQL 與外部 API 端點）

本文件提供最短路徑把此專案作為可複用的 API/批次處理範本：僅修改 SQL 與外部 API 發查端點，其他批次/Recall、儲存、日誌與訊息機制維持不變。

---

## 你要改的地方（速查表）

- SQL（取數與轉換）
  - 修改檔：`sql/get_vmb_data.sql`、`sql/get_vmb_data_range.sql`、`sql/flatten_data_android.sql`、`sql/flatten_data_ios.sql`
  - 替換資料集/表名（SQL 內為靜態字串）：`RAW_VMB_DATASET`、`RAW_HES_DATASET`、`TRANS_HES_DATASET`、`RAW_EDEP_DATASET`、`TRANS_EDEP_DATASET`
  - 保留/使用參數：`@start_date`、`@end_date`（range）、`@partition_date`（flatten）
  - 確保載入 SQL 回傳欄位：`cuid`、`reference_id`、`device_os`、`serial_number`
  - 檢查 `sql/get_vmb_data_range.sql` 結尾 `limit 1` 是否要移除（若要全量處理區間）。

- 外部 API（發查端點）
  - Client：`infrastructure/credolab_client.py`
    - 調整 `base_url`（來自 `config.credolab_base_url`）、授權取得方式（`utils/secret_services.SecretManagerService`）、`get_insights()` 的路徑/參數
    - 速率/重試/代理：`credolab_qpm_limit`、`credolab_max_retries`、`credolab_timeout`、`credolab_proxies`
  - Service：`services/credolab_api_service.py`
    - 盡量維持 `get_credolab_insights(reference_number, api_codes=None)` 介面，或提供等價方法
    - 若更動回傳資料結構，請確認 `utils/data_processor.prepare_raw_data_for_bq` 仍可序列化

- 設定（`config/config.yaml` 對應 active project_id 區塊）
  - `gcp.project_id`、`gcs.bucket_name`、`gcs.blob_path`
  - `pubsub.credolab_topic`、`pubsub.anonymization_topic`
  - `bigquery.raw_edep_dataset`、`bigquery.log_dataset`、`bigquery.api_dataset`、各表名鍵（android/ios/failed_retry）
  - `credolab_api.base_url`、`timeout`、`max_retries`、`batch_size`、`qpm_limit`、`api_codes`、`secret_version_name`、`proxies`

## 1) 先掌握架構與責任邊界
- 參考：`template/TEMPLATE_OVERVIEW.md`
- 了解哪些檔案負責什麼、哪些是穩定的模板層（批次切分/Recall、GCS/BQ、Logging、Pub/Sub）。
- 你主要只需改：`sql/` 內 SQL 與外部 API client/service；其他流程不動。

## 2) 設定環境與 config 鍵位
- 參考：`template/CONFIG_REFERENCE.md`
- 在 `config/config.yaml` 新增/調整與目標 `project_id` 相符的環境段落（程式會用 ADC 取得 `project_id` 決定 active 區塊）。
- 確認資源存在且名稱一致：
  - BigQuery datasets/tables（與 SQL 檔中的名稱一致）
  - GCS bucket 與 `gcs.blob_path`
  - Pub/Sub topic：`pubsub.credolab_topic`、`pubsub.anonymization_topic`
- 確保部署/執行環境具備 ADC 與 BQ/GCS/PubSub/Logging 權限。

## 3) 調整 SQL（取數與轉換）
- 參考：`template/SQL_CUSTOMIZATION.md`
- 載入原始資料：
  - Daily：`sql/get_vmb_data.sql`（無需參數）
  - Range：`sql/get_vmb_data_range.sql`（需要 `@start_date`、`@end_date` 參數，由程式傳入）
- 最終轉換：
  - `sql/flatten_data_android.sql`、`sql/flatten_data_ios.sql`（需要 `@partition_date`，最後一批完成或單批完成後自動執行）
- 重要：SQL 檔內的 dataset/table 名稱目前為靜態字串，若環境不同請直接修改 SQL。
- 必要欄位（供程式使用）：載入 SQL 回傳每列至少要有 `cuid`、`reference_id`、`device_os`、`serial_number`。

## 4) 置換對外 API 發查端點（只動 client/service）
- 參考：`template/CUSTOMIZATION_GUIDE.md`
- 調整檔案：
  - Client：`infrastructure/credolab_client.py`（base URL、授權、query 參數、重試/錯誤處理）
  - Service：`services/credolab_api_service.py`（維持 `get_credolab_insights(reference_number, api_codes=None)` 或等價介面）
- 設定同步更新：`config/config.yaml` 的 `credolab_api.*`（如 `base_url`、`timeout`、`max_retries`、`qpm_limit`、`api_codes`、`proxies` 等）。
- 確保回傳資料可被 `utils/data_processor.py:prepare_raw_data_for_bq(original_record, api_response)` 正確序列化為 `raw_data` 寫入 BQ RAW 表。

## 5) 路由與 Recall 訊息格式確認
- 參考：`template/API_ENDPOINTS.md`
- 既有路由（`blueprints/credolab_routes.py`）：
  - POST `/` → `services/dataflow_service.py:DataFlowService.handle_daily_request`
  - POST `/get_data_range` → `DataFlowService.handle_date_range_request`
- Recall 訊息（由 `utils/pubsub_services.PubSubService` 發布）：
  - Daily（送往 `/`）：attributes 需帶 `start_date:""`、`end_date:""`（空字串），`message.data.message_type = "daily_recall"`
  - Range（送往 `/get_data_range`）：attributes 帶有值的 `start_date`、`end_date`，`message.data.message_type = "range_recall"`

## 6) 依流程驗證（不需改模板流程）
- 參考：`template/DEVELOPMENT_WORKFLOW.md`
- 驗證動作：
  - Daily：呼叫 POST `/`（可帶 `device_type`），觀察首批完成後發布 recall。
  - Range：呼叫 `DataFlowService.process(start_date, end_date, device_type)` 或推送對應 Pub/Sub 訊息，觀察回呼循環。
- 成功資料：
  - GCS：`config.gcs_bucket_name` + `config.gcs_blob_path`
  - BQ RAW 表：依 `device_os` 分 Android/iOS（表名由 `modules/config.py` 組合屬性提供）
- 失敗資料：`CREDOLAB_FAILED_RETRY_LIST`（表名見 `config` 組合屬性）
- 最終：最後一批完成後執行 `flatten_data_*.sql`，成功時發布匿名化通知（Pub/Sub）。

## 7) 觀測與問題排查
- 參考：`template/LOGGING_AND_METRICS.md`
- Flow/API Log：寫入 BigQuery 對應表，並輸出 Cloud Logging（見 `utils/infra_logging.py`）。
- 每分鐘指標：`utils/metrics.py` 於分鐘切換時列印 API 呼叫、BQ 寫入操作次數摘要（stdout）。
- 路由錯誤：`utils/error_handling.py:handle_route_exceptions` 統一轉 JSON 回應。
- 批次內錯誤分類：`application/batch_process_service.py:_handle_operation_error`。

## 8) 上線前核對清單
- 參考：`template/ADOPTION_CHECKLIST.md`
- 勾選設定、資源、必要欄位、流程驗證、權限等是否完整。

---

## 常見陷阱（快速避雷）
- SQL 內的 dataset/table 名稱是靜態字串，請直接改檔案以符合環境。
- 載入 SQL 若未回傳 `reference_id`/`device_os`/`serial_number` 會導致下游寫入或分流失敗。
- `device_os` 請用 `android` 或 `ios`（小寫）；未知值會被跳過或無法分流到對應表。
- 執行環境需具備 ADC 與 BQ/GCS/PubSub/Logging 權限，否則 client 初始化或查詢會失敗。
- Recall 訊息 attributes 與 `message.data` 結構需與 `utils/pubsub_services.py` 相符，否則路由無法識別回呼。
- 失敗清單表結構需與 `application/bigquery_service.py:insert_failed_record` 寫入欄位一致。

## 可選強化（擴散為通用範本）
- 將 SQL 的 dataset/table 名參數化（在 `BigQueryService.run_sql_file`/`execute_query` 注入自訂參數）。
- 抽象外部 API 介面（固定 `get_credolab_insights` 的介面型態，新增供替換的 adapter）。
- 做成 Cookiecutter 或 Repo Template，輸入專案代碼與 datasets 後自動生成初始結構。
