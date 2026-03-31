
INSERT INTO `TRANS_EDEP_DATASET.TMP_GEO_DATA` (
    cuid,
    serial_number,
    contract_longitude,
    contract_latitude,
    contact_address,
    residence_address,
    company_name,
    contract_country,
    contract_city,
    contract_district,
    contract_ward,
    contract_street,
    contract_place_id,
    contract_global_code,
    contact_longitude,
    contact_latitude,
    contact_country,
    contact_city,
    contact_district,
    contact_ward,
    contact_street,
    contact_place_id,
    contact_global_code,
    residence_longitude,
    residence_latitude,
    residence_country,
    residence_city,
    residence_district,
    residence_ward,
    residence_street,
    residence_place_id,
    residence_global_code,
    company_longitude,
    company_latitude,
    company_country,
    company_city,
    company_district,
    company_ward,
    company_street,
    company_place_id,
    company_global_code,
    contract_place_types,
    contact_place_types,
    residence_place_types,
    commute_time_contract_contact,
    commute_distance_contract_contact,
    commute_time_company_contact,
    commute_distance_company_contact,
    contract_poi_corporate_finance,
    contract_poi_commercial_facility,
    contract_poi_residential,
    BQ_UPDATED_TIME,
    PARTITION_DATE
)
WITH
    json_input AS (
        SELECT
            r.cuid,
            r.serial_number,
            r.contact_address,
            r.residence_address,
            r.company_name,
            r.contract_longitude,
            r.contract_latitude,
            r.BQ_UPDATED_TIME,
            r.PARTITION_DATE,
            PARSE_JSON(r.raw_data) AS parsed_json
        FROM `RAW_EDEP_DATASET.GEO_DATA` r
        LEFT JOIN `TRANS_EDEP_DATASET.TMP_GEO_DATA` t
            ON r.serial_number = t.serial_number 
        WHERE r.serial_number IS NOT NULL
        AND t.serial_number IS NULL -- 只處理還沒進Trans的資料
        QUALIFY ROW_NUMBER() OVER (PARTITION BY r.serial_number ORDER BY PARTITION_DATE DESC) = 1

    ),
    base_data AS (
        SELECT
            cuid,
            serial_number,
            contact_address,
            residence_address,
            company_name,
            contract_longitude,
            contract_latitude,
            BQ_UPDATED_TIME,
            PARTITION_DATE,
            -- 從 JSON 中提取 POI 計數
            JSON_VALUE(parsed_json, '$.scenario_counts.corporate_finance')  AS contract_poi_corporate_finance,
            JSON_VALUE(parsed_json, '$.scenario_counts.commercial')  AS contract_poi_commercial_facility,
            JSON_VALUE(parsed_json, '$.scenario_counts.residential')  AS contract_poi_residential
        FROM json_input
    )
SELECT
    -- 基本資訊 (來自 source table)
    b.cuid,
    b.serial_number,

    CASE WHEN SAFE_CAST(b.contract_longitude AS FLOAT64) IS NULL THEN NULL ELSE CAST(ROUND(SAFE_CAST(b.contract_longitude AS FLOAT64), 4) AS STRING) END AS contract_longitude,
    CASE WHEN SAFE_CAST(b.contract_latitude AS FLOAT64) IS NULL THEN NULL ELSE CAST(ROUND(SAFE_CAST(b.contract_latitude AS FLOAT64), 4) AS STRING) END AS contract_latitude,
    CASE WHEN b.contact_address IS NULL OR TRIM(CAST(b.contact_address AS STRING)) = '' THEN NULL ELSE CAST(b.contact_address AS STRING) END AS contact_address,
    CASE WHEN b.residence_address IS NULL OR TRIM(CAST(b.residence_address AS STRING)) = '' THEN NULL ELSE CAST(b.residence_address AS STRING) END AS residence_address,

    b.company_name,

    -- 尚無來源的欄位，先給 NULL
    CAST(NULL AS STRING) AS contract_country,
    CAST(NULL AS STRING) AS contract_city,
    CAST(NULL AS STRING) AS contract_district,
    CAST(NULL AS STRING) AS contract_ward,
    CAST(NULL AS STRING) AS contract_street,
    CAST(NULL AS STRING) AS contract_place_id,
    CAST(NULL AS STRING) AS contract_global_code,
    CAST(NULL AS STRING) AS contact_longitude,
    CAST(NULL AS STRING) AS contact_latitude,
    CAST(NULL AS STRING) AS contact_country,
    CAST(NULL AS STRING) AS contact_city,
    CAST(NULL AS STRING) AS contact_district,
    CAST(NULL AS STRING) AS contact_ward,
    CAST(NULL AS STRING) AS contact_street,
    CAST(NULL AS STRING) AS contact_place_id,
    CAST(NULL AS STRING) AS contact_global_code,
    CAST(NULL AS STRING) AS residence_longitude,
    CAST(NULL AS STRING) AS residence_latitude,
    CAST(NULL AS STRING) AS residence_country,
    CAST(NULL AS STRING) AS residence_city,
    CAST(NULL AS STRING) AS residence_district,
    CAST(NULL AS STRING) AS residence_ward,
    CAST(NULL AS STRING) AS residence_street,
    CAST(NULL AS STRING) AS residence_place_id,
    CAST(NULL AS STRING) AS residence_global_code,
    CAST(NULL AS STRING) AS company_longitude,
    CAST(NULL AS STRING) AS company_latitude,
    CAST(NULL AS STRING) AS company_country,
    CAST(NULL AS STRING) AS company_city,
    CAST(NULL AS STRING) AS company_district,
    CAST(NULL AS STRING) AS company_ward,
    CAST(NULL AS STRING) AS company_street,
    CAST(NULL AS STRING) AS company_place_id,
    CAST(NULL AS STRING) AS company_global_code,
    CAST(NULL AS STRING) AS contract_place_types,
    CAST(NULL AS STRING) AS contact_place_types,
    CAST(NULL AS STRING) AS residence_place_types,
    CAST(NULL AS STRING) AS commute_time_contract_contact,
    CAST(NULL AS STRING) AS commute_distance_contract_contact,
    CAST(NULL AS STRING) AS commute_time_company_contact,
    CAST(NULL AS STRING) AS commute_distance_company_contact,

    b.contract_poi_corporate_finance,
    b.contract_poi_commercial_facility,
    b.contract_poi_residential,

    -- 時間戳記
    b.BQ_UPDATED_TIME,
    b.PARTITION_DATE
FROM base_data b;

