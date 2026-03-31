# Google Maps Geo Data Resolver

Google Maps 地理資料解析服務，整合 Google Maps Places Aggregate API 和 Pydantic 驗證機制。

## 專案概述

這是一個完整的 Python Flask 應用程式，專門用於處理地理位置的 POI (Point of Interest) 資料。

## 技術架構

### 核心技術棧
- **框架**: Python 3.9 + Flask + Gunicorn
- **API 整合**: Google Maps Places Aggregate API
- **資料驗證**: Pydantic v2.0+
- **雲端服務**: Google Cloud Platform (BigQuery, GCS, Pub/Sub, Secret Manager, Cloud Logging)
- **容器化**: Docker (python:3.9.17-slim-bullseye)

### 架構層級

```
├── 應用層 (Application Layer)
│   ├── batch_process_service.py     # 批次處理服務
│   └── bigquery_service.py          # BigQuery 資料管理
├── 服務層 (Service Layer)
│   ├── dataflow_service.py          # 資料流處理
│   └── google_maps_api_service.py   # Google Maps API 服務
├── 基礎設施層 (Infrastructure Layer)
│   └── google_maps_client.py        # API 客戶端與限流
├── 模型層 (Model Layer)
│   └── google_maps_models.py        # Pydantic 資料模型
├── 工具層 (Utilities Layer)
│   ├── infra_logging.py             # 統一日誌系統
│   ├── error_handling.py            # 錯誤處理
│   ├── data_processor.py            # 資料處理
│   ├── gcs_services.py              # Cloud Storage 服務
│   ├── pubsub_services.py           # Pub/Sub 消息服務
│   └── metrics.py                   # 指標收集
└── 路由層 (Routes Layer)
    └── geo_routes.py                 # Flask 路由定義
```

## 功能特性

### 核心功能
- **POI 情境查詢**: 支援 5 種 POI 情境 (corporate_finance, residential, commercial, facility, government)
- **批次處理**: 支援大量位置的批次處理和非同步作業
- **資料驗證**: 完整的 Pydantic 模型驗證
- **速率限制**: QPM (Queries Per Minute) 管理，目標 1200 QPM
- **重試機制**: 指數退避重試策略

### 管理功能
- **健康檢查**: 系統狀態監控
- **統計分析**: 處理統計和成功率分析
- **資料匯出**: 支援 CSV/JSON 格式匯出到 GCS
- **清理機制**: 自動清理舊資料

### 安全與監控
- **Secret Manager**: 安全的 API 金鑰管理
- **統一日誌**: 結構化日誌記錄
- **錯誤追蹤**: 完整的錯誤處理和追蹤
- **指標收集**: API 調用和效能指標

## API 端點

### 核心 API
- `POST /` - 觸發 Google Maps 地理資料處理流程（支持批次回調機制）
- `POST /get_data_range` - 處理特定日期範圍的批次請求

### 特性
- 支援 Daily Job 觸發點，自動處理批次和回調
- 通過 Pub/Sub 機制實現非同步批次處理
- 完整的批次狀態追蹤（使用 UUID）
- 自動重試失敗記錄機制

## 核心模組說明

### 1. 應用層 (Application Layer)
- **batch_process_service.py**: 核心批次處理邏輯
  - `BatchContext`: 批次上下文管理
  - `ProcessingResult`: 處理結果資料結構
  - `BatchProcessService`: 批次處理主類別
  - 支援通用編排、資料載入、單筆和批次記錄處理

- **bigquery_service.py**: BigQuery 資料管理
  - 檢查/建立資料集與資料表
  - 查詢和插入操作
  - 失敗清單記錄

### 2. 服務層 (Service Layer)
- **dataflow_service.py**: 資料流程編排
  - Daily Job 模式支援
  - 日期區間批次處理
  - Pub/Sub 回調機制實現

- **google_maps_api_service.py**: Google Maps API 高層介面
  - 座標驗證
  - API 呼叫管理
  - 效能指標追蹤

### 3. 基礎設施層 (Infrastructure Layer)
- **google_maps_client.py**: API 客戶端
  - HTTP 會話和重試策略
  - QPM 速率限制實現
  - Places Aggregate API 整合

### 4. 模型層 (Model Layer)
- **google_maps_models.py**: Pydantic 資料模型
  - `POIScenarioEnum`: 五大 POI 情境類型
  - 完整的資料驗證

### 5. 工具層 (Utilities Layer)
- **infra_logging.py**: 統一日誌系統
  - 流程日誌 (Flow Log) 記錄
  - API 日誌記錄
  - 裝飾器支援

- **error_handling.py**: 錯誤處理工具
  - 路由異常捕捉
  - Pub/Sub 請求判定

- **data_processor.py**: 資料處理
  - 原始資料行準備
  - 資料轉換

- **gcs_services.py**: Cloud Storage 服務
  - 檔案上傳/下載
  - 資料匯出

- **pubsub_services.py**: Pub/Sub 消息服務
  - 消息發佈
  - 錯誤處理

- **metrics.py**: 指標收集
  - 每分鐘 API 呼叫計數
  - BigQuery 操作計數
  - 自動刷新機制

- **request_context.py**: 請求上下文管理
  - 共享日誌實例管理

- **secret_manager_service.py**: Secret Manager 整合
  - API 金鑰管理

### 6. 路由層 (Routes Layer)
- **geo_routes.py**: Flask 藍圖
  - `trigger_geo_flow()`: Daily Job 觸發點
  - `get_data_range()`: 日期範圍處理
  - Pub/Sub 訊息適配

### 7. 配置管理
- **config.py**: Configuration 管理類別
  - YAML 配置載入
  - 環境特定配置
  - 多環境支援

## 配置管理

### config.yaml 結構
```yaml
default:
  gcp:
    project_id: "default-project"
  
  google_maps_api:
    base_url: "https://places.googleapis.com"
    secret_name: "google-maps-api-key"
    qpm_limit: 1200
    batch_size: 100
    max_retries: 3
    timeout: 30
    
  bigquery:
    raw_edep_dataset: "RAW_EDEP_DATASET"
    trans_edep_dataset: "TRANS_EDEP_DATASET"
    geo_table: "GEO_DATA"
    geo_failed_retry_table: "GEO_DATA_FAILED_RETRY_LIST"
    log_dataset: "LOG_DATASET"
    
  gcs:
    bucket_name: "your-bucket"
    blob_path: "geo-data/"
    
  pubsub:
    project_id: "your-project"
    batch_topic: "geo-batch-topic"
    geo_topic: "geo-geo-topic"

production:
  # 生產環境特定覆蓋
  gcp:
    project_id: "prod-project"
```

## 故障排除

### 常見問題

1. **Pub/Sub 回調未觸發**
   - 檢查 Pub/Sub 主題名稱配置
   - 驗證服務帳號具有 `pubsub.publisher` 角色
   - 確認 Cloud Run/雲端函式已訂閱主題

2. **批次處理無法完成**
   - 檢查 BigQuery 資料表權限
   - 確認日期範圍有效且資料存在
   - 查看失敗重試清單中的錯誤詳情

3. **API 配額超限**
   - 檢查 QPM 設定是否過高
   - 監控實時 API 呼叫計數
   - 調整批次大小以控制速率

4. **座標驗證失敗**
   - 確認緯度範圍: -90 ~ 90
   - 確認經度範圍: -180 ~ 180
   - 檢查資料格式是否為浮點數

5. **Secret Manager 存取失敗**
   - 驗證密鑰版本名稱正確
   - 檢查 IAM 角色綁定

- 使用 `request_context` 共享日誌實例

