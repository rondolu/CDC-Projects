# Geo Data Resolver API 使用指南

## 目錄
1. [API 概述](#api-概述)
2. [端點詳解](#端點詳解)
3. [請求/回應格式](#請求回應格式)
4. [錯誤處理](#錯誤處理)
5. [使用範例](#使用範例)
6. [最佳實踐](#最佳實踐)

## API 概述

### 基本資訊
- **基礎 URL**: `http://localhost:8080` (本地開發) 或 GCP Cloud Run URL
- **內容類型**: `application/json`
- **認證**: 使用 Google Cloud 服務帳號（自動）

### 支援的 POI 情境
```python
CORPORATE_FINANCE = "corporate_finance"  # 企業金融相關
RESIDENTIAL = "residential"              # 住宅區域
COMMERCIAL = "commercial"                # 商業區域
FACILITY = "facility"                    # 公共設施
GOVERNMENT = "government"                # 政府機關
```

## 端點詳解

### 1. Daily Job 觸發

**端點**: `POST /`

**描述**: 觸發地理資料處理流程的 Daily Job。此端點會：
1. 從 BigQuery 載入尚未處理的地理資料
2. 分批呼叫 Google Maps API 進行 POI 查詢
3. 將成功結果寫入 `TMP_GEO_DATA` 表
4. 將失敗記錄寫入 `GEO_DATA_FAILED_RETRY_LIST` 表
5. 發佈 Pub/Sub 訊息觸發後續批次

**請求範例**:
```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{}'
```

**回應成功 (200)**:
```json
{
  "status": "success",
  "message": "Geo data processing flow initiated",
  "batch_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "flow_id": "geo-data-resolver_550e8400-e29b-41d4-a716-446655440000"
}
```

**回應成功 (204) - 來自 Pub/Sub**:
無內容，表示 Pub/Sub 訊息已成功處理

**回應失敗 (500)**:
```json
{
  "status": "error",
  "error_type": "internal_error",
  "message": "Internal server error occurred"
}
```

**查詢參數**: 無

**請求主體**: 可選
```json
{
  "source": "daily_job"  // 可選，用於日誌追蹤
}
```

---

### 2. 日期範圍批次處理

**端點**: `POST /get_data_range`

**描述**: 處理特定日期範圍的批次。此端點通常由前一個批次的 Pub/Sub 回調觸發，但也可手動調用。

**請求範例**:
```bash
curl -X POST http://localhost:8080/get_data_range \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-10-20",
    "end_date": "2025-10-21",
    "batch_number": "02"
  }'
```

**回應成功 (200)**:
```json
{
  "status": "success",
  "message": "Date range batch processing completed",
  "batch_number": "02",
  "records_processed": 1500,
  "records_succeeded": 1455,
  "records_failed": 45,
  "flow_id": "geo-data-resolver_550e8400-e29b-41d4-a716-446655440000"
}
```

**回應成功 (204) - 來自 Pub/Sub**:
無內容

**回應失敗 (400) - 日期範圍無效**:
```json
{
  "status": "error",
  "error_type": "validation_error",
  "message": "Invalid date range: start_date must be before end_date"
}
```

**回應失敗 (500)**:
```json
{
  "status": "error",
  "error_type": "internal_error",
  "message": "Internal server error occurred"
}
```

**請求主體**:
```json
{
  "start_date": "YYYY-MM-DD",  // 必須，開始日期 (包含)
  "end_date": "YYYY-MM-DD",    // 必須，結束日期 (包含)
  "batch_number": "02",         // 必須，批次編號
  "source": "batch_callback"    // 可選
}
```

---

## 請求/回應格式

### 標準回應結構

所有回應都遵循以下基本結構：

**成功回應**:
```json
{
  "status": "success",
  "message": "...",
  "data": {
    // 端點特定的回應資料
  }
}
```

**錯誤回應**:
```json
{
  "status": "error",
  "error_type": "error_category",
  "message": "error description",
  "details": {}  // 可選的額外詳情
}
```

### HTTP 狀態碼

| 狀態碼 | 意義 | 說明 |
|--------|------|------|
| 200 | OK | 請求成功，返回資料 |
| 204 | No Content | Pub/Sub 訊息成功處理 |
| 400 | Bad Request | 請求格式或參數無效 |
| 500 | Internal Server Error | 伺服器內部錯誤 |
| 502 | Bad Gateway | 外部 API 呼叫失敗 |

---

## 錯誤處理

### 常見錯誤類型

#### 1. DataValidationError (400)
```json
{
  "status": "error",
  "error_type": "data_validation_error",
  "message": "Data validation error: Invalid coordinates",
  "details": {
    "field": "latitude",
    "value": "invalid_value",
    "reason": "Latitude must be between -90 and 90"
  }
}
```

**可能原因**:
- 日期格式不符合 ISO 8601 標準
- 座標範圍不正確
- 必須字段缺失

#### 2. GoogleMapsAPIError (502)
```json
{
  "status": "error",
  "error_type": "google_maps_api_error",
  "message": "Google Maps API error: quota exceeded",
  "details": {
    "api_error_code": "QUOTA_EXCEEDED",
    "retry_after": 3600
  }
}
```

**可能原因**:
- API 配額已超限
- 座標無效
- 網路連線問題

#### 3. PubSubError (500)
```json
{
  "status": "error",
  "error_type": "pubsub_error",
  "message": "Failed to publish callback message to Pub/Sub",
  "details": {
    "topic": "projects/my-project/topics/geo-batch"
  }
}
```

**可能原因**:
- Pub/Sub 主題不存在或無權限
- 訊息格式無效

#### 4. 內部伺服器錯誤 (500)
```json
{
  "status": "error",
  "error_type": "internal_error",
  "message": "An unexpected error occurred",
  "details": {
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**調查方法**:
1. 使用 `correlation_id` 查詢 Cloud Logging
2. 檢查 BigQuery `FLOW_LOG` 表
3. 檢查 API_LOG 表中的最近呼叫

---

## 使用範例

### 範例 1: 基本 Daily Job 觸發

```python
import requests
import json

def trigger_daily_job():
    url = "http://localhost:8080/"
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, headers=headers, json={})
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ 流程已啟動")
        print(f"  Flow ID: {data['flow_id']}")
        print(f"  Batch UUID: {data['batch_uuid']}")
    else:
        print(f"✗ 錯誤 ({response.status_code}): {response.text}")

# 執行
trigger_daily_job()
```

### 範例 2: 手動觸發日期範圍處理

```python
import requests
from datetime import datetime, timedelta

def process_date_range(start_date, end_date):
    url = "http://localhost:8080/get_data_range"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "start_date": start_date,
        "end_date": end_date,
        "batch_number": "01",
        "source": "manual_trigger"
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ 批次處理完成")
        print(f"  已處理: {data['records_processed']}")
        print(f"  成功: {data['records_succeeded']}")
        print(f"  失敗: {data['records_failed']}")
    else:
        print(f"✗ 錯誤: {response.json()['message']}")

# 執行 - 處理昨天的資料
yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
today = datetime.now().strftime("%Y-%m-%d")
process_date_range(yesterday, today)
```

### 範例 3: 使用 cURL 進行批次測試

```bash
#!/bin/bash

# 設定環境
API_URL="http://localhost:8080"

# 1. 觸發 Daily Job
echo "1. 觸發 Daily Job..."
RESPONSE=$(curl -X POST "$API_URL/" \
  -H "Content-Type: application/json" \
  -d '{}' \
  -s)

echo "$RESPONSE" | jq '.'
FLOW_ID=$(echo "$RESPONSE" | jq -r '.flow_id')

# 2. 等待處理
echo -e "\n2. 等待 30 秒..."
sleep 30

# 3. 查詢日誌狀態
echo -e "\n3. 查詢流程日誌..."
bq query --nouse_legacy_sql "
  SELECT task_name, status, message 
  FROM \`project.LOG_DATASET.FLOW_LOG\`
  WHERE flow_id = '$FLOW_ID'
  ORDER BY timestamp DESC
  LIMIT 10
"

# 4. 查詢失敗記錄
echo -e "\n4. 查詢失敗記錄..."
bq query --nouse_legacy_sql "
  SELECT COUNT(*) as failed_count
  FROM \`project.RAW_EDEP_DATASET.GEO_DATA_FAILED_RETRY_LIST\`
  WHERE PARTITION_DATE >= CURRENT_DATE()
"
```

### 範例 4: 監控批次進度

```python
import time
from google.cloud import bigquery

def monitor_batch(flow_id, timeout_seconds=600):
    client = bigquery.Client()
    start_time = time.time()
    
    query = f"""
    SELECT 
      COUNT(*) as total_rows,
      COUNTIF(status = 'Success') as success_rows,
      COUNTIF(status = 'Failure') as failure_rows,
      MAX(timestamp) as last_update
    FROM `project.LOG_DATASET.FLOW_LOG`
    WHERE flow_id = '{flow_id}'
    """
    
    while time.time() - start_time < timeout_seconds:
        results = client.query(query).result()
        row = next(results)
        
        total = row['total_rows'] or 0
        success = row['success_rows'] or 0
        failure = row['failure_rows'] or 0
        
        print(f"\r進度: {success}/{total} ✓, {failure} ✗", end="")
        
        if total > 0 and (success + failure) == total:
            print("\n✓ 批次處理完成！")
            return True
        
        time.sleep(5)
    
    print("\n✗ 超時")
    return False

# 使用
monitor_batch("geo-data-resolver_550e8400-e29b-41d4-a716-446655440000")
```

---

## 最佳實踐

### 1. 日期範圍管理

```python
# ✓ 好的做法: 使用標準化的日期格式
start_date = "2025-10-20"  # YYYY-MM-DD
end_date = "2025-10-21"

# ✗ 不好的做法: 時間戳記或其他格式
start_date = "20251020"
start_date = "2025-10-20 00:00:00"
```

### 2. 錯誤重試策略

```python
import time

def call_api_with_retry(max_retries=3, backoff_factor=2):
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, ...)
            if response.status_code == 200:
                return response.json()
            elif response.status_code in [502, 503]:
                # API 暫時不可用，進行重試
                wait_time = backoff_factor ** attempt
                print(f"重試 {attempt + 1}/{max_retries}，等待 {wait_time}s")
                time.sleep(wait_time)
            else:
                # 客戶端錯誤，不重試
                raise Exception(f"客戶端錯誤: {response.status_code}")
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"嘗試 {attempt + 1} 失敗: {e}")

# 使用
data = call_api_with_retry()
```

### 3. 日誌和監控

```python
import logging
from datetime import datetime

# 設定結構化日誌
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 記錄重要事件
def log_api_call(flow_id, records_processed, success_count):
    logger.info(
        f"Batch completed - flow_id={flow_id}, "
        f"records_processed={records_processed}, "
        f"success_count={success_count}, "
        f"success_rate={success_count/records_processed*100:.1f}%"
    )

# 監控效能
start_time = datetime.now()
# ... 執行操作 ...
duration = (datetime.now() - start_time).total_seconds()
logger.info(f"Operation completed in {duration:.2f}s")
```

### 4. Pub/Sub 訊息來源檢測

```python
def is_pubsub_request(request_data):
    """檢測是否為 Pub/Sub Push 訊息"""
    # Pub/Sub Push 包含特定的結構
    return "message" in request_data and "subscription" in request_data

def handle_request(data):
    if is_pubsub_request(data):
        # 這是來自 Pub/Sub 的訊息
        message_data = data["message"]["data"]
        # 解析 base64 編碼的訊息
        import base64
        payload = json.loads(base64.b64decode(message_data))
        return process_date_range(
            payload["start_date"],
            payload["end_date"],
            payload.get("batch_number", "01")
        )
    else:
        # 這是直接的 HTTP 請求
        return trigger_daily_job()
```

### 5. 配額管理

```python
from datetime import datetime, timezone

def check_api_quota():
    """檢查當前 API 使用率"""
    client = bigquery.Client()
    
    # 查詢當分鐘的 API 呼叫次數
    now = datetime.now(timezone.utc)
    current_minute = now.replace(second=0, microsecond=0)
    
    query = f"""
    SELECT COUNT(*) as calls_this_minute
    FROM `project.LOG_DATASET.API_LOG`
    WHERE api_name = 'geo-data-resolver'
      AND start_time >= TIMESTAMP('{current_minute.isoformat()}')
    """
    
    result = client.query(query).result()
    row = next(result)
    calls = row['calls_this_minute']
    
    # 1200 QPM = 20 QPS
    max_calls_per_minute = 1200
    usage_percent = (calls / max_calls_per_minute) * 100
    
    print(f"API 使用率: {calls}/{max_calls_per_minute} ({usage_percent:.1f}%)")
    
    if usage_percent > 80:
        print("⚠ 警告: 接近配額限制，考慮減速")
    
    return calls, usage_percent
```

### 6. 災難恢復

```python
def recover_failed_batch(flow_id):
    """重新處理失敗的記錄"""
    client = bigquery.Client()
    
    # 1. 查詢失敗記錄
    query = f"""
    SELECT DISTINCT start_date, end_date
    FROM `project.RAW_EDEP_DATASET.GEO_DATA_FAILED_RETRY_LIST`
    WHERE flow_id = '{flow_id}'
    """
    
    for row in client.query(query).result():
        # 2. 重新觸發日期範圍處理
        print(f"重新處理: {row['start_date']} 到 {row['end_date']}")
        response = requests.post(
            f"{API_URL}/get_data_range",
            json={
                "start_date": row['start_date'].strftime("%Y-%m-%d"),
                "end_date": row['end_date'].strftime("%Y-%m-%d"),
                "batch_number": "recovery",
                "source": "disaster_recovery"
            }
        )
        print(f"結果: {response.status_code}")
```

---

## 故障排除

### 問題: 批次處理卡住

**症狀**: 已發送請求但無回應

**排查**:
1. 檢查 Cloud Run 實例狀態
2. 查詢 Cloud Logging 中的最近日誌
3. 檢查 Pub/Sub 主題配置

### 問題: API 調用失敗 (502)

**症狀**: 收到 Google Maps API 錯誤

**排查**:
1. 驗證 API 金鑰是否有效
2. 檢查座標是否有效 (-90 ≤ lat ≤ 90, -180 ≤ lon ≤ 180)
3. 檢查 API 配額使用情況

### 問題: 日期範圍處理無法開始

**症狀**: 手動呼叫日期範圍端點但無反應

**排查**:
1. 驗證日期格式 (YYYY-MM-DD)
2. 確認 start_date < end_date
3. 檢查該日期範圍是否有資料

---

**最後更新**: 2025-10-27
