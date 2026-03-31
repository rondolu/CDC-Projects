# Credolab 資料處理流程摘要

## 完整資料流程說明
```
HTTP JSON → 參數解析 → SQL 載入 VMB 資料 → 逐筆：呼叫 Credolab API
    →（成功）立即上傳原始記錄至 GCS + 立即寫入 BigQuery（依 device_os 分表）
    →（失敗）寫入 Failed Retry 表（不自動重試）

批次結束：若仍有下一批 → 發布 recall Pub/Sub 訊息
最後一批：執行 flatten SQL（android/ios）→ 發布 anonymization 訊息 → 回傳完成摘要
```

## 日誌記錄機制

系統實現了雙層日誌記錄機制，完全符合客戶端提供的 BigQuery table schema：

- **流程日誌**: 僅記錄完成/錯誤狀態（不記錄開始；由裝飾器控制）
- **API 日誌**: 記錄每筆 API 呼叫的完整資訊，包含重試次數
- **雙重記錄**: 同時寫入 BigQuery 和 Cloud Logging
- **錯誤追蹤**: 包含完整錯誤堆疊和上下文

> 詳細的日誌系統使用方式請參考 [`LOGGING_GUIDE.md`](./LOGGING_GUIDE.md)

### 流程日誌（LOG_DATASET.FLOW_LOG）

記錄所有關鍵資料流的執行狀態：

| 欄位 | 類型 | 說明 |
|------|------|------|
| DATETIME | STRING | 記錄時間 |
| FLOW_ID | STRING | 流程識別碼 |
| FLOW_NAME | STRING | 流程名稱 |
| TASK_CODE | STRING | 任務代碼 |
| TASK_NAME | STRING | 任務名稱 |
| STATUS | STRING | Success/Error |
| MESSAGE | STRING | 詳細訊息 |
| SEVERITY | STRING | 嚴重程度 |

### API 日誌（API_DATASET.API_LOG）

記錄每筆 API 呼叫的詳細資訊：

| 欄位 | 類型 | 說明 |
|------|------|------|
| UUID_Request | STRING | 請求級 UUID（`Logging.log_uuid`；非 reference_id） |
| API_Type | STRING | CREDOLAB |
| API_Name | STRING | API 名稱和參數 |
| Start_Time | DATETIME | 開始時間 |
| End_Time | DATETIME | 結束時間 |
| Status_Code | STRING | HTTP 狀態碼 |
| Status_Detail | STRING | 狀態詳細資訊 |
| Retry | INTEGER | 重試次數 |

## 系統架構與實作

### 1. HTTP 端點（`blueprints/credolab_routes.py`）

- `POST /`：啟動 daily 模式（由系統自動決定 partition_date）；亦作為 daily_recall 回調端點
- `POST /get_data_range`：啟動 range 模式（需提供 start/end）；亦作為 range_recall 回調端點
- 兩端點皆能接收 Pub/Sub push（由 attributes 篩選）

### 2. 參數解析與驗證

- 日期格式驗證 (YYYY-MM-DD)
- 資料範圍驗證

### 3. SQL 載入與 BigQuery 查詢 VMB

#### SQL 檔案（位於 `sql/`）

- `get_vmb_data.sql` - 日常批次處理
- `get_vmb_data_range.sql` - 指定日期範圍處理
- `failed_retry_list.sql` - 失敗重試列表查詢

（查詢邏輯請以實際 SQL 檔為準，下列僅示意）

```sql
-- 結合 VMB、HES Customer 和 Application 資料
SELECT
    m.cuid         AS cuid,
    m.reference_id AS referenceNumber,
    m.device_os    AS device_os,
    m.created_timestamp AS created_at,
    ap.SERIAL_NUMBER AS serial_number
FROM RAW_VMB_DATASET.CREDOLAB_DATA m
LEFT JOIN (
    SELECT *
    FROM `RAW_HES_DATASET.CUSTOMER`
    QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY PARTITION_DATE DESC) = 1
) c ON (c.cuid = m.cuid)
LEFT JOIN (
    SELECT *
    FROM `TRANS_HES_DATASET.APPLICATION`
    QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id, SERIAL_NUMBER ORDER BY PARTITION_DATE DESC) = 1
) ap ON (c.id = ap.customer_id AND DATE(ap.CREATED_AT) = DATE(m.created_timestamp))
```

