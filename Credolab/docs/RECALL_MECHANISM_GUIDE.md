# Credolab 批次回調機制指南（同步 2025-10 現況）

## 批次回調流程設計

系統透過單一主題（由 `config.pubsub_credolab_topic` 設定）+ `message_type` 區分 daily 與 range；attributes 僅用於訂閱篩選；不自動重試最後一批失敗。

### 系統架構概覽

```
Topic: <config.pubsub_credolab_topic>
├── <subscription for range>  → 推送到 /get_data_range
│   └── 篩選器: (attributes.start_date AND attributes.end_date)
└── <subscription for daily>  → 推送到 /
    └── 篩選器: (NOT attributes.start_date OR NOT attributes.end_date)
```

重要：所有 recall 訊息 attributes 均包含 `start_date`,`end_date`；Daily = 空字串，Range = 實際日期。

## 流程 1: Daily Job 觸發 (`POST /`)

### 初始觸發

```http
POST /
Content-Type: application/json

{
  "start_date": "2025-01-15",
  "end_date": "2025-01-15",
  "device_type": "android"
}
```

### 處理流程

1. **執行** `get_vmb_data.sql` 查詢（partition_date = UTC 今日）
2. **計算**總批次數（依 config 之 batch_size，預設 50）
3. **處理**第一批次（逐筆 API→GCS→BQ）
4. **發布**帶有空字串日期 attributes 的 recall 訊息（若仍有下一批）

### Pub/Sub 訊息格式（由 `utils.pubsub_services.PubSubService.publish_daily_recall_message` 發布）

```json
{
  "message_type": "daily_recall",
  "processing_params": {
    "start_date": "2025-01-15",
    "end_date": "2025-01-15",
    "batch_number": 2,
    "total_batches": 5,
    "source": "daily_job"
  }
}
```

### 訊息屬性（用於訂閱篩選）

```json
{
  "start_date": "",  // 空值
  "end_date": "",    // 空值
  "category": "DAILY",
  "target_group": "ALL"
}
```

範例路由結果：

- Range 訂閱（→ `/get_data_range`）被過濾（因日期為空） 
- Daily 訂閱（→ `/`）接收（因日期為空） 

---

## 流程 2: PubSub 觸發 (`POST /get_data_range`)

### Pub/Sub 觸發

來自 `credolab-sub01` 的推送請求

### 處理流程

1. **執行** `get_vmb_data_range.sql` 查詢
2. **處理**指定批次號的資料
3. **發布**帶有**實際值** `start_date`、`end_date` attributes 的 Pub/Sub 訊息

### Pub/Sub 訊息格式（由 `utils.pubsub_services.PubSubService.publish_range_recall_message` 發布）

```json
{
  "message_type": "range_recall",
  "processing_params": {
    "start_date": "2025-01-15",
    "end_date": "2025-01-15",
    "batch_number": 3,
    "total_batches": 5,
    "source": "get_data_range"
  }
}
```

### 訊息屬性

```json
{
  "start_date": "2025-01-15",  // 實際值
  "end_date": "2025-01-15",    // 實際值
  "category": "MANUAL",
  "target_group": "txttobq"
}
```

範例路由結果：

- Range 訂閱（→ `/get_data_range`）接收（因有實際日期） 
- Daily 訂閱（→ `/`）被過濾（因有實際日期） 

---

## 訂閱篩選器設定

### credolab-sub01 篩選器

```
(attributes.start_date EXISTS AND attributes.end_date EXISTS)
```

**用途**: 接收 Range 回調訊息（帶有實際日期值）

### credolab-sub02 篩選器

```
(NOT attributes.start_date OR NOT attributes.end_date)
```

**用途**: 接收 Daily 回調訊息（日期屬性為空字串）

---

## 回調流程（摘要）

```
Daily Job (POST /) 
    ↓ 處理第一批次
    ↓ 發布訊息 (帶 dates)
credolab-sub01 → /get_data_range
    ↓ 處理第二批次
    ↓ 發布訊息 (不帶 dates)
credolab-sub02 → /
    ↓ 處理第三批次
    ↓ 發布訊息 (不帶 dates)
credolab-sub02 → /
    ⋮ (重複直到完成)
    ↓ 最後一批次 → flatten（android / ios）→ 發 anonymization（不重試失敗表）

接收 Pub/Sub 推送（message_type: daily_recall/range_recall）→ 根據批次號處理該批次並視情況發布下一批次

### 3. 路由端點修改

#### `POST /`
Daily 初始 & daily_recall 回調（可解析 range_recall 但語意建議分流）

#### `POST /get_data_range`
Range 初始 & range_recall 回調

---

## 配置要求（節錄）

### config.yaml

```yaml
pubsub:
  project_id: "<your-project-id>"
  credolab_topic: "<your-topic>"
```

（環境變數名稱請以專案 `modules/config.py` 的讀取邏輯為準）

---

## 測試建議

（調試命令依實際部署環境為準，避免在此重複列出）

---

## 注意事項

1. **訊息屬性是關鍵**: 確保正確設定 `start_date`、`end_date` 屬性
2. **篩選器語法**: 使用正確的 Pub/Sub 篩選器語法
3. **錯誤處理**: 每個批次都有獨立的錯誤處理機制
4. **資料一致性**: 每次回調都重新查詢資料確保一致性
5. **最後批次**: 不執行失敗自動重試（僅 flatten + anonymization）

---

## 效能考量（簡要）

- **並行度**: 透過 Pub/Sub 實現自然的負載分散
- **錯誤隔離**: 單一批次失敗不影響其他批次
- **資源控制**: Cloud Run 自動擴展處理高負載
- **監控**: 完整的日誌記錄和追蹤機制

---

## 總結

### 核心路由邏輯

| 流程類型 | 日期屬性 | 路由目標 | 篩選原因 |
|---------|---------|----------|------|
| 每日定時工作 | 空值 ("", "") | `/`（daily 訂閱） | `NOT attributes.start_date OR NOT attributes.end_date` |
| 範圍查詢 | 實際值 (YYYY-MM-DD) | `/get_data_range`（range 訂閱） | `attributes.start_date AND attributes.end_date` |

### 篩選器設計原理

- **credolab-sub01**：`attributes:start_date`
  - 只接收**有實際日期值**的訊息 → 路由至 `/get_data_range`
- **credolab-sub02**：`NOT attributes:start_date`
  - 只接收**沒有日期值或空值**的訊息 → 路由至 `/`

### 實作關鍵點

1. 每日定時工作需發送空字串日期屬性：`{"start_date": "", "end_date": ""}`
2. 範圍查詢需發送實際日期屬性：`{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}`
3. Pub/Sub 篩選器多以屬性存在性判斷（並搭配內容判斷），依實際訂閱設定為準

### 訊息流向總覽

```
Daily Job (route(/))→ 處理第一批 → 發空值屬性 → credolab-sub02 → / → 處理第二批 → ...
get_data_range(route(/get_data_range)) → 處理指定批 → 發實際值屬性 → credolab-sub01 → /get_data_range → 處理下一批 → ...
```


