WITH ApiLogsWithReferenceID AS (
  SELECT
    *,
    REGEXP_EXTRACT(status_detail, r'/api/insights/v1/(.+?)\?') AS extracted_reference_id
  FROM
    `API_DATASET.API_LOG`
  WHERE
    API_Name = 'CREDOLAB'
  AND 
    status_detail LIKE '%/api/insights/v1/%'
)
SELECT
  *
FROM
  ApiLogsWithReferenceID
WHERE

  extracted_reference_id = 'dc4cc5af-0fe4-4f3c-8e67-8eb002e6fa52_20251028235646'