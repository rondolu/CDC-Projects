-- 查詢 CREDOLAB_FAILED_RETRY_LIST 中待重試的失敗紀錄
-- 此查詢會取得所有非成功狀態的紀錄，並且避免重複處理同一個 reference_id
-- api_status 可能的值：
--   - 成功狀態碼：200, 201, 202, 204 等 (會被排除)
--   - 錯誤狀態碼：400, 401, 403, 404, 500, 502, 503, 504 等 (會被包含)
--   - 其他錯誤：'failed', 'unknown' 等 (會被包含)

WITH latest_status AS (
  SELECT
    uuid,
    cuid,
    reference_id,
    series_number,
    device_os,
    api_payload_message,
    api_status,
    BQ_UPDATED_TIME,
    PARTITION_DATE,
    ROW_NUMBER() OVER (
      PARTITION BY reference_id
      ORDER BY BQ_UPDATED_TIME DESC
    ) AS rn
  FROM `{dataset}.{table}`
  WHERE PARTITION_DATE >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
)
SELECT
  uuid,
  cuid,
  reference_id,
  series_number,
  device_os,
  api_payload_message,
  api_status,
  BQ_UPDATED_TIME,
  PARTITION_DATE
FROM latest_status
WHERE rn = 1
  AND NOT (api_status LIKE '2%' OR api_status = 'success')   -- 排除所有 2xx 狀態碼與 'success' 記錄
ORDER BY BQ_UPDATED_TIME ASC
