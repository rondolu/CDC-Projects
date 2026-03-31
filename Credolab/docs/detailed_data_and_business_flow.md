# Credolab 資料處理系統 - 詳細資料與業務流程說明（已同步 2025-09 程式現況）

## 專案概述

Credolab 資料處理系統是一個基於 Flask 的雲端服務應用程式，專門用於整合 VMB（Virtual Mobile Banking）資料處理與 Credolab API 呼叫。系統採用 Service Layer 架構設計，重點在於批次處理資料、API 呼叫、儲存到 BigQuery 和 GCS，並支援 Pub/Sub 回調機制，專為 Google Cloud Run 無人為介入的環境設計。

### 核心功能
- **批次資料處理**：支援大規模 VMB 資料的批次處理
- **Credolab API 整合**：自動呼叫 Credolab API 獲取裝置洞察資料
- **多儲存支援**：資料儲存至 BigQuery 和 Google Cloud Storage
- **Pub/Sub 回調機制**：支援非同步批次處理和重試機制
- **錯誤處理**：完整的錯誤處理和重試邏輯

## 系統架構

### 整體架構圖
```
HTTP Request / PubSub Message
        ↓
[Flask Routes] (blueprints/credolab_routes.py)
        ↓
[DataFlow Service] (services/dataflow_service.py)
        ↓
[Batch Process Service] (application/batch_process_service.py)
        ↓
├── [BigQuery Service] (application/bigquery_service.py)
├── [Credolab API Service] (services/credolab_api_service.py)
├── [GCS Service] (utils/gcs_services.py)
└── [PubSub Service] (utils/pubsub_services.py)
```

### 主要組件說明

#### 1. 路由層 (Blueprints)
- **檔案**：`blueprints/credolab_routes.py`
- **功能**：處理 HTTP 請求和 Pub/Sub 訊息
- **主要路由**：
  - `POST /`：觸發日常批次處理流程
  - `POST /get_data_range`：處理日期範圍批次或 Pub/Sub 回調

#### 2. 資料流程服務 (DataFlow Service)
- **檔案**：`services/dataflow_service.py`
- **功能**：統一流程處理，負責請求解析、模式判斷、Pub/Sub 訊息處理
- **支援模式**：
  - **Daily 模式**：處理昨天的資料（自動使用 partition_date）
  - **Range 模式**：處理指定日期範圍的資料

#### 3. 批次處理服務 (Batch Process Service)
- **檔案**：`application/batch_process_service.py`
- **功能**：核心業務邏輯，負責資料載入、API 呼叫、資料儲存
- **關鍵方法**：
  - `_load_vmb_data()`：載入 VMB 資料
   - `_process_batch_records()`：處理單一批次中的所有記錄（批次層級協調）
   - `process_single_vmb_record()`：處理單筆 VMB 記錄（記錄層級處理）
   - （已移除）`retry_failed_calls()`：不再於流程結束自動執行失敗重試

##### `_process_batch_records` 方法詳解
**職責**：批次層級的協調和錯誤處理
- 接收一個批次的記錄列表
- 逐筆呼叫 `process_single_vmb_record()` 處理每筆記錄
- 負責錯誤分類和失敗記錄的儲存
- 在批次完成後觸發下一批次的 Pub/Sub 訊息
- 返回該批次的處理結果統計

##### `_load_vmb_data` 方法詳解
**職責**：資料載入和查詢參數處理
- 根據是否有日期參數動態選擇 SQL 查詢檔案
  - 有日期參數：使用 `get_vmb_data_range.sql`
  - 無日期參數：使用 `get_vmb_data.sql`（Daily 模式）
- 自動設定 `partition_date` 為當前 UTC 日期
- 支援裝置類型過濾（`device_type` 參數）
- 處理查詢參數的格式化和傳遞
- 返回 BigQuery 查詢結果的記錄列表

##### `_orchestrate_batch_processing` 方法詳解
**職責**：批次處理的整體協調和狀態管理
- 生成批次 ID 用於追蹤和日誌記錄
- 計算當前批次的資料範圍：`start_idx = (batch_number - 1) * batch_size`
- 處理批次資料切片：`batch_data = data[start_idx:end_idx]`
- 設定下一批次的發布回調函數
- 判斷是否為最後一批次並執行相應邏輯
- 統籌批次完成後的重試機制
- 返回詳細的批次處理結果統計

