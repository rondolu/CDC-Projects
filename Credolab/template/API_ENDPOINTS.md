# 對外 API 規格與 Recall 訊息（依據現有程式碼）

路由檔：`blueprints/credolab_routes.py`

- POST `/`
  - 說明：啟動 daily 流程或處理 daily recall（依輸入是否為 Pub/Sub push 格式決定）。
  - 進入點：`DataFlowService.handle_daily_request(data)`
  - Pub/Sub push 成功處理後回傳 204（程式會先以 `utils.error_handling.is_pubsub_request` 判斷格式）。

- POST `/get_data_range`
  - 說明：處理 range recall（由 range 模式的回呼訊息觸發）。
  - 進入點：`DataFlowService.handle_date_range_request(data)`
  - Pub/Sub push 成功處理後回傳 204。

服務層：`services/dataflow_service.py`
- `process(start_date=None, end_date=None, device_type=None)`
  - 無日期參數 → daily 模式；有任一日期參數 → range 模式。
  - 回傳：第一批處理結果與後續 recall 發布狀態（dict）。
- `process_recall_batch(message_type, batch_number, ...)`
  - `message_type` 為 `daily_recall` 或 `range_recall`。
  - 依 message_type 建構回呼並繼續批次處理。

回呼訊息格式（由 `utils.pubsub_services.PubSubService` 發布）：
- daily recall（會送往 `/`）：
  - message.data（JSON）：
    - `{"message_type":"daily_recall","processing_params":{"batch_number":<next>,"source":"daily_job"}}`
  - attributes：包含 `start_date:""`、`end_date:""`（空字串）

- range recall（會送往 `/get_data_range`）：
  - message.data（JSON）：
    - `{"message_type":"range_recall","processing_params":{"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD","batch_number":<next>,"source":"get_data_range"}}`
  - attributes：包含 `start_date`、`end_date`（具值）

注意：回應格式由各 service 回傳的 dict 與 `handle_route_exceptions` 統一處理；若為 Pub/Sub push 且成功，路由會回傳 204 空內容。

---

## 你要改什麼（路由/Recall 版）

- 如需新增對外 API 路由：
  - 在 `blueprints/credolab_routes.py` 新增對應的 `@credolab_bp.route(...)`
  - 建議保留裝飾器：`@Logging.logtobq(task_code="..")` 與 `@handle_route_exceptions`
  - 在 handler 內呼叫對應的 Service 方法（比照 `DataFlowService.handle_daily_request`）

- Recall 訊息格式（保持不變）：
  - `utils/pubsub_services.PubSubService` 的 `publish_daily_recall_message` 與 `publish_range_recall_message` 構造的 `message.data` 與 attributes 為現有解析依據
  - 若修改 payload 形狀，需同步調整 `services/dataflow_service.py` 中的解析與處理邏輯
