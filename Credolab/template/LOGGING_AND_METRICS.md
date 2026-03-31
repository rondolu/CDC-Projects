# 日誌與指標（依據現有實作）

- Cloud Logging 與 BQ Flow/API Log
  - 實作：`utils/infra_logging.py` 提供 `Logging` 類別與裝飾器 `Logging.logtobq` / `Logging.logapicall`。
  - Flow Log 寫入表：`config.bq_log_dataset`.`config.bq_flow_log_table`
  - API Log 寫入表：`config.bq_api_dataset`.`config.bq_api_log_table`
  - 路由與部分服務已加上裝飾器，回傳（含錯誤）皆會紀錄。

- 每分鐘指標列印
  - 實作：`utils/metrics.py`，目前僅列印至 stdout（不寫回後端）。
  - 指標涵蓋：Credolab API 呼叫次數、BQ 寫入操作次數。

- 錯誤處理
  - 路由層：`utils/error_handling.py` 的 `handle_route_exceptions` 將應用常見錯誤到統一 JSON 回應。
  - 服務層：`application/batch_process_service.py` 的 `_handle_operation_error` 對 GCP、外部 API、資料驗證與未知錯誤做分類處理。

---

## 你要改什麼（通常不需要改）

- 預設不需修改 Logging/metrics 程式；如需調整寫入目的表，請改 `config.yaml` 的：
  - `bigquery.log_dataset`、`bigquery.api_dataset`、`bigquery.flow_log_table`、`bigquery.api_log_table`
- 若要關閉或改動每分鐘指標列印行為，請調整 `utils/metrics.py`（僅列印，不影響主流程）。
