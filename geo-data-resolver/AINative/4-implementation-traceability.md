# 4) Implementation Traceability（實作可追蹤性）

本文件建立需求 ↔ 規格 ↔ 程式/SQL 的映射，便於影響分析與回歸。

## 4.1 對應矩陣（摘要）

- BR-01 Daily/Range 模式
  - Specs：Spec-02, Spec-05
  - 實作：
    - `services/dataflow_service.py` → `process()`, `handle_daily_request()`, `handle_date_range_request()`, `process_recall_batch()`
    - `blueprints/geo_routes.py` → `POST /`, `POST /get_data_range`

- BR-02 來源資料去重與排除
  - Specs：Spec-01, Spec-02
  - 實作：
    - `sql/get_geo_query_data.sql`、`sql/get_geo_query_data_range.sql`

- BR-03 API 呼叫與 RAW 寫入條件
  - Specs：Spec-04, Spec-07~09
  - 實作：
    - `services/google_maps_api_service.py` → `get_area_insights()`
    - `infrastructure/google_maps_client.py` → `get_places_aggregate()`、`_rate_limit()`
    - `application/batch_process_service.py` → `_process_batch_records()`、`_insert_raw_rows_to_bq()`
    - `utils/data_processor.py` → `prepare_geo_raw_row()`

- BR-04 批次大小與速率限制
  - Specs：Spec-05, Spec-08
  - 實作：
    - `modules/config.py`（`google_maps_batch_size`, `google_maps_qpm_limit` 等）
    - `infrastructure/google_maps_client.py`（`_rate_limit` 與重試）

- BR-05 失敗重試（視窗與成功排除）
  - Specs：Spec-03, Spec-06
  - 實作：
    - `sql/failed_retry_list.sql`
    - `application/batch_process_service.py` → `_load_failed_retry_rows()`, `post_batch_processing()`
    - `application/bigquery_service.py` → `insert_failed_record()`, `update_failed_retry_status()`

- BR-06 扁平化與匿名化
  - Specs：Spec-06, Spec-10
  - 實作：
    - `sql/flatten_geo_data.sql`
    - `application/batch_process_service.py` → `post_batch_processing()`（flatten 成功後通知）

- BR-07 Logging/Metrics
  - Specs：各處含有（Spec-04/07/08 等）
  - 實作：
    - `utils/infra_logging.py`, `utils/metrics.py`, `utils/request_context.py`

## 4.2 關鍵契約（Contract）摘錄

- API 輸入：`latitude`, `longitude`, `scenario`（`POIScenarioEnum`）
- API 輸出：`{"count": string|"null", "response_time_ms": number}`；例外時拋 `GoogleMapsAPIError`
- RAW 欄位：見 `docs/BQ_TABLE_SCHEMAS.md`（`RAW_EDEP_DATASET.GEO_DATA`）
- 失敗清單：`api_status` 為字串，2xx 或 `success` 視為成功
- flatten：從 `raw_data.scenario_counts.*` 映射至 `TMP_GEO_DATA` 的各 POI 欄位

## 4.3 Edge Cases（與對應實作）

- 無效座標：`get_area_insights()` 直接回 `{count:"null"}`，不中斷（`services/google_maps_api_service.py`）
- 單情境失敗：記錄 `failed_retry` 並不寫 RAW（`_process_batch_records`）
- RAW 插入失敗：逐筆改寫入 `failed_retry`（`_insert_raw_rows_to_bq`）
- 視窗與去重：`failed_retry_list.sql` 使用 `ROW_NUMBER()` 取最新 + 排除 2xx/success

## 4.4 待補強/注意事項

- 若未來需要「部分成功也寫 RAW」，需調整 `_process_batch_records` 的條件與 downstream 映射。
- `flatten_geo_data.sql` 目前多欄位為 NULL 佔位，後續若加入 geocoding/address 分解，需更新映射規格與驗收。
- 匿名化通知 payload 目前固定，與下游契約需版本化管理。