### 4. VMB Record 處理流程

#### 主要服務：`application/batch_process_service.py`（`BatchProcessService`）

- 批次處理：第一批由 HTTP 觸發，其餘批次透過 Pub/Sub recall
- 逐筆即時存儲：API 成功後立即上傳 GCS 並寫入 BigQuery（不等待整批）
- 錯誤記錄：失敗寫入 Failed Retry 表（不自動重試）
- 回調設計：整批完成後才發布下一批（無跨批並行）

#### 處理步驟（現況）

1. 查詢 VMB 資料（daily：get_vmb_data.sql；range：get_vmb_data_range.sql）
2. 計算批次數量（batch_size 來源於 config）
3. 僅處理第一批（或指定 recall 批次）
4. 逐筆：API →（成功）GCS → BQ；失敗→寫入 FAILED_RETRY_LIST
5. 若還有下一批：發布 Pub/Sub recall 訊息（message_type=daily_recall|range_recall）
6. 若為最後一批：執行 `flatten_data_android.sql` / `flatten_data_ios.sql` → 發布 anonymization
7. 回傳第一批或最終批次回應（不包含聚合重試統計欄位）

### 5. Credolab API 整合

#### API 客戶端：`infrastructure/credolab_client.py`（`CredolabAPIClient`）

- 認證：Bearer Token
- 速率限制與重試：由客戶端負責（例如 429/5xx 指數退避）
- 超時：由客戶端設定
- 主要方法：`get_insights(reference_id, api_codes)`

#### 支援的 API 代碼

```yaml
api_codes:
  - "appsInfo"
  - "deviceInfo" 
  - "ipInfo"
  - "lastApps"
  - "permissions"
  - "riskyApps"
  - "velocity"
  - "fraudAlerts"
  - "typing"
  - "uiInteractions"
  - "fingerGestures"
  - "touchActions"
  - "anomaly"
  - "expertScore"
```

### 6. GCS 原始資料上傳

#### 檔案路徑格式（現況：扁平，日期/OS/Reference ID 放入檔名中）

```text
{bucket}/{blob_path}/{YYYY-MM-DD}_{device_os}_{reference_id}.json
```

#### 範例（bucket=rawdata_api, blob_path=EDEP/CREDOLAB）

```text
rawdata_api/EDEP/CREDOLAB/2025-01-15_android_REF123456.json
rawdata_api/EDEP/CREDOLAB/2025-01-15_ios_REF789012.json
```

#### 檔案內容

```json
{
    "uuid": "生成的 UUID",
    "cuid": "客戶 ID",
    "reference_id": "提供給credolab api查詢分析結果的參考號碼",
    "series_number": "HES申貸編號",
    "device_os": "裝置作業系統",
    "raw_data": "Credolab API 回應 JSON 格式字串",
    "BQ_UPDATED_TIME": "更新時間 (UTC ISO 格式)",
    "PARTITION_DATE": "分區日期 (YYYY-MM-DD)"
}
```

### 7. BigQuery 資料儲存

#### 目標表格（實際表名以 `config/config.yaml` 為準）

- Android：`config.bq_credolab_table_android`
- iOS：`config.bq_credolab_table_ios`
- 失敗重試：`config.bq_credolab_failed_retry_table`

#### 資料結構 (由 `data_processor.py` 處理)

```python
{
    "uuid": "生成的 UUID",
    "cuid": "客戶 ID",
    "reference_id": "提供給credolab api查詢分析結果的參考號碼",
    "series_number": "HES申貸編號",
    "device_os": "裝置作業系統",
    "raw_data": "Credolab API 回應 JSON 格式字串",
    "BQ_UPDATED_TIME": "更新時間 (UTC ISO 格式)",
    "PARTITION_DATE": "分區日期 (YYYY-MM-DD)"
}
```

