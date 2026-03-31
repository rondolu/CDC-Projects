# SQL 檔案與參數對照（依據現有程式碼與 SQL）

檔案位置：`sql/`

- `get_vmb_data.sql`（daily 模式載入）
  - 現有 SQL 無需傳入參數；內部以 `CURRENT_DATE()` 與固定條件取近 7 天資料，並排除已處理 `reference_id`。
  - 由 `BatchProcessService._load_vmb_data()` 在無 `start_date/end_date` 時選用本檔。

- `get_vmb_data_range.sql`（range 模式載入）
  - 需要參數：`@start_date`、`@end_date`（由 `BatchProcessService._load_vmb_data` 設定並透過 `BigQueryService.execute_query` 傳入）。
  - 排除已處理 `reference_id` 邏輯同上。

- `flatten_data_android.sql`、`flatten_data_ios.sql`（最後一批或單批完成後執行）
  - 需要參數：`@partition_date`（由 `BatchProcessService` 以 `BigQueryService.run_sql_file(sql_name, {"partition_date": partition_date})` 執行）。
  - 輸入來源 RAW 表：`RAW_EDEP_DATASET.CREDOLAB_DATA_ANDROID` / `RAW_EDEP_DATASET.CREDOLAB_DATA_iOS`
  - 目的 TRANS 表：`TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_ANDROID` / `TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_iOS`

- `failed_retry_list.sql`
  - 目前程式未直接呼叫此檔，內容示範以 `{dataset}.{table}` 作為佔位。若要使用，請自行以適用的 dataset/table 名稱取代並以 `BigQueryService.execute_query` 執行。

重要說明：
- 目前 SQL 內的 dataset/table 名稱（如 `RAW_EDEP_DATASET`）為純文字，非由 `config.yaml` 自動替換。如需改名，需直接修改 SQL 檔案。

最小欄位需求（供程式使用）：
- `get_vmb_data*.sql` 回傳每列至少包含：`cuid`、`reference_id`、`device_os`、`serial_number`。

---

## 你需要修改什麼（逐檔提示）

- `get_vmb_data.sql`
  - 將 `RAW_VMB_DATASET`、`RAW_HES_DATASET` 等資料集名稱替換為你的環境名稱。
  - 確認 `reference_id` 未被已有 RAW EDEP Android/iOS 表收錄的去重條件適用你的環境。

- `get_vmb_data_range.sql`
  - 同上替換資料集名稱，保留 `@start_date`、`@end_date` 參數位。
  - 如要處理整段資料，請移除檔尾的 `limit 1`。

- `flatten_data_android.sql` / `flatten_data_ios.sql`
  - 替換 `RAW_EDEP_DATASET` 與 `TRANS_EDEP_DATASET` 兩類資料集名稱。
  - 保留 `@partition_date` 參數位（由程式傳入），確保 `reference_id` / `reference_number` 關聯條件符合你的 RAW 表欄位命名。
