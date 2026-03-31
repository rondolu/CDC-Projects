SELECT DISTINCT
  c.CUID as cuid,
  ap.SERIAL_NUMBER as serial_number,
  ay.LONGITUDE as longitude,
  ay.LATITUDE as latitude
FROM `RAW_HES_DATASET.CUSTOMER` c
LEFT JOIN `RAW_HES_DATASET.APPLICATION` ap ON (c.id = ap.customer_id)
LEFT JOIN `RAW_VMB_DATASET.APPLY_INFO` ay ON (c.cuid = ay.cuid)
WHERE c.cuid IS NOT NULL
  AND DATE(ap.partition_date) BETWEEN @start_date AND @end_date
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.CUID, ap.SERIAL_NUMBER ORDER BY ap.partition_date DESC) = 1

ORDER BY cuid, serial_number
