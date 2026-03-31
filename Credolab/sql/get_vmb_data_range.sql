-- 取得指定日期範圍的 VMB 資料進行 Credolab API 查詢
-- 此查詢用於批次補檔，處理指定日期範圍內的資料
-- 排除已經處理過的 reference_id
-- 優化版本：使用 NOT EXISTS 替代 NOT IN，避免全表掃描

SELECT
    m.cuid         AS cuid,
    m.reference_id AS reference_id,
    m.device_os    AS device_os,
    m.created_timestamp AS created_timestamp,
    ap.SERIAL_NUMBER AS serial_number
FROM RAW_VMB_DATASET.CREDOLAB_DATA m
LEFT JOIN (
    SELECT *
    FROM `RAW_HES_DATASET.CUSTOMER`
    QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY PARTITION_DATE DESC) = 1
) c ON c.cuid = m.cuid
LEFT JOIN (
    SELECT *
    FROM `TRANS_HES_DATASET.APPLICATION`
    QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id, SERIAL_NUMBER ORDER BY PARTITION_DATE DESC) = 1
) ap ON c.id = ap.customer_id AND DATE(ap.CREATED_AT) = DATE(m.created_timestamp)
WHERE DATE(m.created_timestamp) BETWEEN @start_date AND @end_date
  AND m.reference_id IS NOT NULL
  AND NOT EXISTS (
    -- 排除已經在 Android 表中的 reference_id
    SELECT 1 
    FROM `RAW_EDEP_DATASET.CREDOLAB_DATA_ANDROID` a
    WHERE a.reference_id = m.reference_id
  )
  AND NOT EXISTS (
    -- 排除已經在 iOS 表中的 reference_id
    SELECT 1 
    FROM `RAW_EDEP_DATASET.CREDOLAB_DATA_iOS` i
    WHERE i.reference_id = m.reference_id
  )
ORDER BY m.created_timestamp
LIMIT 50