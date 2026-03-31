# 設定鍵對照與讀取（依據 `modules/config.py` 與 `config/config.yaml`）

- Active 環境選擇：
  - 程式於 `Configuration._select_active_environment()` 透過 ADC 取得 `project_id`，使用其對應的 YAML 區塊做為 active 環境。
  - YAML 範例環境鍵：`vn-loancloudmvp-data`、`ovs-lx-vdo-01-ut-6869fc`、`ovs-lx-vdo-01-uat-d545f3`、`ovs-lx-vdo-01-prod-d27767`。

- 主要設定屬性（程式實際使用）：
  - GCP/Project
    - `gcp.project_id`（必須在環境段落中設定）
  - BigQuery（部分屬性會組合 project_id 與 dataset/table）：
    - `bigquery.raw_edep_dataset`、`bigquery.log_dataset`、`bigquery.api_dataset`
    - `bigquery.credolab_android_table`、`bigquery.credolab_ios_table`、`bigquery.credolab_failed_retry_table`
    - 程式屬性：`bq_credolab_table_android`、`bq_credolab_table_ios`、`bq_credolab_failed_retry_table`、`bq_log_dataset`、`bq_api_dataset`、`bq_flow_log_table`、`bq_api_log_table`
  - GCS
    - `gcs.bucket_name`、`gcs.blob_path`
  - Pub/Sub
    - `pubsub.project_id`、`pubsub.credolab_topic`、`pubsub.anonymization_topic`、`pubsub.batch_topic`
  - 外部 API（Credolab 為例）
    - `credolab_api.base_url`、`credolab_api.timeout`、`credolab_api.max_retries`、`credolab_api.batch_size`、`credolab_api.qpm_limit`、`credolab_api.api_codes`
    - `credolab_api.secret_version_name`（若需透過 Secret Manager 取得 API Key）
    - `credolab_api.proxies`（如需 HTTP 代理）

- 讀取優先順序：環境變數 > YAML > 預設值（見 `Configuration._get`）。

- 重要行為：
  - BigQuery、GCS、Pub/Sub、Cloud Logging 等 client 多依賴 ADC；請確認部署環境具備相應權限。

---

## 你要改什麼（config.yaml 版）

- 在目標 `project_id` 區塊（成為 active 環境）更新：
  - `gcp.project_id`：必填，決定 active 環境鍵
  - `gcs.bucket_name`、`gcs.blob_path`：影響 GCS 上傳路徑
  - `pubsub.credolab_topic`、`pubsub.anonymization_topic`：影響 Recall 與匿名化發布的 topic 名稱
  - `bigquery.raw_edep_dataset`、`bigquery.log_dataset`、`bigquery.api_dataset` 及相關表名鍵：影響 BQ 讀寫目的表
  - `credolab_api.base_url`、`timeout`、`max_retries`、`batch_size`、`qpm_limit`、`api_codes`、`secret_version_name`、`proxies`：影響外部 API 呼叫行為

- 若要使用環境變數覆蓋：鍵名以大寫與底線分隔，例如 `CREDOLAB_API_BASE_URL` 覆蓋 `credolab_api.base_url`
