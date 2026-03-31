SELECT
  c.CUID AS cuid,
  ap.SERIAL_NUMBER AS serial_number,
  ap.CREATED_AT AS created_at,
  c.CURRENT_DETAILED_ADDRESS AS current_detailed_address,
  c.PERMANENT_DETAILED_ADDRESS AS permanent_detailed_address,
  ay.tax_code AS tax_code,
  ay.company_name AS company_name,
  ay.LONGITUDE AS longitude,
  ay.LATITUDE AS latitude,
  ap.partition_date AS partition_date
FROM `RAW_HES_DATASET.CUSTOMER` c
INNER JOIN `RAW_HES_DATASET.APPLICATION` ap ON c.id = ap.customer_id
INNER JOIN `RAW_VMB_DATASET.APPLY_INFO` ay ON c.cuid = ay.cuid
WHERE c.CUID IS NOT NULL
AND ap.SERIAL_NUMBER IS NOT NULL
AND ap.status = 'ACTIVE'
AND longitude <> "null"
AND latitude <> "null"
  AND NOT EXISTS (
    -- 排除已經在 RAW 的 serial_number（避免重複處理）
    SELECT 1 FROM `RAW_EDEP_DATASET.GEO_DATA` a
    WHERE a.serial_number = ap.SERIAL_NUMBER )
  AND NOT EXISTS (
    -- 排除已經在 failed retry table 的 series_number（避免重複發查）
    SELECT 1 FROM `RAW_EDEP_DATASET.GEO_DATA_FAILED_RETRY_LIST` fr
    WHERE fr.series_number = ap.SERIAL_NUMBER )
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY c.CUID, ap.SERIAL_NUMBER
  ORDER BY ap.BQ_UPDATED_TIME DESC
) = 1
ORDER BY cuid, serial_number
LIMIT 500