##### `_initiate_batch_processing` 方法詳解
**職責**：第一批次的特殊處理邏輯
- 計算總批次數：`(total_records + batch_size - 1) // batch_size`
- 處理第一批次資料（前 `batch_size` 筆記錄）
- 設定非同步回調機制用於觸發後續批次
- 根據總批次數決定回應格式：
  - 多批次：返回 "processing" 狀態，觸發下一批次
  - 單批次：執行重試後返回 "completed" 狀態
- 整合第一批次結果和重試結果的統計資訊

##### （變更）原 `retry_failed_calls` 已取消
目前流程在所有批次完成後不再自動讀取失敗清單並重試；失敗記錄仍會寫入 `CREDOLAB_FAILED_RETRY_LIST` 供後續離線或人工工具處理。

##### `_save_credolab_response` 方法詳解
**職責**：API 回應資料的結構化儲存
- 使用 `data_processor.prepare_raw_data_for_bq()` 組裝完整資料
- 根據 `device_os` 欄位動態選擇目標表格：
  - Android：`TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_ANDROID`
  - iOS：`TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_IOS`
- 驗證裝置類型，未知類型拋出 `DataValidationError`
- 呼叫 BigQuery 服務執行資料插入
- 記錄儲存操作的詳細日誌資訊

##### `_upload_raw_data_to_gcs` 方法詳解
**職責**：原始資料的備份儲存
- 將 VMB 記錄序列化為 JSON 格式（保留非 ASCII 字元）
- 生成結構化的 GCS 檔案路徑：
  - 格式：`{blob_path}/{YYYY-MM-DD}_{device_os}_{reference_id}.json`
  - 範例：`EDEP/CREDOLAB/2025-09-10_android_ABC123.json`
- 設定適當的內容類型（`application/json`）
- 呼叫 GCS 服務執行檔案上傳
- 記錄上傳操作的詳細資訊和檔案路徑

##### `_read_sql_file` 方法詳解
**職責**：SQL 檔案的動態載入和錯誤處理
- 建構 SQL 檔案的絕對路徑：`{專案根目錄}/sql/{檔案名稱}`
- 驗證 SQL 檔案是否存在，檔案不存在拋出 `FileNotFoundError`
- 以 UTF-8 編碼讀取檔案內容
- 處理檔案讀取異常並提供詳細錯誤訊息
- 返回 SQL 查詢字串供後續格式化和執行

##### `_handle_operation_error` 方法詳解
**職責**：統一的錯誤分類和處理邏輯
- 根據異常類型進行智慧分類：
  - `GoogleCloudError`：GCP 服務相關錯誤
  - `CredolabAPIError`：API 呼叫相關錯誤（保持原始類型）
  - `DataValidationError`：資料驗證錯誤（保持原始類型）
  - 其他異常：通用錯誤處理
- 記錄詳細的錯誤資訊到系統日誌
- 將具體錯誤封裝為標準化的 `CredolabError` 物件
- 支援額外的上下文資訊傳遞以便問題診斷

##### `_generate_batch_id` 方法詳解
**職責**：批次識別碼的生成和管理
- 使用批次編號作為簡單的識別碼格式
- 確保批次 ID 的唯一性和可追蹤性
- 支援日誌記錄和狀態追蹤的需要
- 返回字串格式的批次識別碼

#### 4. 資料服務
- **BigQuery 服務**：`application/bigquery_service.py`
- **GCS 服務**：`utils/gcs_services.py`
- **Credolab API 服務**：`services/credolab_api_service.py`

## 資料流程

### Daily 處理流程（現況）

1. **觸發階段**
   - 接收 POST 請求到 `/` 路由
   - DataFlowService.handle_daily_request() 檢查是否為 Pub/Sub 訊息

2. **資料載入階段**
   - 呼叫 BatchProcessService._load_vmb_data()
   - 使用 `sql/get_vmb_data.sql` 查詢「當前 UTC 日期 (today UTC)」的 VMB 資料
   - `partition_date` 來源：`datetime.now().strftime('%Y-%m-%d')`

