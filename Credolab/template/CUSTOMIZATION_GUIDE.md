# 客製範圍與實作指引（只改 SQL 與發查端點）

本範本目標：其他開發者可拿公版程式，僅針對 SQL 與外部 API 發查端點實作業務差異，其他流程照舊。

可改動重點：
1) SQL 取數與轉換（`sql/`）
   - 載入原始資料：`get_vmb_data.sql`（daily 模式）與 `get_vmb_data_range.sql`（range 模式）。
   - 最終轉換：`flatten_data_android.sql`、`flatten_data_ios.sql`（最後一批或單批完成後執行）。
   - 若資料集或表名不同，請直接修改 SQL 檔案內的 dataset/table 名稱（目前程式未對 SQL 內的 dataset 名做動態替換）。

2) 外部 API 發查端點
   - 端點 client：`infrastructure/credolab_client.py`（`CredolabAPIClient.get_insights`）。
   - service 包裝：`services/credolab_api_service.py`（`get_credolab_insights`）。
   - 若要改成查詢不同對外 API：
     - 在 client 中調整 base URL、授權、query 參數格式與錯誤處理。
     - 在 service 中維持 `get_credolab_insights(reference_number, api_codes=None)` 介面或提供等價方法，讓核心批次邏輯可沿用。

務必保留的資料結構要求：
- `_load_vmb_data()` 回傳的每筆紀錄至少需提供以下欄位（現有程式實際使用）：
  - `reference_id`（或 `referenceNumber`，兩者其一會被讀取為查詢鍵）
  - `cuid`
  - `device_os`（`android` 或 `ios`，用於分流寫入表）
  - `serial_number`（於 `prepare_raw_data_for_bq` 中對應 `series_number`）
- 外部 API 回傳資料在 `prepare_raw_data_for_bq(original_record, api_response)` 中會被序列化為 `raw_data` 欄位後寫入 BQ RAW 表。

回呼（Recall）與批次切分：
- 不需改動。由 `BatchProcessService` 與 `DataFlowService` 內建處理：
  - 首批：`_initiate_batch_processing`
  - 後續批：透過 `PubSubService.publish_daily_recall_message` 或 `publish_range_recall_message` 觸發對應路由，由 `DataFlowService` 解析後進入 `_orchestrate_batch_processing` 處理。

錯誤處理與重試清單：
- 呼叫外部 API 失敗時，`_process_batch_records()` 會呼叫 `BigQueryService.insert_failed_record` 寫入 `CREDOLAB_FAILED_RETRY_LIST`。可依需要調整該表 schema 與對應程式（`modules/config.py` 提供表名組裝）。

---

## 你要改什麼（指令式清單）

- SQL：
  - 編輯 `sql/get_vmb_data.sql`、`sql/get_vmb_data_range.sql`、`sql/flatten_data_android.sql`、`sql/flatten_data_ios.sql`
  - 直接替換 SQL 內的資料集/表名字串為你的環境；保留 `@start_date`、`@end_date`、`@partition_date` 參數位。
  - 載入 SQL 確保回傳欄位：`cuid`、`reference_id`、`device_os`、`serial_number`。

- API 端點（client/service）：
  - `infrastructure/credolab_client.py`：修改 `base_url`、路徑、授權、重試與代理設定；保留或等價實作 `get_insights(...)`。
  - `services/credolab_api_service.py`：盡量保持 `get_credolab_insights(reference_number, api_codes=None)` 介面。
  - `utils/data_processor.py:prepare_raw_data_for_bq`：如外部 API 回傳資料結構變動，確保此處仍可序列化為 `raw_data`。

- 設定：
  - 在 `config/config.yaml` 的 active 專案段落更新：`gcp.project_id`、`gcs.bucket_name`、`pubsub.*`、`bigquery.*`、`credolab_api.*`
