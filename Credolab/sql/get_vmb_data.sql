-- 取得 VMB 資料並與 HES 系統結合取得申貸編號，作為Credolab API 發查清單
-- 排除已經處理過的 reference_id

SELECT DISTINCT 
    m.cuid AS cuid, 
    m.reference_id AS reference_id, 
    m.device_os AS device_os, 
    m.created_timestamp AS created_timestamp, 
    ap.SERIAL_NUMBER AS serial_number, 
    m.PARTITION_DATE AS partition_date 
FROM RAW_VMB_DATASET.CREDOLAB_DATA m 
LEFT JOIN (
    SELECT * 
    FROM RAW_HES_DATASET.CUSTOMER
    QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY PARTITION_DATE DESC) = 1
) c ON c.cuid = m.cuid 
LEFT JOIN (
    SELECT * 
    FROM RAW_HES_DATASET.APPLICATION 
    QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id, SERIAL_NUMBER ORDER BY PARTITION_DATE DESC) = 1
) ap ON c.id = ap.customer_id AND DATE(ap.CREATED_AT) = DATE(m.created_timestamp) 
WHERE m.cuid IS NOT NULL 
-- AND m.partition_date = DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY) 
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
AND NOT EXISTS (
-- 排除在失敗重試清單（當天partition_date）的 reference_id
SELECT 1
FROM `RAW_EDEP_DATASET.CREDOLAB_FAILED_RETRY_LIST` fr
WHERE fr.reference_id = m.reference_id
    AND fr.PARTITION_DATE = @partition_date
)
QUALIFY ROW_NUMBER() OVER (PARTITION BY m.reference_id ORDER BY m.PARTITION_DATE DESC) = 1 
ORDER BY m.reference_id, m.cuid
LIMIT 50
