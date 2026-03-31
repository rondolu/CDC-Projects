# Geo Data Resolver 架構設計文檔

## 1. 系統概述

### 目的
Google Maps Geo Data Resolver 是一個地理資料解析服務，專門用於：
- 批量查詢 Google Maps POI (Point of Interest) 資料
- 處理地理位置的地址解析和編碼
- 提供完整的非同步批次處理能力
- 記錄詳細的審計日誌和效能指標

### 技術棧
- **後端**: Python 3.9 + Flask + Gunicorn
- **雲端**: Google Cloud Platform (GCP)
- **API**: Google Maps Places Aggregate API
- **資料驗證**: Pydantic v2.0+
- **容器化**: Docker

## 2. 分層架構設計

```
┌─────────────────────────────────────────────────────────────────┐
│                        HTTP/Pub/Sub 層                           │
├─────────────────────────────────────────────────────────────────┤
│                        路由層 (Routes)                            │
│                    blueprints/geo_routes.py                      │
├─────────────────────────────────────────────────────────────────┤
│                      服務層 (Services)                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ dataflow_service.py    google_maps_api_service.py        │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                  應用層 (Application)                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ batch_process_service.py    bigquery_service.py          │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│              基礎設施層 (Infrastructure)                          │
│              infrastructure/google_maps_client.py                │
├─────────────────────────────────────────────────────────────────┤
│                       模型層 (Models)                             │
│              models/google_maps_models.py                        │
├─────────────────────────────────────────────────────────────────┤
│                      工具層 (Utilities)                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ infra_logging.py  error_handling.py  gcs_services.py    │   │
│  │ pubsub_services.py  metrics.py  data_processor.py       │   │
│  │ request_context.py  secret_manager_service.py           │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                    配置層 (Configuration)                         │
│                    modules/config.py                             │
├─────────────────────────────────────────────────────────────────┤
│              外部服務 (External Services)                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Google Cloud: BigQuery, GCS, Pub/Sub, Secret Manager    │   │
│  │ Google Maps API                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 主要組件詳解

### 3.1 路由層 (blueprints/geo_routes.py)
**職責**: HTTP 請求路由和 Pub/Sub 訊息適配

**關鍵端點**:
- `POST /` - Daily Job 觸發點
- `POST /get_data_range` - 日期範圍批次處理

**特性**:
- 使用 `@Logging.logtobq()` 裝飾器自動記錄
- 使用 `@handle_route_exceptions` 統一異常處理
- 支持 Pub/Sub Push 訊息，成功時回傳 204

### 3.2 服務層 (services/)

#### 3.2.1 DataflowService (dataflow_service.py)
**職責**: 資料流程編排和批次策略

**主要方法**:
- `handle_daily_request()`: 處理 Daily Job 請求
  - 首次批次查詢不帶日期
  - 發送 Pub/Sub 回調消息至後續批次
  
- `handle_date_range_request()`: 處理日期範圍批次
  - 從 Pub/Sub 回調接收日期
  - 支持批次連鎖處理

**批次回調機制**:
```
Daily Job (start_date=None) 
    ↓ [處理第一批] 
    ↓ [發送 Pub/Sub] 
Batch 2 (start_date, end_date) 
    ↓ [處理第二批] 
    ↓ [發送 Pub/Sub] 
