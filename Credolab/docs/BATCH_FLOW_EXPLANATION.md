# 批次處理流程

## 階段 1：載入 VMB 資料
- 依是否有日期參數選擇 `get_vmb_data.sql` 或 `get_vmb_data_range.sql`
- 設定查詢參數（例如 partition_date），呼叫 BigQuery 取得資料清單

## 階段 2：初始化批次處理（第一批）
- 建立回調（recall）用的處理器（daily/range 分別發布不同的訊息格式）
- 處理第一批資料（大小以 `batch_size` 為準）

## 階段 3：處理單一批次記錄
- 逐筆呼叫 Credolab API 取得 insights
- 成功：彙整後批次寫入 BigQuery、上傳原始記錄至 GCS
- 失敗：寫入 Failed Retry 表（主流程不自動重試）
- 批次完成：依情況發布下一批 recall 訊息

## 階段 4：回調批次（recall）
- 接收 Pub/Sub push 後，解析 message_type（daily_recall/range_recall）
- 重新查詢資料，處理指定批次
- 判斷是否為最後一批（以結果筆數與 `batch_size` 比較）
  - 非最後一批：發布下一批 recall
  - 最後一批：執行 flatten SQL（android/ios）並發布 anonymization（必要時）

## Recall 訊息（由 `utils.pubsub_services.PubSubService` 發布）
- Daily：attributes 內 `start_date`、`end_date` 以空字串表示（由 daily 訂閱接收，路由至 `/`）
- Range：attributes 帶實際日期值（由 range 訂閱接收，路由至 `/get_data_range`）

## 其他說明
- 日誌：使用 `utils/infra_logging.Logging` 寫入 FLOW_LOG（完成/錯誤）與 API_LOG
- 表名/資料集/Topic：以 `config/config.yaml` 與環境變數為準

<!-- ----------------------------------------------------------------------------- -->

## 概述
```
批次開始 → 逐筆：API → (成功) GCS + BQ / (失敗) 寫失敗表 → 直到所有筆完成 → 判斷是否發布下一批
```

### **核心特性（現況）**

1. 每筆成功 API → 立即 GCS + RAW BQ
2. 整批完成後才發布下一批（無跨批並行）
3. 失敗記錄寫入 `CREDOLAB_FAILED_RETRY_LIST`（不自動重試）

## 技術重點（對照現行程式）

- 逐筆即時處理：API 成功後立即 GCS + RAW BQ
- 批次完成後才發布下一批（避免跨批並行與競態）
- 失敗落 `Failed Retry` 表（不自動重試）

#### **即時資料可用性**

- 每筆資料處理完立即可在 BigQuery 中查詢
- GCS 中的原始資料即時可用
- 不需要等待整個批次完成

#### **簡化流程**

避免「發布下一批後仍處理上一批存儲」的競態，降低觀測與追蹤複雜度。

### **效能說明（不以虛構數值評估）**

省略併行存儲優化後，性能仍受限於：
* API 呼叫延遲
* QPM 限制（預設 50/min）
* 單筆存儲（GCS + BQ）開銷

- **資料即時可用**：不需要等批次完成
- **錯誤隔離**：單筆失敗不影響其他筆的儲存
- **系統響應性**：更快的資料流轉

### 1. Daily 模式回調

```python
# 第1筆：API成功 → 立即存GCS + 立即存BigQuery
# 第2筆：API成功 → 立即存GCS + 立即存BigQuery
# ...
# 第50筆：API成功 → 立即存GCS + 立即存BigQuery
# 整批完成 → 立即發布daily recall訊息
```

### 2. Range 模式回調

```python
# 同樣的即時處理模式
# 整批完成 → 立即發布range recall訊息
```

## 錯誤處理與容錯（現況）

### 1. 單筆處理錯誤隔離

```python
for record in batch:
    try:
        api_data = self.fetch_credolab_data_for_record(record)
        # 立即儲存這一筆
        self._save_credolab_response(...)
        successful_count += 1
    except Exception as e:
        # 這一筆失敗，不影響其他筆的處理
        logging.error(f"Record {reference_id} failed: {e}")
        continue
```

