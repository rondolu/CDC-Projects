# Credolab 日誌系統使用指南

## 概述

本系統提供統一的日誌模組 `utils/infra_logging.py`（唯一來源）。日誌機制符合客戶端提供的 BigQuery schema：

1. 流程日誌 (`LOG_DATASET.FLOW_LOG`) - 記錄業務流程執行狀態
2. API 日誌 (`API_DATASET.API_LOG`) - 記錄 API 呼叫詳細資訊

## Table Schema

### LOG_DATASET.FLOW_LOG

| 欄位名稱 | 類型 | 說明 |
|---------|------|------|
| DATETIME | STRING | 記錄時間 (YYYY-MM-DD HH:MM:SS) |
| FLOW_ID | STRING | 流程識別碼或 UUID_Request |
| FLOW_NAME | STRING | 流程名稱或 API Type |
| TASK_CODE | STRING | 任務代碼 (START/END/ERROR/TASK) |
| TASK_NAME | STRING | 任務名稱 |
| STATUS | STRING | 狀態 (Success/Error) |
| MESSAGE | STRING | 詳細訊息或錯誤訊息 |
| SEVERITY | STRING | 嚴重程度 (Info/Debug/Error/Notice) |

### API_DATASET.API_LOG

| 欄位名稱 | 類型 | 說明 |
|---------|------|------|
| UUID_Request | STRING | 請求級唯一識別碼（`Logging.log_uuid`，非單筆 reference_id） |
| API_Type | STRING | API 類型 (CREDOLAB) |
| API_Name | STRING | API 名稱和呼叫參數 |
| Start_Time | DATETIME | API 呼叫開始時間 |
| End_Time | DATETIME | API 呼叫結束時間 |
| Status_Code | STRING | HTTP 狀態碼 |
| Status_Detail | STRING | 狀態詳細資訊或錯誤訊息 |
| Retry | INTEGER | 重試次數 |

## 使用方式

### 1. 推薦：以 Logging 記錄流程日誌（只記錄完成/錯誤）

```python
from utils.infra_logging import Logging
import uuid

# 初始化統一日誌（建議 flow_code: "<FLOW_ID>_<FLOW_NAME>")
flow_code = "E05_credolab"
log_uuid = str(uuid.uuid4())
log = Logging(mission_name="init", log_uuid=log_uuid, flow_code=flow_code)

# 記錄流程完成或錯誤（不記錄開始；開始訊息由裝飾器省略）
log.flowlog(
    "data_processing",
    "TASK",
    "Flow completed: {\"processed_count\": 100}",
    status="Success",
    severity="Info",
)

# 記錄一般任務
log.flowlog("validate_data", "01", "Data validation completed", status="Success", severity="Info")
```

### 2. 推薦：以 Logging 記錄 API 日誌

```python
from datetime import datetime
from utils.infra_logging import Logging
import uuid

log = Logging(mission_name="api", log_uuid=str(uuid.uuid4()), flow_code="E05_credolab")

start_time = datetime.now()
end_time = datetime.now()
log.apilog(
    uuid_request=log.log_uuid,   # 請求級 UUID，非 reference_id
    api_type="credolab_api",
    api_name="CREDOLAB",        # 也可由裝飾器自動帶入函式名稱
    start_time=start_time,
    end_time=end_time,
    status_code="200",
    status_detail="Success",
    retry=0,
)
```

### 3. 裝飾器使用（只記錄完成/錯誤，不記錄開始）

```python
from utils.infra_logging import Logging
import uuid

class MyService:
    def __init__(self):
        self.log = Logging(mission_name="service", log_uuid=str(uuid.uuid4()), flow_code="E05_credolab")

    @Logging.logtobq(task_code="01")
    def process(self):
        # 業務邏輯；回傳可用 "DEBUG:"/"NOTICE:" 影響嚴重度
        return "NOTICE: first batch done"

    @Logging.logapicall(api_type="credolab_api")
    def call_api(self):
        class R: status_code = 200
        return R()
```

