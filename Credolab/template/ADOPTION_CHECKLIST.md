# 落地前檢查清單（基於現有程式）

請逐項確認：

設定與資源
- [ ] `config/config.yaml` 已新增對應 `project_id` 的環境段落
- [ ] BigQuery 資料集與表已建立，並與 SQL 檔案中名稱一致
- [ ] GCS bucket 與 `gcs.blob_path` 可用
- [ ] Pub/Sub topic：`credolab_topic` 與 `anonymization`（或依 `config` 更名）已存在
- [ ] 部署環境具備 ADC 與對應 GCP 權限（BQ / GCS / PubSub / Logging）

程式與資料
- [ ] 僅修改 `sql/` 與外部 API client/service（其餘程式未動）
- [ ] `get_vmb_data*.sql` 回傳欄位包含：`cuid`、`reference_id`、`device_os`、`serial_number`
- [ ] 外部 API 回傳可被 `prepare_raw_data_for_bq` 正確序列化

流程驗證
- [ ] daily：POST `/` 可啟動首批並發布 recall
- [ ] range：透過 `process(start_date, end_date)` 啟動，後續 recall 正常
- [ ] 最終：最後一批完成後執行 `flatten_data_*.sql`，並發布匿名化通知