Batch N (start_date, end_date)
```

#### 3.2.2 GoogleMapsAPIService (google_maps_api_service.py)
**職責**: Google Maps API 高層介面

**主要方法**:
- `get_area_insights()`: 取得特定區域 POI 數據
  - 坐標驗證
  - API 呼叫管理
  - 效能指標追蹤

**特性**:
- 自動坐標驗證，無效時回傳 null
- 記錄每次 API 呼叫的詳細資訊
- 整合效能指標收集

### 3.3 應用層 (application/)

#### 3.3.1 BatchProcessService (batch_process_service.py)
**職責**: 核心批次處理邏輯

**主要類別**:
- `BatchContext`: 批次上下文
  ```python
  @dataclass
  class BatchContext:
      batch_number: str          # 批次編號
      start_date: Optional[str]  # 開始日期
      end_date: Optional[str]    # 結束日期
      batch_uuid: str            # 批次唯一識別碼
      flow_id: str               # 流程 ID (用於日誌追蹤)
      is_last_batch: bool        # 是否最後一批
  ```

- `ProcessingResult`: 處理結果
  ```python
  @dataclass
  class ProcessingResult:
      success_count: int
      error_count: int
      skipped_count: int
      processed_references: List[str]
      errors: List[Dict[str, Any]]
  ```

- `BatchProcessService`: 批次處理主類別
  - 支援通用編排
  - 資料載入與分頁
  - 單筆和批次記錄處理
  - Pub/Sub 回調

#### 3.3.2 BigQueryService (bigquery_service.py)
**職責**: BigQuery 資料管理

**主要功能**:
- 檢查/自動建立資料集和資料表
- 查詢和插入操作
- 失敗清單記錄
- 自動重試機制

### 3.4 基礎設施層 (infrastructure/)

#### GoogleMapsAPIClient (google_maps_client.py)
**職責**: Google Maps API 低層客戶端

**主要特性**:
- HTTP 會話管理和連接池
- 指數退避重試策略
- QPM 速率限制實現
- 配置式 POI 類型對映

**速率限制實現**:
```python
def _rate_limit(self) -> None:
    """實施 QPM (Queries Per Minute) 限制"""
    # 計算應該等待的時間
    # 目標: 1200 QPM = 20 QPS
```

### 3.5 工具層 (utils/)

#### 3.5.1 infra_logging.py
**日誌系統架構**:

- **Flow Log**: 記錄任務流程
  ```python
  log.flowlog(
      task_name="process_batch",
      task_code="01",
      message="Batch processing started",
      status="Success",
      severity="Info"
  )
  ```

- **API Log**: 記錄 API 呼叫
  ```python
  log.apilog(
      uuid_request=uuid,
      api_type="geo-data-resolver-api",
      api_name="geo-data-resolver",
      start_time=start,
      end_time=end,
      status_code="200",
      retry=0
  )
  ```

- **裝飾器支援**:
  - `@Logging.logtobq()`: 自動記錄方法執行結果到 FLOW_LOG
  - `@Logging.logapicall()`: 自動記錄 API 呼叫到 API_LOG

#### 3.5.2 metrics.py
**指標收集**:
```python
# 每分鐘指標
metrics.inc_api_call()        # API 呼叫計數
metrics.inc_bq_write(rows)    # BigQuery 寫入計數
metrics.maybe_flush()         # 自動刷新
```

#### 3.5.3 pubsub_services.py
**Pub/Sub 整合**:
- 批次完成時發佈回調消息
- 自動觸發下一批次
- 錯誤處理和重試

#### 3.5.4 request_context.py
**請求上下文管理**:
```python
# 在請求開始時設置共享日誌
set_current_log(shared_log)

# 在路由或服務中獲取共享日誌
shared_log = get_current_log()

# 請求結束時清理
clear_current_log()
```

### 3.6 配置層 (modules/)

#### Configuration (config.py)
**配置管理**:
- YAML 檔案加載
- 環境特定配置
- 點記法路徑支援
- Secret Manager 整合

**單例模式**:
```python
config = get_config()  # 全域快取實例
```

## 4. 資料流程

### 4.1 Daily Job 流程
```
┌────────────┐
│ Daily Job  │ (External Scheduler)
└─────┬──────┘
      │
      ↓
┌──────────────────────────────┐
│ POST / (trigger_geo_flow)    │ Route
└─────┬────────────────────────┘
      │
      ↓
┌──────────────────────────────┐
│ DataflowService              │ Service
│ .handle_daily_request()      │
└─────┬────────────────────────┘
      │
      ↓
┌──────────────────────────────┐
│ BatchProcessService          │ Application
│ ._process_batch_generic()    │
└─────┬────────────────────────┘
      │
      ├─→ Load Data (BigQuery)
      ├─→ Process Records (Google Maps API)
      ├─→ Write Results (BigQuery/GCS)
      └─→ Publish Callback (Pub/Sub)
           │
           ↓
┌──────────────────────────────┐
│ Pub/Sub Topic (geo-batch)    │
└──────────────────────────────┘
           │
           ↓ (Cloud Run / Function)
┌──────────────────────────────┐
│ POST /get_data_range         │ Route
└──────────────────────────────┘
```

### 4.2 日期範圍批次流程
```
Pub/Sub Message (start_date, end_date)
      ↓
POST /get_data_range
      ↓