### 2. 儲存錯誤處理
若 GCS 或 BQ 寫入失敗：記錄錯誤並將該筆寫入失敗表（狀態碼 'failed' 或實際 HTTP），繼續下一筆。

## 核心程式區塊

- `_process_batch_records`：逐筆處理 + 統計 +（需要時）發布下一批
- `_initiate_batch_processing`：第一批處理 + recall handler 設定
- `_orchestrate_batch_processing`：後續批次處理

## 使用範例

```python
# 啟動優化的 Daily 批次處理（使用 Flow Service）
from services.dataflow_service import DataFlowService

service = DataFlowService()
result = service.process(
    start_date="2025-01-15",
    end_date="2025-01-15"
)

# 處理流程：
# 第1筆: API → 立即存GCS → 立即存BigQuery
# 第2筆: API → 立即存GCS → 立即存BigQuery
# ...
# 第50筆: API → 立即存GCS → 立即存BigQuery
# 批次完成 → 立即觸發下一批次

# 結果會顯示：
# "message": "Daily batch 1/5 completed, next batch triggered immediately after API calls"
```

## 監控與追蹤

日誌重點：
* 單筆成功 / 失敗輸出（stdout + Cloud Logging + FLOW/API LOG）
* 批次完成摘要
* 最終批次：flatten SQL 執行紀錄 + anonymization 訊息 ID

### 效能指標

- **即時儲存成功率**: 每筆資料儲存是否成功
- **API 批次完成時間**: 整個批次 API 呼叫完成時間
- **下一批次觸發延遲**: 從 API 完成到觸發下一批次的時間

## 不採用的概念（保留註記）

- 分離 fetch→publish→save 三階段
- 跨批並行（下一批 API 與上一批存儲並行）
- 批次級別的延遲觸發調整

### 1. Daily Job 回調

- 使用 `DataFlowService.process()` (mode='daily')
- 發布空日期屬性的訊息到 `credolab-sub02` (→ `/`)

### 2. Range 回調  

- 使用 `DataFlowService.process()` (mode='range')
- 發布實際日期屬性的訊息到 `credolab-sub01` (→ `/get_data_range`)

### 3. 進入點

僅使用 `process()` 與 `process_recall_batch()` 兩個進入點，無「指定批次處理」公開 API。

## 錯誤處理與容錯

### 1. API 呼叫階段錯誤

- 失敗的記錄寫入 `CREDOLAB_FAILED_RETRY_LIST`
- 成功的記錄繼續進行儲存流程
- 不影響下一批次的觸發

### 2. 儲存階段錯誤

- 儲存錯誤不影響批次處理結果
- 記錄詳細錯誤日誌
- 下一批次已經開始執行，提高整體容錯性

### 3. 訊息發布錯誤

- 記錄發布失敗的錯誤
- 不影響當前批次的儲存流程

## 向後相容性

現行版本移除了「獨立 fetch/save 分階段」與「公開單批接口」的需求，但保留原始流程語意：
* 入口語意未變（每日、區間、回調批次）。
* 仍可在未來替換批次內部實作而不影響路由層。

## 配置

無需額外配置，使用現有的：

- `batch_size`: 批次大小（預設50）
- Pub/Sub 主題和訂閱設定
- BigQuery 和 GCS 連線設定

## 使用範例

```python
# 啟動優化的批次處理（使用統一 Flow Service）
from services.dataflow_service import DataFlowService

service = DataFlowService()
result = service.process(
    start_date="2025-01-15",
    end_date="2025-01-15"
)

# 結果會顯示：
# "message": "Daily batch 1/5 completed, next batch triggered immediately after API calls"
```

## 總結（修訂）

| 項目 | 文件原描述 | 現行實作 |
|------|------------|-----------|
| 單筆處理 | API → GCS → BQ | 相同（同步逐筆） |
| 發布下一批 | API 完成後立即（與存儲並行） | 所有筆存儲完成後才發布 |
| 並行儲存 | 是 | 否 |
| 分離 fetch/save 階段 | 是 | 否（單函式完成） |
| 自動重試 | 未涉及此檔案，但其他文件曾描述 | 無自動重試（僅記錄失敗） |

本檔案已調整為「描述現況 + 標註原計畫差異」。未來如導入跨批並行可再增加效益量化。