3. **批次處理階段**
   - 動態批次確定：根據每次 SQL 查詢結果大小判斷（無需預先計算總批次數）
   - 處理第一批次資料：
     - `_process_batch_records()` 接收該批次的記錄列表
     - 逐筆呼叫 `process_single_vmb_record()` 處理每筆記錄
     - 每筆記錄處理包含：API 呼叫 → GCS 上傳 → BigQuery 儲存
   - 記錄處理結果和錯誤統計

4. **回調機制**
   - 若查詢結果 >= 50 筆：第一批走 `_initiate_batch_processing`，其內部在批次所有記錄完成後透過 `callback_handler` 發布下一批 recall 訊息
   - Daily 模式的 recall 訊息：`message_type = "daily_recall"`，attributes 內仍包含 `start_date`, `end_date` key 但值為空字串
   - 後續批次由 `_orchestrate_batch_processing` 處理；若查詢結果 < 50 筆表示最後一批，則進入 flatten 及 anonymization 流程
   - 回調訊息由不同的 Pub/Sub 推送訂閱指向對應端點（每日可推到 `/`，但程式也能在 `/get_data_range` 解析 message_type）

5. **（變更）重試階段**
   - 已完全移除「流程尾自動重試」：程式不會在所有批次完成後再讀取失敗清單
   - 所有失敗（API 非 2xx 或其他例外）僅寫入 `RAW_EDEP_DATASET.CREDOLAB_FAILED_RETRY_LIST`
   - 日後若需補處理：建議外部排程（Cloud Scheduler + Cloud Run / Dataform）掃描表再補呼叫

### Range 處理流程（現況）

1. **觸發階段**
   - 接收 POST 請求到 `/` 路由，包含 start_date 和 end_date
   - 或接收 Pub/Sub 回調訊息到 `/get_data_range`

2. **資料載入階段**
   - 使用 `sql/get_vmb_data_range.sql` 查詢指定日期範圍的資料
   - 支援 device_type 過濾

3. **批次處理階段**
   - 與 Daily 批次處理邏輯相同（第一批 `_initiate_batch_processing`，後續 `_orchestrate_batch_processing`）
   - Range 模式 recall 訊息：`message_type = "range_recall"`，attributes 中 `start_date` / `end_date` 為實際日期字串
   - 中斷後恢復：依靠 Pub/Sub recall 連鎖（程式目前未提供「直接指定任意批次重新處理」API）

## 資料結構

### 上行電文 (VMB 資料輸入)

從 BigQuery `RAW_VMB_DATASET.CREDOLAB_DATA` 載入的原始記錄：

```json
{
  "cuid": "用戶唯一識別碼",
  "reference_id": "參考編號（用於 API 查詢）",
  "device_os": "裝置作業系統（android/ios）",
  "created_timestamp": "建立時間",
  "serial_number": "HES 申貸編號"
}
```

### 下行電文 (Credolab API 回應輸出)

API 回應的 JSON 資料，包含裝置洞察資訊：

```json
{
  "referenceNumber": "參考編號",
  "insights": [
    {
      "code": "deviceInfo",
      "value": {
        "deviceId": "裝置 ID",
        "deviceBrand": "品牌",
        "deviceModel": "型號"
      }
    }
  ],
  "requestedDate": "請求日期"
}
```

### 儲存至 RAW 表後（實際寫入結構）

`BatchProcessService._save_credolab_response()`：

1. 依 `device_os` 寫入：
   - Android → `RAW_EDEP_DATASET.CREDOLAB_DATA_ANDROID`
   - iOS → `RAW_EDEP_DATASET.CREDOLAB_DATA_iOS`
2. 寫入資料欄位（由 `prepare_raw_data_for_bq` 組裝）：
```json
{
  "uuid": "UUID",
  "cuid": "客戶 ID",
  "reference_id": "參考編號",
  "series_number": "申貸編號",
  "device_os": "android|ios",
  "raw_data": "Credolab API 原始回應 JSON 字串",
  "BQ_UPDATED_TIME": "UTC ISO 時間",
  "PARTITION_DATE": "YYYY-MM-DD"
}
```
3. 最終（單批或最後一批）才執行 flatten：
   - `flatten_data_android.sql` / `flatten_data_ios.sql` 將 RAW 新增記錄轉入 `TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_ANDROID` / `TMP_CREDOLAB_DATA_iOS`（避免重覆：LEFT JOIN 過濾已處理 reference）
   - 接著發布 anonymization Pub/Sub 訊息（best-effort，不阻斷主流程）