### 4. 相容性說明

請全面改用 `utils.infra_logging.Logging` 與其裝飾器；舊的 `utils/logging.py` 已不再使用。

## 配置設定

在 `config/config.yaml` 中配置日誌相關設定：

```yaml
bigquery:
  log_dataset: "LOG_DATASET"
  api_dataset: "API_DATASET"
  flow_log_table: "FLOW_LOG"
  api_log_table: "API_LOG"
```

## 重要特性

### 1. 雙重記錄（BigQuery + Cloud Logging）

- BigQuery：資料分析與查詢
- Cloud Logging：即時監控與除錯（僅在非 Info 嚴重度時寫入結構化 log）

### 2. 錯誤處理

- 日誌寫入失敗不會中斷主要業務流程
- 失敗的日誌會記錄到 Cloud Logging 中

### 3. 重試追蹤

- API 日誌自動追蹤重試次數
- 支援指數退避重試機制

### 4. 速率與重試（由 API client 負責）

- QPM（每分鐘請求數）與重試策略由 CredolabAPIClient 實作
- 日誌層僅記錄呼叫次數與結果，不負責重試

## 實際使用範例

### Credolab API 服務中的使用

建議使用 `self.log.apilog()` 或 `@Logging.logapicall(api_type=...)`。

## 監控查詢範例

### 查詢流程執行統計

```sql
SELECT 
    FLOW_NAME,
    STATUS,
    COUNT(*) as count,
    DATE(PARSE_DATETIME('%Y-%m-%d %H:%M:%S', DATETIME)) as date
FROM `LOG_DATASET.FLOW_LOG`
WHERE DATE(PARSE_DATETIME('%Y-%m-%d %H:%M:%S', DATETIME)) = CURRENT_DATE()
GROUP BY FLOW_NAME, STATUS, date
ORDER BY date DESC, count DESC
```

### 查詢 API 呼叫統計

```sql
SELECT 
    API_Type,
    Status_Code,
    COUNT(*) as call_count,
    AVG(DATETIME_DIFF(End_Time, Start_Time, SECOND)) as avg_duration_seconds,
    SUM(Retry) as total_retries,
    DATE(Start_Time) as date
FROM `API_DATASET.API_LOG`
WHERE DATE(Start_Time) = CURRENT_DATE()
GROUP BY API_Type, Status_Code, date
ORDER BY date DESC, call_count DESC
```

### 查詢重試統計

```sql
SELECT 
    API_Type,
    Status_Code,
    Retry,
    COUNT(*) as count
FROM `API_DATASET.API_LOG`
WHERE DATE(Start_Time) = CURRENT_DATE()
  AND Retry > 0
GROUP BY API_Type, Status_Code, Retry
ORDER BY Retry DESC, count DESC
```

## 注意事項 / 補充

1. **時區處理**: 所有時間都使用 UTC
2. **資料大小**: MESSAGE 和 Status_Detail 欄位請控制在合理長度內
3. **效能**: 日誌記錄是異步的，不會阻塞主要業務流程
4. **統一格式**: 系統只支援新的 schema 格式，不再向後相容
5. **配置**: 可通過環境變數覆蓋配置文件中的設定
6. **Severity 規則**: 裝飾器回傳字串前綴 `NOTICE:` → Notice；`DEBUG:` → Debug；HTTP 狀態碼 >= 400 自動記為 Error；其餘預設 Info

7. **完成訊息寫入點（"all job completed"）**：現行程式會在下列終點路徑各寫入一次 Flow Log 完成訊息（實際觸發其一）：
    - 無資料情境（完成 flatten + anonymization 後）
    - 單批次情境（完成 flatten + anonymization 後）
    - 多批次的最後一批（完成 flatten + anonymization 後）

## 故障排除

如果日誌記錄出現問題：

1. 檢查 BigQuery 權限
2. 確認 dataset 和 table 是否存在
3. 查看 Cloud Logging 中的錯誤訊息
4. 確認配置文件設定正確
