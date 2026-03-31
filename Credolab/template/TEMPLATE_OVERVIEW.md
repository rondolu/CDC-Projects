# 架構概觀與責任切分（依據現有程式碼）

本範本來源於現有專案，以下為各層責任與檔案位置（僅列出實際存在之檔名與方法）。

- 進入點與路由
  - `main.py`：Flask 應用建立與錯誤處理器註冊。
  - `blueprints/credolab_routes.py`：
    - POST `/` → `DataFlowService.handle_daily_request`
    - POST `/get_data_range` → `DataFlowService.handle_date_range_request`
    - 路由均使用 `@Logging.logtobq(...)` 與 `@handle_route_exceptions` 裝飾器。

- Service 層（流程協調）
  - `services/dataflow_service.py`：
    - `process()`：自動判斷 daily / range 模式，建構 `BatchContext` 與回呼，調用核心批次流程。
    - `process_recall_batch()`：協調回呼批次處理。
    - `handle_daily_request()`、`handle_date_range_request()`：路由入口處理、解析 Pub/Sub 訊息。
    - 對 Pub/Sub 之 recall 訊息格式採用 `utils.pubsub_services.PubSubService` 中的 `publish_daily_recall_message` / `publish_range_recall_message` 所構造之 JSON 格式。

- 核心批次處理（商務邏輯保持不變）
  - `application/batch_process_service.py`：
    - 載入與分頁：`_load_vmb_data()`（選擇 `sql/get_vmb_data.sql` 或 `sql/get_vmb_data_range.sql`）
    - 首批處理：`_initiate_batch_processing()`
    - 單批協作：`_orchestrate_batch_processing()`（最後一批會執行 `flatten` SQL 與匿名化通知）
    - 單批記錄處理：`_process_batch_records()`（逐筆呼叫外部 API、寫入失敗清單、成功批次上傳 GCS 與 BQ、發布下一批）
    - 外部 API 呼叫：`_call_credolab_api()` → `services/credolab_api_service.py`
    - 完成後通知：`_publish_anonymization_notification()` → `PubSubService.publish_anonymization`

- 基礎設施與工具
  - BigQuery：`application/bigquery_service.py`
    - `execute_query()`、`insert_rows()`、`run_sql_file()`、`insert_failed_record()`
  - GCS：`utils/gcs_services.py`
    - `batch_upload_to_gcs()` 批次上傳
  - Pub/Sub：`utils/pubsub_services.py`
    - `publish_daily_recall_message()`、`publish_range_recall_message()`、`publish_anonymization()`
  - 外部 API：`infrastructure/credolab_client.py` + `services/credolab_api_service.py`
    - Client：Rate limit、重試、SSL/proxy、錯誤轉換
    - Service：`get_credolab_insights()`、`get_api_status()`
  - 日誌與指標：
    - `utils/infra_logging.py`（Cloud Logging + BQ Flow/API Log）
    - `utils/metrics.py`（每分鐘列印 QPS/BQ 寫入次數摘要）
  - 其他：`utils/error_handling.py`（路由錯誤處理）、`utils/data_processor.py`（`prepare_raw_data_for_bq`）、`utils/request_context.py`（請求範圍 Logger 共享接口）

- 設定：`modules/config.py` + `config/config.yaml`
  - 以 ADC 偵測到的 `project_id` 做為 active 環境鍵，讀取對應段落設定。
  - 程式透過 `Configuration` 物件的屬性讀取設定（如 `bq_credolab_table_android`、`gcs_bucket_name`、`pubsub_credolab_topic` 等）。

採用方式：保留上述層次與流程，僅在「SQL」與「外部 API 發查端點」進行替換或調整。

---

## 需要你修改的部分（指向精確檔案）

- SQL：`sql/` 目錄
  - 取數：`get_vmb_data.sql`（daily）、`get_vmb_data_range.sql`（range, 使用 @start_date/@end_date）
  - 轉換：`flatten_data_android.sql`、`flatten_data_ios.sql`（使用 @partition_date）
  - 若資料集/表名不同，請直接在上述 SQL 檔內替換 `RAW_*_DATASET`、`TRANS_*_DATASET` 的字面值。

- 對外 API：
  - Client（端點/授權/重試/代理）：`infrastructure/credolab_client.py`
  - Service（介面保持）：`services/credolab_api_service.py` → `get_credolab_insights(...)`

- 設定（active 環境區塊）：`config/config.yaml`
  - `gcp.project_id`、`gcs.bucket_name`、`gcs.blob_path`
  - `pubsub.credolab_topic`、`pubsub.anonymization_topic`
  - `bigquery.*` 資料集與表名鍵、`credolab_api.*` 端點與限制相關鍵

其餘層（批次協作、Recall、GCS/BQ 寫入、Logging、Pub/Sub 發布/解析）建議保持不變。
