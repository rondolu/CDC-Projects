# Credolab Data Flow 說明

此文件提供決策節點語意與資料責任分層。

---
## 1. 流程總覽階段 (Stages)
1. Entry & Routing
2. Context Build & Generic Batch Framework
3. Data Load & Batch Dimensioning
4. First Batch vs Subsequent Batches 控制流
5. Record-Level Processing Loop
6. 成功 / 失敗分流與持久化
7. 批次遞進 (Recall) 與最終收斂
8. 後處理（Flatten + Anonymization）

---
## 2. 主要元件職責 (Components)
| 元件 | 角色 | 關鍵方法 |
|------|------|----------|
| DataFlowService | HTTP 入口協調 | `handle_daily_request`, `handle_date_range_request`, `process` |
| BatchProcessService | 核心批次框架 | `_process_batch_generic`, `_initiate_batch_processing`, `_orchestrate_batch_processing` |
| BigQueryService | 查詢 / 寫入 BQ | `execute_query`, `insert_rows`, `insert_failed_record`, `run_sql_file` |
| CredolabAPIService | 呼叫 Credolab API | `get_credolab_insights` |
| GCSService | 原始資料備援 | `upload_to_gcs` |
| PubSubService | 觸發後續批次 & 匿名化 | `publish_*_recall_message`, `publish_anonymization` |

---
## 3. 關鍵決策節點 (Decision Semantics)
| 節點 | 判斷條件 | 影響 |
|------|----------|------|
| Range? | 是否傳入 start_date / end_date | 決定 SQL 與回調類型 |
| First batch? | batch_number == 1 | 決定是否走 `_initiate_batch_processing` 並立即回應 processing |
| HTTP 2xx? | API 回傳狀態碼前綴為 2 | 成功：儲存 + 上傳；失敗：寫入失敗表 |
| More batches? | `len(data) >= batch_size` (batch_size=50) | 是：publish recall；否：進入 last batch 判斷 |
| Last batch? | `len(data) < batch_size` (batch_size=50) | 是：執行 flatten + anonymization；否：回應 processing |

---
## 4. 資料流 (Data Flow)
1. SQL 載入：
   - Range 模式：`get_vmb_data_range.sql`。
   - Daily 模式：`get_vmb_data.sql`（使用 `partition_date = UTC today`）。
2. 單筆成功（Success Path）：
   - 上傳原始 JSON → GCS（檔名：`{YYYY-MM-DD}_{device_os}_{reference_id}.json`）
   - 組裝整合資料寫入 RAW 表：`RAW_EDEP_DATASET.CREDOLAB_DATA_ANDROID|CREDOLAB_DATA_iOS`
3. 單筆失敗（Failure Path）：
   - API 非 2xx：`status_code` 即實際 HTTP 狀態碼
   - 其他例外：`status_code = 'failed'`
   - Unified：`insert_failed_record` 寫入重試表
4. 最後批次或單批：
   - 執行 flatten → 產出/補 `TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_ANDROID|TMP_CREDOLAB_DATA_iOS`
   - 發布 anonymization topic（best-effort，失敗不阻斷）

---
## 5. 錯誤與恢復 (Error Handling & Recovery)
| 類型 | 處理策略 | 是否阻斷主流程 |
|------|----------|----------------|
| Credolab API 非 2xx | 記錄 + 進入失敗表 | 否 |
| DataValidationError | 記錄失敗表 (failed) | 否（僅影響該筆） |
| GCS 上傳失敗 | raise → 記錄失敗表 | 不中斷其他記錄 |
| BQ 插入失敗 | raise → 記錄失敗表 | 不中斷其他記錄 |
| Flatten SQL 失敗 | Warning 日誌 | 否 |
| Anonymization 發布失敗 | Warning 日誌 | 否 |

---
## 6. 回應語意 (API Responses)
| 階段 | status | 說明 |
|------|--------|------|
| 第一批完成 (仍有後續) | processing | 已啟動 recall 排程後續批次 |
| 單批全量 | completed | 直接進入 flatten + anonymization |
| 最後一批完成 | completed | 提供最終統計與（可選）匿名化消息 ID |

---
## 7. 指標與可觀察性 (Observability)
| 指標 | 來源 |
|------|------|
| success_count / error_count | `_process_batch_records` 彙總 |
| processed_references | 累積 reference_id | 
| flatten 執行狀態 | console + `_logger.log_text` |
| anonymization 發布 ID | `_publish_anonymization_notification` 回傳 |

---
## 8. 可改進建議 (Potential Enhancements)
1. 加入失敗重試專屬 API 或自動排程（現僅寫入失敗紀錄）。
2. 增加批次級別 metrics：耗時、平均 API RTT、失敗率。
3. 於失敗表新增 retry_flag / last_retry_timestamp 欄位。
4. flatten 失敗時追加警示通知（Email / Slack）。
5. 匿名化發布失敗改為可選重試（目前直接忽略）。

---
## 9. 流程摘要 (Narrative Summary)
系統接收 Daily 或 Range 請求，建立帶回呼的批次上下文後進入通用批次框架載入原始 VMB 資料，切批後第一批立即回應 processing。每筆資料同步呼叫 Credolab API，成功即寫入標準化表與備份原始 JSON；失敗則以狀態碼或 'failed' 登錄於失敗重試表。所有批次透過 Pub/Sub recall 串接，最終批次觸發雙平台 flatten SQL 與匿名化發布，流程以 completed 回應收束並輸出統計。整體設計確保即時回應、失敗隔離與後處理鬆耦合。

---
## 10. 附註 (Notes)
- Flatten / Anonymization 屬非阻斷後處理：即便失敗亦不回滾主流程。
- 記錄層級錯誤不影響批次迴圈持續進行。
- 失敗表為後續可能的 retry workflow 預留基礎。

---
(Generated: Enhanced documentation based on current codebase state)
