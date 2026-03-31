# 批次處理非同步機制說明

## 概述

為避免長時間執行限制，系統以 Pub/Sub 實作非同步批次處理。以下為現況要點：

- `services/dataflow_service.py`：統一流程入口與回呼（`process` / `process_recall_batch`）
- `application/batch_process_service.py`：核心批次處理（逐筆即時存檔；失敗落表，不自動重試）
- `utils/pubsub_services.py`：回調訊息發布（daily/range）與 anonymization 通知
- `utils/gcs_services.py`：GCS 批次上傳
- `utils/secret_services.py`：Secret Manager（Credolab API key）

### QPM（每分鐘查詢率）與重試

QPM 與重試由 `infrastructure/credolab_client.py` 內部處理（例如 429/5xx 的指數退避）；批次層不主動控制重試僅記錄結果。

## 架構設計說明

### 架構重點

採用小型、職責明確的服務：

**Pub/Sub 功能**：

- `publish_daily_recall_message()`：Daily 回調（日期屬性為空字串）
- `publish_range_recall_message()`：Range 回調（日期屬性為實際值）
- `publish_anonymization()`：匿名化觸發

### 統一的服務架構

```
CredolabService
    ├── BigQueryService (資料查詢)
    ├── CredolabAPIService (API 呼叫) 
    └── 專責服務（GCSService / PubSubService / SecretManagerService）
        ├── BigQuery 操作
        ├── Cloud Storage 操作
        └── Pub/Sub 操作 (包含批次處理)
```

## 處理流程

### 1) 初始觸發（Daily `POST /`；Range `POST /get_data_range` 或帶日期 `process()`）

```
手動觸發或排程觸發
    ↓
執行 get_vmb_data.sql（daily，UTC 今日 partition_date） / get_vmb_data_range.sql（range） 查詢
    ↓
處理第一批次（`_initiate_batch_processing`）
    ↓
第一批所有記錄完成後，視情況發布回調訊息（`publish_daily_recall_message` / `publish_range_recall_message`）
    ↓
回傳初始處理結果
```

### 2) 批次鏈式處理（回調端點）

```
接收 Pub/Sub 訊息（message body `message_type`: daily_recall|range_recall）
    ↓
重新查詢 VMB 資料（同一 SQL 再計算）
    ↓
`_orchestrate_batch_processing`：逐筆 API → (成功) GCS + RAW BQ / (失敗) 失敗表
    ↓
批次完成：
    ├─ 非最後批：發布下一批 recall
    └─ 最後批：flatten（android / ios）→ 發 anonymization（失敗不阻斷）
```

## 關鍵改進

### 1. 通用服務拆分

- **專責服務**：避免重複程式碼且易於測試/維護
- **擴展批次處理功能**：在既有架構上新增批次處理方法
- **保持一致性**：所有 GCP 服務使用同一個管理器

### 2) 回調訊息方法

```python
# Pub/Sub 專責服務使用：
def publish_daily_recall_message(self, current_batch, attributes=None)

def publish_range_recall_message(self, current_batch, start_date, end_date, attributes=None)
```

### 3) 配置整合

以 `config.yaml` 設定主題名稱（不在本文重述訂閱名稱；實務上請建立推送訂閱並配置篩選器）。

## 處理流程詳解

### 從 get_vmb_data.sql 到 API 呼叫的流程（摘要）

1. **查詢 VMB 資料**

   ```python
   vmb_data = self._get_vmb_data_by_date_range(start_date, end_date, device_type)
   ```

2. **批次資訊**：根據查詢結果與 `batch_size` 決定是否需回調

3. **處理第一批次**：呼叫 `_initiate_batch_processing()`

4. **在 `_process_batch()` 中的優化處理**：

   **逐筆即時處理**

   ```python
   for record in batch:
       # 處理記錄（包含 API 呼叫和立即儲存）
       if self.process_single_vmb_record(record):
           successful_api_count += 1
           logging.info(f"Successfully processed and saved reference {reference_id} immediately")
   ```

   **批次完成後判斷是否發布下一批次**

   ```python
   # 整個批次完成後，若仍有下一批才發布 recall 訊息
   message_id = publish_next_batch_callback()  # 內部已判斷是否為最後一批
   ```

5. **關鍵特性**：每筆成功即時寫入；失敗落表；批次完成後才發布下一批

## 優勢

### 1. 架構簡潔

- **單一責任**：以功能拆分服務類別，降低耦合
- **避免重複**：不需要額外的 Pub/Sub 服務類別
- **易於維護**：所有 GCP 操作集中管理

### 2. 功能完整

- **批次處理**：支援非同步批次處理（第一批 + recall）
- **錯誤處理**：統一錯誤處理；失敗寫入 CREDOLAB_FAILED_RETRY_LIST（僅記錄）
- **監控日誌**：完整的處理日誌

### 3. 向後相容

- **既有功能**：保留所有現有的 Pub/Sub 功能
- **擴展性**：容易添加新的 GCP 服務功能

## 配置範例

### config.yaml

```yaml
pubsub:
    credolab_topic: "credolab"
    anonymization_topic: "anonymization"
credolab_api:
    batch_size: 50
    qpm_limit: 50
```

## 相關文件

- 資料流摘要：`docs/DATAFLOW_SUMMARY.md`
- 回調機制：`docs/RECALL_MECHANISM_GUIDE.md`
- 日誌機制：`docs/LOGGING_GUIDE.md`
