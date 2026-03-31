# Credolab Integration Service

此專案是一個 Flask 應用程式，用於整合 VMB 資料處理與 Credolab API 呼叫。專案採用 **Service Layer 架構**，專為 Cloud Run 無人為介入的環境設計。

---
## Features
- 分批批次處理（Daily / Date Range / Recall）
- Pub/Sub 回調觸發下一批（無需人工輪詢）
- BigQuery：來源查詢 + 目的儲存 + flatten 後處理
- GCS：原始 API 回應與請求關聯資料備份
- Credolab API 整合：QPM 節流、Retry、錯誤標準化
- 結構化日誌（BigQuery + Cloud Logging）
- 失敗 API 記錄（不自動重試，留存 retry table）
- Secret Manager 管理 API Key（本地 fallback 明碼）
- 模組化 Service Layer：清晰職責分離

---
## Architecture Overview
執行流程（高階）：
1. 入口路由接收 HTTP 或 Pub/Sub 推送（每日 / 範圍 / 回調）。
2. DataFlowService 解析模式，無需預先計算總批次數。
3. BatchProcessService 載入第一批（依 batch_size 設定）→ 逐筆呼叫 Credolab API → 即時寫入 BigQuery 並備份至 GCS。
4. 若查詢結果 ≥ batch_size（表示還有更多資料）→ 發布下一批 Pub/Sub 訊息（daily_recall 或 range_recall）。
5. 若查詢結果 < batch_size（表示最後一批）→ 執行 flatten SQL（Android / iOS）→ 視需要發布匿名化通知。
6. 失敗 API 寫入失敗列表表格供後續離線處理（主流程不自動重試）。

補充：完整流程圖/細節請參考 `docs/` 目錄 drawio 與說明檔。

---
## Directory Layout 
```
Credolab/
├── main.py                      # Flask app 入口
├── blueprints/credolab_routes.py# / 與 /get_data_range 路由
├── services/
│   ├── dataflow_service.py      # 流程協調 + 模式判斷
│   └── credolab_api_service.py  # API 呼叫封裝
├── application/
│   ├── batch_process_service.py # 批次 orchestrator + 每批處理
│   └── bigquery_service.py      # BigQuery 查詢 / 寫入 / flatten
├── infrastructure/credolab_client.py # 低階 HTTP 客戶端
├── utils/
│   ├── infra_logging.py         # 結構化日誌
│   ├── pubsub_services.py       # Pub/Sub 發布工具
│   ├── gcs_services.py          # GCS 上傳
│   ├── secret_services.py       # Secret 取得
│   ├── data_processor.py        # 資料轉換
│   ├── metrics.py               # 指標記錄（預留擴充）
│   ├── helpers.py               # 通用工具
│   ├── error_handling.py        # 路由層例外處理裝飾器
│   └── request_context.py       # 跨流程共享 log 物件
├── sql/                         # 查詢與 ETL SQL
│   ├── get_vmb_data.sql
│   ├── get_vmb_data_range.sql
│   ├── flatten_data_android.sql
│   ├── flatten_data_ios.sql
│   └── failed_retry_list.sql
├── modules/config.py            # 設定單例
├── config/config.yaml           # 多環境設定（以 project id 選擇）
└── dockerfile / requirements.txt
```

---
## Tech Stack
- Python 3.9 (Cloud Run 基底映像 python:3.9-slim)
- Flask + Gunicorn
- Google Cloud：BigQuery / Storage / Pub/Sub / Secret Manager / Cloud Logging
- requests / pandas / PyYAML

---
## Prerequisites
| 類別 | 需求 |
|------|------|
| Python | 3.9.x |
| GCP 權限 | BigQuery Data Viewer / User、Storage Object Admin (或細粒度上傳權限)、Pub/Sub Publisher、Secret Accessor、Logging Writer |
| 網路 | 出站可連 Credolab API domain |
| Config | `config/config.yaml` 需含對應 project id 區塊 |

---
## Configuration
設定來源優先序：環境變數 > `config.yaml` > 預設。
`modules/config.py` 會依目前執行環境的 GCP project id 自動選擇對應段落。