### 8. 失敗記錄（暫無自動重試流程）

#### 失敗記錄結構

```python
{
    "uuid": "生成的 UUID",
    "cuid": "客戶 ID",
    "reference_id": "提供給credolab api查詢分析結果的參考號碼",
    "series_number": "HES申貸編號",
    "device_os": "裝置作業系統",
    "api_payload_message": "Credolab API 回應 JSON 格式字串",
    "api_status": "HTTP 狀態碼或錯誤代碼",
    "BQ_UPDATED_TIME": "更新時間 (UTC ISO 格式)",
    "PARTITION_DATE": "分區日期 (YYYY-MM-DD)"
}
```

目前僅「記錄」失敗事件；系統不會在流程尾自動重新呼叫 API。若需補處理，建議以排程掃描 Failed Retry 表。

### 9. 回應格式（示意）

Daily / Range 第 1 批：

```json
{
    "status": "success",
    "message": "Daily Credolab flow initiated with recall mechanism",
    "processing_period": {"mode": "daily", "device_type": "all"},
    "first_batch_result": {
        "status": "processing",
        "total_records": 123,
        "total_batches": 3,
        "batch_result": {"success_count": 48, "error_count": 2, "processed_references": ["R1", "R2"], "message": "..."}
    }
}
```

最後一批（完成）：

```json
{
    "status": "completed",
    "message": "All 3 batches completed",
    "final_batch_result": {
        "total_count": 123,
        "success_count": 119,
        "error_count": 4,
        "processed_references": ["R1", "R2", "..."]
    },
    "anonymization_message_id": "1234567890"
}
```

## 配置管理

### 主要配置檔案: `config/config.yaml`

- **GCP 專案設定**
- **BigQuery 資料集和表格配置**
- **Credolab API 設定**
- **GCS 儲存桶配置**
- **日誌和監控設定**

### 環境變數支援

- 環境變數優先於 YAML 檔案
- 支援 GCP Secret Manager 整合
- 點分隔鍵轉換為大寫底線格式

## 錯誤處理與重試機制

### 1. API 錯誤處理

- **429 (Rate Limit)**: 自動等待重試，記錄重試次數
- **5xx 錯誤**: 指數退避重試，最多重試配置次數
- **4xx 錯誤**: 記錄但不重試

### 2. 失敗記錄處理

- 失敗記錄存入 `CREDOLAB_FAILED_RETRY_LIST`
- 不自動重試；保留後續人工或排程機制

### 3. 日誌記錄整合

- **流程日誌**: 記錄每個關鍵流程的開始、結束和錯誤狀態
- **API 日誌**: 記錄每筆 API 呼叫的完整資訊，包含重試次數
- **統一格式**: 所有日誌都使用新的 schema 格式
- **雙重記錄**: 同時寫入 BigQuery 和 Cloud Logging
- **錯誤追蹤**: 包含完整錯誤堆疊和上下文

## 監控與維護

### 關鍵指標

- 處理成功率
- API 回應時間
- 錯誤率和錯誤類型
- 資料處理延遲
- 重試成功率
- QPM 使用率 (50/分鐘限制)

### 告警設定

- API 回應時間異常
- BigQuery 寫入錯誤
- GCS 上傳失敗
- 重試機制異常
- QPM 限制接近


## 效能考量

### 批次處理要點

- 批次大小：可由 `config` 調整（預設 50）
- 並行策略：現行不做跨批並行，避免競態

### API 速率限制

- **QPM 控制**: 防止 API 限制 (50 次/分鐘)
- **重試策略**: 智慧型退避機制
- **連線池**: HTTP 連線重用

## 提要（與早期構想差異）

- 僅使用 insights 查詢（無上傳資料 API 流程）
- 不做自動重試（僅落表記錄）
- 回應不含 retry_processing 區塊
- 逐筆：API → GCS → BigQuery；最後一批才執行 flatten + anonymization