## 業務邏輯

### 批次處理策略（現況）

1. **動態批次計算**
   - 根據總記錄數和設定批次大小動態計算批次數
   - 公式：`total_batches = (total_records + batch_size - 1) // batch_size`

2. **兩層處理架構**
   - **批次層**：`_process_batch_records` 負責批次級別的協調
     - 管理批次內的記錄迴圈
     - 處理跨記錄的錯誤統計
     - 負責批次間的狀態轉換
   - **記錄層**：`process_single_vmb_record` 負責單筆記錄的處理
     - 處理單筆記錄的完整業務邏輯
     - 管理 API 呼叫和資料儲存
     - 確保每筆記錄的原子性處理

3. **立即儲存策略**
   - 每筆記錄 API 呼叫成功後立即：上傳 GCS → 寫入對應 RAW BQ 表
   - 失敗不寫 RAW 表，僅記錄至 `CREDOLAB_FAILED_RETRY_LIST`

4. **非同步回調機制**
   - Pub/Sub recall：每日（空日期 attributes） vs 區間（實際日期 attributes）
   - message body 以 `message_type` 區分：`daily_recall` / `range_recall`
   - 每批完成後才發布下一批（無「提前」並行）

### 方法協同工作流程

#### 完整處理鏈路（現況）：
```
1. 初始化階段
   ├── _read_sql_file() → 載入 SQL 查詢
   └── 初始化各服務組件 (BQ, GCS, API)

2. 資料載入階段
   ├── _load_vmb_data() → 查詢 VMB 資料
   └── _handle_operation_error() → 處理載入錯誤

3. 批次處理階段
   ├── _initiate_batch_processing() → 第一批次處理
   │   ├── _process_batch_records() → 批次層級協調
   │   │   └── process_single_vmb_record() → 逐筆記錄處理
   │   │       ├── _save_credolab_response() → BigQuery 儲存
   │   │       └── _upload_raw_data_to_gcs() → GCS 備份
   │   └── _generate_batch_id() → 批次 ID 生成
   │
   ├── _orchestrate_batch_processing() → 後續批次處理
   └── Pub/Sub 訊息觸發下一批次

4. Flatten / 後處理階段（僅單批或最後一批）
   ├── 執行 flatten SQL (android / ios)
   ├── 插入 TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_*
   └── 發布 anonymization 訊息（失敗僅 Warning）
```

#### 錯誤處理鏈路：
```
任何階段發生錯誤
    ↓
_handle_operation_error() → 錯誤分類和處理
    ↓
├── Google Cloud 錯誤 → 拋出 CredolabError
├── API 錯誤 → 保持 CredolabAPIError 類型
├── 驗證錯誤 → 保持 DataValidationError 類型
└── 其他錯誤 → 封裝為 CredolabError
    ↓
上層方法捕獲並記錄到失敗重試列表
```

### 錯誤處理和重試機制（現況）

1. **錯誤分類**
   - **API 錯誤**：Credolab API 呼叫失敗
   - **資料驗證錯誤**：輸入資料格式錯誤
   - **儲存錯誤**：BigQuery/GCS 儲存失敗
   - **系統錯誤**：其他未預期錯誤

2. **重試邏輯**
   - 核心流程不自動重試
   - 失敗記錄僅落表保留供外部後續機制
   - 若未來導入：可建立獨立 Cloud Run Job 讀取失敗表再重呼 Credolab API

3. **錯誤記錄結構**
   ```json
   {
     "reference_id": "參考編號",
     "api_payload_message": "原始 VMB 記錄 JSON",
     "status_code": "HTTP 狀態碼或 'failed'",
     "error_message": "錯誤訊息",
     "uuid": "唯一識別碼",
     "created_at": "建立時間"
   }
   ```

## 儲存策略

### BigQuery 儲存（現況）

1. **Immediate RAW Ingestion**
   - Android：`RAW_EDEP_DATASET.CREDOLAB_DATA_ANDROID`
   - iOS：`RAW_EDEP_DATASET.CREDOLAB_DATA_iOS`
