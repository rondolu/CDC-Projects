# Credolab 架構概觀（精簡版，2025-10）

本文件以精要方式說明現行系統架構，專注於實作現況，避免過度推演與假設。

## 分層與資料流

1) 路由層（`blueprints/credolab_routes.py`）
- `POST /`（daily 入口與 daily_recall 回調）
- `POST /get_data_range`（range 入口與 range_recall 回調）

2) 服務編排層（`services/dataflow_service.py`）
- `process()`：統一入口，決定 daily 或 range 流程並啟動第一批
- `process_recall_batch()`：處理回調批次
- `handle_*_request()`：路由層使用的封裝方法

3) 批次處理層（`application/batch_process_service.py`）
- `_process_batch_generic()`：通用框架（查詢 → 批次處理）
- `_initiate_batch_processing()`：第一批處理與回調設定
- `_orchestrate_batch_processing()`：後續批次協調
- `_process_batch_records()`：逐筆執行 API → 成功即時 GCS + BQ；失敗寫入 Failed 表

4) 外部整合與基礎設施
- `infrastructure/credolab_client.py`：Credolab API 客戶端（認證、速率限制、重試）
- `application/bigquery_service.py`：BigQuery 查詢/寫入
- `utils/gcs_services.py`：GCS 批次上傳
- `utils/pubsub_services.py`：回調訊息發布（daily/range）、anonymization 通知
- `utils/infra_logging.py`：FLOW_LOG / API_LOG 與 Cloud Logging

## 關鍵行為（現況）

- 逐筆成功即時寫入（GCS + RAW BQ），不等待整批
- 批次完成後才發布下一批回調（不做跨批並行）
- 失敗寫入 Failed Retry 表，不在流程尾自動重試
- 最後一批完成後執行 flatten（android/ios），並發布 anonymization

## 設定來源

- 主要參數（專案/資料集/表/Topic 等）皆由 `config/config.yaml` 與環境變數提供（細節見根目錄 `README.md`）

## 日誌

- `utils/infra_logging.Logging`
  - Flow Log：只記錄完成/錯誤（`logtobq` 裝飾器）
  - API Log：`apilog` 或 `logapicall` 裝飾器
  - 亦寫入 Cloud Logging（非 Info 嚴重度才寫入結構化）

---

本文件僅保留現況摘要；進一步的最佳化與延伸討論請改至 PR/設計提案中進行，以免文件與程式行為脫節。