DataflowService.handle_date_range_request()
      ↓
BatchProcessService._process_batch_generic()
      ↓
[相同的批次處理邏輯]
```

### 4.3 單筆記錄處理流程
```
┌─────────────────────────────────────────────────┐
│ Raw Record (CUID, Address, Coordinates)         │
└────────────────┬────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────┐
│ Data Validation (Pydantic)                      │
│ Coordinate Validation                           │
└────────────────┬────────────────────────────────┘
                 ↓
         ┌───────┴──────────┐
         │                  │
    Invalid              Valid
         │                  │
         ↓                  ↓
    [Skip/Error]   [Call API]
         │              │
         │              ↓
         │      ┌─────────────────────────────────┐
         │      │ GoogleMapsAPIClient             │
         │      │ .get_places_aggregate()         │
         │      └─────────────┬───────────────────┘
         │                    │
         │            ┌───────┴──────────┐
         │            │                  │
         │        Success           Failure
         │            │                  │
         │            ↓                  ↓
         │      [Record POI]    [Retry/Log]
         │            │                  │
         └────────────┼──────────────────┘
                      ↓
         ┌─────────────────────────────────┐
         │ Write to BigQuery               │
         │ - TMP_GEO_DATA (success)        │
         │ - FAILED_RETRY_LIST (failure)   │
         └─────────────────────────────────┘
```

## 5. 錯誤處理策略

### 5.1 異常層級
```
┌─────────────────────────────┐
│ GeoDataError (Base)         │
├─────────────────────────────┤
│ - DataValidationError       │
│ - GoogleMapsAPIError        │
│ - PubSubError               │
│ - BigQueryError (implicit)  │
└─────────────────────────────┘
```

### 5.2 重試策略
```
First Attempt
      ↓
   Failed
      ↓
Exponential Backoff
  Retry 1: 1s
  Retry 2: 2s
  Retry 3: 4s
      ↓
   Max Retries Reached
      ↓
Record in FAILED_RETRY_LIST
```

## 6. 效能優化

### 6.1 速率限制
- **目標**: 1200 QPM (20 QPS)
- **實現**: `GoogleMapsAPIClient._rate_limit()`
- **監控**: `metrics.inc_api_call()` 每分鐘計數

### 6.2 批次大小
- **配置項**: `google_maps_batch_size` (預設 100)
- **調整**: 根據記憶體和 API 限制

### 6.3 非同步處理
- **Pub/Sub 機制**: 減少 HTTP 超時風險
- **批次回調**: 自動化連續批次處理

## 7. 監控和診斷

### 7.1 日誌查詢
```sql
-- 查詢特定流程的所有任務
SELECT * FROM LOG_DATASET.FLOW_LOG
WHERE flow_code = "E06_geo_data_resolver"
  AND DATE(timestamp) = CURRENT_DATE()
ORDER BY timestamp

-- 查詢 API 效能
SELECT 
  DATE(timestamp) as date,
  COUNT(*) as total_calls,
  COUNTIF(status_code = "200") as success,
  AVG(response_time_ms) as avg_response_ms
FROM LOG_DATASET.API_LOG
WHERE DATE(timestamp) >= CURRENT_DATE() - 7
GROUP BY date
```

### 7.2 效能指標
- **QPS (Queries Per Second)**: 應保持 ≤ 20
- **API 成功率**: 應 > 95%
- **批次完成率**: 應 100%

## 8. 擴展性考慮

### 8.1 水平擴展
- 無狀態設計支援多實例部署
- 共享 BigQuery 和 Pub/Sub 資源
- 使用 Cloud Load Balancer 分散流量

### 8.2 垂直擴展
- 增加批次大小提高吞吐量
- 調整 QPM 限制
- 優化 BigQuery 查詢

### 8.3 新 POI 情境支援
1. 在 `POIScenarioEnum` 中新增情境
2. 在 `config.yaml` 中配置 POI 類型對映
3. 無需修改核心邏輯

## 9. 安全性考慮

- **Secret Manager**: API 金鑰加密儲存
- **IAM 角色**: 最小權限原則
- **日誌隔離**: 敏感資訊屏蔽
- **Pub/Sub 認證**: 服務帳號驗證

## 10. 版本資訊

- **版本**: 1.0.0
- **最後更新**: 2025-10-27
