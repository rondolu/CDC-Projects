# 開發與驗證流程（以現有程式為準）

此流程僅涵蓋與程式一致的必要步驟，不包含環境建置細節。

1) 設定與環境
- 於 `config/config.yaml` 新增或調整與目標 `project_id` 相符之環境段落。
- 確認 BigQuery 資料集與表存在，或與 SQL 檔案中使用之名稱一致。
- 確認 GCS bucket 與 `gcs.blob_path` 可用。
- 確認 Pub/Sub topic（`pubsub.credolab_topic` 與 `pubsub.anonymization_topic`）存在。

2) 僅修改 SQL 與 API 發查端點
- 按 `template/SQL_CUSTOMIZATION.md` 更新 `sql/` 內檔案（包含 dataset/table 名）。
- 按 `template/CUSTOMIZATION_GUIDE.md` 更新 `infrastructure/credolab_client.py` 與 `services/credolab_api_service.py` 以對接新 API。

3) 手動驗證邏輯
- daily 啟動：向 POST `/` 發送 JSON（可含 `device_type`）。
- range 啟動：由 `DataFlowService.process(start_date, end_date, device_type)` 觸發，後續 recall 由 Pub/Sub 自動驅動。
- 檢視批次：
  - 成功：GCS 路徑（`config.gcs_bucket_name` + `config.gcs_blob_path`）、BQ RAW 表（依 `device_os` 分 Android/iOS）。
  - 失敗：`CREDOLAB_FAILED_RETRY_LIST`（表名見 `config` 組合屬性）。
  - 最終：最後一批完成後執行 `flatten_data_*.sql`，成功時發送匿名化通知（Pub/Sub）。

4) 日誌與指標
- Flow/API Log：寫入 BigQuery（資料集與表名見 `modules/config.py`），同時輸出 Cloud Logging。
- 指標列印：`utils/metrics.py` 於分鐘切換時輸出一行摘要至 stdout。

5) 風險與驗證建議
- SQL 內 dataset/table 名稱需與實際環境一致。
- `_load_vmb_data()` 期望欄位請符合文件敘述，否則下游處理與上傳會失敗。
- 外部 API 回應格式應能被 `prepare_raw_data_for_bq` 序列化，否則 BQ 寫入會失敗。

---

## 你要改什麼（流程對應）

- 僅改 `sql/` 與 `infrastructure/credolab_client.py`、`services/credolab_api_service.py`，其餘（Recall、批次協作、GCS/BQ、Logging、Pub/Sub）不動。
