# 2) Specs & Acceptance Tests（規格與驗收測試）

本文件將業務需求轉為可驗證的規格與情境（Given/When/Then）。檔名以 repo 現況為準，重點標註映射。

---
## 2.1 來源資料查詢（Daily）
- 對應：`sql/get_geo_query_data.sql`

Spec-01（去重與排除）
- Given：
  - `CUSTOMER`, `APPLICATION`, `APPLY_INFO` 有重複 `CUID + SERIAL_NUMBER` 的多筆不同分區資料
  - `RAW_EDEP_DATASET.GEO_DATA` 已存在其中部分 `serial_number`
  - `GEO_DATA_FAILED_RETRY_LIST` 已存在其中部分 `series_number`
- When：執行 `get_geo_query_data.sql`
- Then：
  - 僅保留每個 `CUID + SERIAL_NUMBER` 的最新一筆（依 `ap.partition_date`）
  - 排除已在 RAW 與 Failed Retry 的 `serial/series_number`
  - 只回傳 `CUID` 不為空的記錄

驗收斷言（示例）：
- 任一回傳列，其 `serial_number` 不存在於 `RAW_EDEP_DATASET.GEO_DATA.serial_number`
- 任一回傳列，其 `serial_number` 不存在於 `GEO_DATA_FAILED_RETRY_LIST.series_number`
- 對每個 `CUID + SERIAL_NUMBER` 僅有 1 列

---
## 2.2 來源資料查詢（Range）
- 對應：`sql/get_geo_query_data_range.sql`

Spec-02（日期區間 + 去重）
- Given：`APPLICATION.partition_date` 在 `[start_date, end_date]`
- When：執行 `get_geo_query_data_range.sql` 並帶參數 `@start_date`, `@end_date`
- Then：
  - 回傳 `CUID` 不為空
  - 以 `CUID + SERIAL_NUMBER` 保留最新一筆（依 `ap.partition_date`）

驗收斷言（示例）：
- 回傳所有列之 `ap.partition_date` 皆在指定區間內
- 對每個 `CUID + SERIAL_NUMBER` 僅有 1 列

---
## 2.3 失敗重試清單（Failed Retry）
- 對應：`sql/failed_retry_list.sql`

Spec-03（視窗、去重、排除成功）
- Given：`GEO_DATA_FAILED_RETRY_LIST` 有同一 `series_number` 的多筆記錄、不同 `BQ_UPDATED_TIME` 與 `api_status`
- When：執行 `failed_retry_list.sql`
- Then：
  - 僅取 D-14 ~ D-1 的分區（避免當日）
  - 以 `series_number` 去重，保留 `BQ_UPDATED_TIME` 最新一筆
  - 僅回傳 `api_status` 非成功（非 `2xx` 且不等於 `success`）

驗收斷言（示例）：
- 結果中不存在 `api_status` 以 `"2"` 開頭或等於 `"success"` 的列
- 對每個 `series_number` 僅有 1 列，且其 `BQ_UPDATED_TIME` 為該 series 最新

---
## 2.4 批次處理規則（Application 層）
- 對應：`application/batch_process_service.py`

Spec-04（單筆資料流程）
- Given：一筆來源記錄（含座標）
- When：依序呼叫 `get_area_insights()` 取得三種情境的 `count`
- Then：
  - 若座標無效：不呼叫 API，該情境 `count = "null"`；不中斷整筆處理
  - 若任一情境拋出例外：
    - 記錄失敗（`insert_failed_record`）
    - 該情境 `count = "null"`
    - 整筆不得寫入 RAW
  - 僅當全部情境成功（無例外）才將彙整後結果寫入 `RAW_EDEP_DATASET.GEO_DATA`

Spec-05（批次切分與回呼）
- Given：批次大小 `batch_size = N`
- When：處理資料長度為 `K`
- Then：
  - 若 `K < N`，標記 `is_last_batch = True`
  - 若非最後一批且設定了回呼，發布下一批訊息（Pub/Sub）
  - 若為最後一批，呼叫 `post_batch_processing()`

Spec-06（後置流程）
- When：`post_batch_processing()`
- Then：
  - 載入 Failed Retry 視窗資料並依批次處理
  - 執行 `flatten_geo_data.sql`（以 `@partition_date`）
  - 僅在 flatten 成功後發布匿名化通知

---
## 2.5 Google Maps API 規格
- 對應：`services/google_maps_api_service.py`, `infrastructure/google_maps_client.py`

Spec-07（座標驗證與回傳）
- Given：輸入座標
- When：`validate_and_convert_coordinates()` 判為無效
- Then：
  - 跳過 API 呼叫，回傳 `{ count: "null", response_time_ms: 0 }`

Spec-08（速率限制與重試）
- Given：QPM 限制與重試設定
- When：連續多筆呼叫
- Then：
  - `_rate_limit()` 確保請求間隔
  - 429/5xx/Timeout 採用指數退避重試

Spec-09（回應解析）
- Given：Google API 回應（可能為 `insights` 陣列或 `count` 欄位）
- When：解析回應
- Then：
  - 取得整體 `count` 數字並轉為字串存放

---
## 2.6 扁平化（TRANS）
- 對應：`sql/flatten_geo_data.sql`

Spec-10（映射與寫入）
- Given：RAW 表 `GEO_DATA` 的 `raw_data` JSON 內含 `scenario_counts`
- When：執行 `flatten_geo_data.sql`
- Then：
  - 將 `scenario_counts` 對應映射到 `contract_poi_corporate_finance / commercial_facility / residential`
  - 經緯度以 4 位小數字串格式化
  - 僅處理尚未在 `TMP_GEO_DATA` 的 `serial_number`

---
## 2.7 範例（以規格斷言口語化）
- 失敗重試輸出：
  - 對任一列：`api_status NOT LIKE '2%' AND api_status != 'success'`
  - 每個 `series_number` 僅有 1 筆且為最新 `BQ_UPDATED_TIME`
- RAW 寫入前置條件：
  - `had_error_for_record == False`
  - `scenario_counts` 皆為非例外回傳（可含 "null" 值）
