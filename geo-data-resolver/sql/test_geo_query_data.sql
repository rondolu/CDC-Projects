-- 測試發查名單 - 11筆測試資料 (2025-10-20)
-- 用於測試Google Maps地理數據解析功能
-- 修正版：使用正確的 TIMESTAMP 和 DATE 格式

SELECT
  cuid,
  serial_number,
  created_at,
  current_detailed_address,
  permanent_detailed_address,
  tax_code,
  company_name,
  longitude,
  latitude,
  partition_date
FROM (
  SELECT
    "a5c50c8b-792c-4da4-b279-966caf055d33" as cuid,
    "141011354623dfdfdd123456" as serial_number,
    TIMESTAMP("2025-10-14 11:09:43.765312+00") as created_at,
    "Ngõ 24 kim đồng" as current_detailed_address,
    "Thôn Lương Thiện Lương Sơn, Thanh Hóa" as permanent_detailed_address,
    CAST(NULL AS STRING) as tax_code,
    "việt foood" as company_name,
    "105.76631755800807" as longitude,
    "10.039397649536806" as latitude,
    DATE("2025-10-20") as partition_date
  UNION ALL
  SELECT
    "b7d61e2c-8a3f-4e1a-9c4b-5f3e7a2c1d9a" as cuid,
    "141011354623dfdfdd123456789" as serial_number,
    TIMESTAMP("2025-10-14 11:15:22.432156+00") as created_at,
    "Số 45 Nguyễn Huệ" as current_detailed_address,
    "Xã Tân Bình, TP Hồ Chí Minh" as permanent_detailed_address,
    "0305123456" as tax_code,
    "mekong coffee solutions" as company_name,
    "106.36492068013104" as longitude,
    "10.252252252252251" as latitude,
    DATE("2025-10-20") as partition_date
  
) AS test_data
WHERE NOT EXISTS (
  -- 排除已經在raw表中的serial_number
  SELECT 1
  FROM `RAW_EDEP_DATASET.GEO_DATA` a
  WHERE a.serial_number = test_data.serial_number
)

-- UNION ALL

-- -- 合併失敗重試列表中的待重試記錄
-- SELECT
--   f.cuid,
--   f.series_number as serial_number,
--   TIMESTAMP(f.BQ_UPDATED_TIME) as created_at,
--   f.contact_address as current_detailed_address,
--   f.residence_address as permanent_detailed_address,
--   f.tax_code as tax_code,
--   f.company_name as company_name,
--   f.contract_longitude as longitude,
--   f.contract_latitude as latitude,
--   f.PARTITION_DATE as partition_date
-- FROM (
--   WITH latest_status AS (
--     SELECT
--       uuid,
--       cuid,
--       series_number,
--       contact_address,
--       residence_address,
--       tax_code,
--       company_name,
--       contract_longitude,
--       contract_latitude,
--       api_payload_message,
--       api_status,
--       BQ_UPDATED_TIME,
--       PARTITION_DATE,
--       ROW_NUMBER() OVER (
--         PARTITION BY series_number
--         ORDER BY BQ_UPDATED_TIME DESC
--       ) AS rn
--     FROM `RAW_EDEP_DATASET.GEO_DATA_FAILED_RETRY_LIST`
--     WHERE PARTITION_DATE >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
--   )
--   SELECT *
--   FROM latest_status
--   WHERE rn = 1
--     AND NOT (api_status LIKE '2%' OR api_status = 'success')
-- ) f

ORDER BY cuid, serial_number
