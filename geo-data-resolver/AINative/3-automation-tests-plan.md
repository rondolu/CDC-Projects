# 3) Automation Tests Plan（自動化測試計畫）

目標：以最小改動導入可維護、可重現的測試，覆蓋關鍵行為與邊界條件。此處先提供策略與範例，實作可逐步落地。

## 3.1 測試層級
- Unit（單元）
  - 純函式/類別邏輯：如 `prepare_geo_raw_row`、座標驗證、批次分流、錯誤處理分支
  - 以 `pytest` + `monkeypatch`/`unittest.mock` 隔離外部服務
- Service Integration（服務整合）
  - `BatchProcessService` 與 `GoogleMapsAPIService`、`BigQueryService` 交互
  - 以 Stub/Mock BigQuery、GCS、Pub/Sub
- SQL/Spec 驗證（資料斷言）
  - 對 `failed_retry_list.sql`、`get_geo_query_data.sql`、`flatten_geo_data.sql` 的輸入/輸出規則進行斷言
  - 可先以「資料表接口的模擬」來驗證 SQL 規則（或在 CI 上以測試 Dataset 驗證）

## 3.2 覆蓋目標
- 來源查詢規則（去重、排除、日期範圍）
- 失敗重試視窗與成功排除條件
- 批次處理寫入 RAW 的「全情境成功才寫入」
- API 速率限制與重試策略（以時間/呼叫序列模擬）
- 扁平化映射與經緯度格式化

## 3.3 框架與工具
- 測試框架：`pytest`
- Mock：`unittest.mock` 或 `pytest-mock`
- 斷言：`pytest` 內建；JSON 結構可用 `jsonschema` 輔助
- 選配（規格驗證）：以 spec 工具或自製斷言表達「資料/格式規範」

## 3.4 測試案例建議

### U-01 prepare_geo_raw_row（utils/data_processor.py）
- Happy Path：輸入完整 `source_record` 與 `scenario_counts`，回傳欄位完整、`raw_data` 為 JSON 字串
- 邊界：任一欄位 None 時不報錯；時間欄位存在且格式正確

### U-02 GoogleMapsAPIService.get_area_insights
- 無效座標：Mock `validate_and_convert_coordinates -> False`，應回 `{count:"null"}` 且不觸發 client 呼叫
- API 成功：Mock client 回 200 + `{count: 3}`，應記錄 metrics 與 apilog，回傳 `{count:"3"}`
- API 例外：Mock client 拋錯，應拋 `GoogleMapsAPIError` 並記錄 apilog

### U-03 GoogleMapsAPIClient.get_places_aggregate
- 429/5xx：模擬前 N 次回應錯誤，後續成功；斷言有 retry 與延遲（可 mock `time.sleep`）
- Timeout：模擬 `requests.exceptions.Timeout`，達最大重試後拋 `GoogleMapsAPITimeoutError`
- 回應解析：回應含 `insights` 陣列，能正確取出 count

### S-01 BatchProcessService._process_batch_records
- 全成功：三情境皆成功 → 寫入 RAW；不寫入 failed
- 單情境失敗：某情境拋錯 → 不寫 RAW；寫入 failed；其它情境 count 設 "null"
- 無效座標：任一情境回 `{count:"null"}`（非例外）仍可寫 RAW，前提是其它情境無例外
- GCS/BigQuery 失敗：寫入 RAW 失敗時，將各筆寫入失敗記錄（`insert_failed_record`）

### S-02 後置流程 post_batch_processing
- 有 Failed Retry：Mock `_load_failed_retry_rows` 回多筆，分 chunk 呼叫 `_process_batch_records`
- Flatten 成功 → 觸發匿名化通知；失敗 → 不觸發

### SQL-01 failed_retry_list.sql 規則
- 準備測試資料（以測試 Dataset 或以假資料結構模擬）：
  - 同一 `series_number` 不同 `BQ_UPDATED_TIME` 與 `api_status`
  - 預期：只回最新一筆，且 `api_status` 非 `2xx/success`

### SQL-02 get_geo_query_data.sql 規則
- 多筆重複 `CUID + SERIAL_NUMBER`，含已存在 RAW/Failed Retry 的 `serial_number`
- 預期：去重且排除已處理者

### SQL-03 flatten_geo_data.sql 規則
- `raw_data` JSON 含 `scenario_counts`
- 預期：映射到 `contract_poi_*` 欄位，緯經度四捨五入到小數四位

## 3.5 測試夾具（fixtures）範例構想
- `fixtures/raw_source_rows.json`：來源樣本
- `fixtures/failed_retry_rows.json`：失敗重試樣本
- `fixtures/google_maps_responses.json`：API 回應樣本（成功、429、5xx、timeout）

## 3.6 執行策略
- 本機：純單元/服務測試以 Mock 為主
- CI：可分兩階段
  1) Unit/Service 測試（Mock 外部資源）
  2) 選配：針對測試 Dataset 的 SQL 驗證（受限權限與成本，可先跳過）

## 3.7 最小落地清單（可逐步導入）
- 新增 `tests/`（pytest）
- 先完成 U-01, U-02, S-01（投入小、覆蓋高）
- 後續補 S-02、SQL-01~03