建議環境變數（例）：
```
CREDOLAB_BATCH_SIZE=500
CREDOLAB_QPM_LIMIT=240
CREDOLAB_GCS_BUCKET=your-bucket
LOG_SINK_DATASET=RAW_LOG_DATASET
```
Credolab API Key 取得順序：
1. Secret Manager (`credolab_secret_version_name`)
2. 環境變數 `CREDOLAB_DEFAULT_API_KEY`
3. config.yaml fallback（僅本地測試）


## API Endpoints
| Method | Path | 用途 | Body 例 | 備註 |
|--------|------|------|---------|------|
| POST | / | 觸發 daily 第一批 | `{}` 或 `{ "device_type": "android" }` | 自動使用 partition_date（通常為昨日） |
| POST | /get_data_range | 觸發範圍處理起始 | `{ "start_date": "2024-10-01", "end_date": "2024-10-03", "device_type": "ios" }` | |
| POST | / 或 /get_data_range | 回調批次 (Pub/Sub) | Pub/Sub push JSON | 由 attributes 判別 daily/range |

錯誤格式（例）：
```json
{ "error": { "code": "INVALID_DATE", "message": "start_date must be <= end_date" } }
```

---
## Batch & Recall Strategy
| 模式 | 入口 | message_type | 下一批發布條件 | 回調路由 |
|------|------|--------------|---------------|-----------|
| Daily | POST / | daily_recall | 查詢結果 ≥ batch_size | / |
| Range | POST /get_data_range | range_recall | 查詢結果 ≥ batch_size | /get_data_range |

**批次終止判定**：當 SQL 查詢結果 < 50 筆時，表示最後一批，進入 flatten 與 anonymization 流程。

GCS 檔名格式：`{blob_path}/{YYYY-MM-DD}_{device_os}_{reference_id}.json`
失敗 API：寫入 `CREDOLAB_FAILED_RETRY_LIST`（不自動重試）。

---
## Data Flow
流程：依 SQL（`sql/get_vmb_data*.sql`）查詢 → 檢查結果大小 → 逐筆 API → 寫入 BigQuery（依 OS 分表）→ 備份原始 JSON 至 GCS。
後續判斷：
  - 結果 ≥ batch_size：發布下一批 recall 訊息
  - 結果 < batch_size：執行 flatten SQL（Android / iOS）→ 視需要發布 anonymization 通知
Flatten SQL：`flatten_data_android.sql` / `flatten_data_ios.sql`（實際表名以 config 為準）。

---
## Testing（建議）
- 單元：data parsing / 批次切分邏輯
- 整合：模擬 Pub/Sub recall 與最後一批 flatten/anonymization
- 合約：Credolab API 回應 schema 驗證

---
## Error Handling
- 路由層裝飾器：統一 try/except → 標準 JSON 錯誤輸出
- Credolab API：429 / 5xx 自動重試（限次數）
- 資料驗證錯誤：立即回 400 並不進入流程
- 外部服務錯誤：記錄並納入失敗列表（不阻塞其他記錄）

---
## Logging & Observability
- `utils/infra_logging.Logging`：FLOW_LOG（僅完成/錯誤）與 API_LOG；非 Info 嚴重度寫入 Cloud Logging 結構化 log
- BigQuery：可作稽核與報表；表名/資料集以 config 為準
- Cloud Logging：即時追蹤
- 指標（`utils/metrics.py`）：可擴充（API calls、BQ writes 等）
註：完成訊息（例如 "all job completed"）在流程終點寫入一次（依實際路徑其一）。

---
## Security & Secrets
- API Key：透過 Secret Manager 存取；本地可用環境變數或 config fallback
- 無使用者資料寫入 Log（只寫 reference_id / cuid，如規則允許）

---
## Appendix (SQL 摘要)
| 檔案 | 用途 |
|------|------|
| get_vmb_data.sql | 取得 daily 起始資料 |
| get_vmb_data_range.sql | 取得日期範圍資料 |
| flatten_data_android.sql | Android 聚合與扁平化 |
| flatten_data_ios.sql | iOS 聚合與扁平化 |
| failed_retry_list.sql | 失敗 API 記錄查詢/建立 |

---
## License / Usage
內部專案（Internal Use Only）。