2. **Flatten（最後 / 單批）**
   - 產出：`TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_ANDROID` / `TMP_CREDOLAB_DATA_iOS`
   - SQL 會避免重複插入（LEFT JOIN 與 NULL 判斷）
3. **失敗記錄**
   - `RAW_EDEP_DATASET.CREDOLAB_FAILED_RETRY_LIST`

### Google Cloud Storage 儲存

1. **檔案路徑格式**
   ```
   {bucket_name}/{blob_path}/{YYYY-MM-DD}_{device_os}_{reference_id}.json
   ```

2. **檔案內容**
   - 儲存原始 VMB 記錄（上行電文）
   - JSON 格式，便於後續分析

## 配置管理

### 主要配置項目

- **批次處理**：`credolab_batch_size` - 每批處理的記錄數
- **BigQuery**：
  - `bq_credolab_table_android` - Android 資料表
  - `bq_credolab_table_ios` - iOS 資料表
  - `bq_raw_edep_dataset` - 原始資料集
- **GCS**：
  - `gcs_bucket_name` - 儲存桶名稱
  - `gcs_blob_path` - 物件路徑
- **Pub/Sub**：
  - `pubsub_topic_daily_recall` - 日常回調主題
  - `pubsub_topic_range_recall` - 範圍回調主題

## 監控和日誌

### 日誌系統

1. **結構化日誌**
   - 使用 `utils/infra_logging.py` 的 `Logging` 類（唯一入口）
   - FLOW / API 兩種表 + Cloud Logging 雙寫

2. **日誌分類**
   - **流程日誌**：記錄業務流程執行狀態
   - **錯誤日誌**：記錄異常情況
   - **效能日誌**：記錄處理效能指標

### 關鍵指標（建議觀測）

- API 呼叫成功/失敗數
- 批次處理時間
- 資料處理量
- 重試成功率

## 部署和運行

### 環境需求

- Python 3.8+
- Google Cloud Platform
  - Cloud Run
  - BigQuery
  - Cloud Storage
  - Pub/Sub
  - Secret Manager

### 啟動流程

1. **環境設定**
   - 安裝依賴：`pip install -r requirements.txt`
   - 設定 GCP 認證
   - 配置環境變數

2. **服務啟動**
   - 執行 `python main.py`
   - 或使用 `start.sh` 腳本

3. **健康檢查**
   - 檢查服務狀態
   - 驗證 GCP 服務連線

## 總結

Credolab 資料處理系統是一個高度自動化的批次處理平台，具備以下特點：

- **高可用性**：支援非同步處理和錯誤恢復
- **可擴展性**：動態批次計算和資源調度
- **資料完整性**：立即儲存和去重機制
- **監控完善**：完整的日誌和指標追蹤
- **雲端原生**：充分利用 GCP 服務特性

系統設計充分考慮了生產環境的需求，支援大規模資料處理，同時保持了良好的錯誤處理和重試機制。

### 方法設計理念總結

#### 1. **關注點分離原則**
- **資料載入**：`_load_vmb_data()` 專注資料查詢
- **批次協調**：`_process_batch_records()` 專注批次管理
- **記錄處理**：`process_single_vmb_record()` 專注業務邏輯
- **儲存操作**：`_save_credolab_response()` / `_upload_raw_data_to_gcs()` 專注資料持久化
- **錯誤處理**：`_handle_operation_error()` 統一錯誤分類

#### 2. **單一職責原則**
- 每個方法都有明確且專注的職責
- 方法間通過明確的介面進行協作
- 避免方法過於龐大和複雜

#### 3. **立即儲存策略**
- 每筆記錄處理完成後立即儲存
- 確保資料不因系統中途失敗而遺失
- 支援部分失敗場景下的資料恢復

#### 5. **統一錯誤處理**
- `_handle_operation_error` 做分類：GCP / CredolabAPIError / DataValidationError / 其他 → 包裝 CredolabError
- 批次內錯誤不會中斷其他記錄

#### 5. **可擴展的架構設計**
- 方法支援參數化配置
- 容易添加新的處理邏輯
- 支援不同類型的批次處理模式
