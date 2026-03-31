"""
批次處理服務
核心批次處理邏輯，包含：
- BatchContext: 批次上下文管理
- _process_batch_generic: 通用批次處理編排
- _load_geo_data: 資料載入與分頁
- _process_single_batch: 統一的批次處理方法
- _process_batch_records: 批次記錄處理
"""

from __future__ import annotations

import os
import json
from typing import Dict, Any, Optional, List, Callable, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from uuid import uuid4

from application.bigquery_service import BigQueryService
from services.google_maps_api_service import GoogleMapsAPIService
from models.google_maps_models import POIScenarioEnum
from utils.infra_logging import _logger, Logging
from utils.request_context import get_current_log
from utils.data_processor import prepare_geo_raw_row
from utils.gcs_services import GCSService
from utils.pubsub_services import PubSubService, PubSubError
from modules.config import config


@dataclass
class ProcessingResult:
    """處理結果資料結構"""
    success_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    processed_references: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BatchContext:
    """批次上下文，用於追蹤批次狀態"""
    batch_number: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    callback_handler: Optional[Callable] = None
    source: str = "unknown"
    batch_uuid: Optional[str] = None
    is_last_batch: bool = False

    def __post_init__(self):
        if self.batch_uuid is None:
            self.batch_uuid = str(uuid4())
        self.flow_id = f"geo-data-resolver_{self.batch_uuid}"
        


class BatchProcessService:
    """批次處理服務核心"""
    
    def __init__(self) -> None:
        self.bq = BigQueryService()
        self.api_service = GoogleMapsAPIService()
        self.gcs = GCSService()
        self.config = config
        self.batch_size = self.config.google_maps_batch_size 
        self.pubsub_service = PubSubService()

        shared_log = get_current_log()
        self.log = shared_log if isinstance(shared_log, Logging) else Logging(
            mission_name="batch_process_service",
            log_uuid=str(uuid4()),
            flow_code="E06_geo_data_resolver",
        )

    def _publish_anonymization_notification(self) -> Optional[str]:
        """在 flatten SQL 完成後，通知 anonymization topic。

        Returns: message_id 或 None (失敗)
        """
        file_list = [
            "TRANS_EDEP_DATASET.GEO_DATA"
        ]
        try:
            message = {"file_list": file_list}
            message_id = self.pubsub_service.publish_pubsub_message(
                topic_name=self.config.anonymization_pubsub_topic,
                message=message,
                project_id=self.config.pubsub_project_id
            )
            _logger.log_text(
                f"anonymization_publish_completed | file_list={file_list}",
                severity="Notice"
            )
            return f"NOTICE: anonymization published {message_id}"
        except PubSubError as e:
            _logger.log_text(
                f"anonymization_publish_failed | mission={getattr(self.log, 'mission_name', None)} | error={str(e)}", 
                severity="Error"
            )
            return None

    

    @Logging.logtobq(task_code="03")
    def _process_batch_generic(
        self,
        batch_loader_func: Callable,
        batch_processor_func: Callable,
        context: BatchContext,
        **kwargs
    ) -> Dict[str, Any]:
        """
        通用批次處理編排

        Args:
            batch_loader_func: 載入全量資料的函數
            batch_processor_func: 批次處理函數
            context: 批次上下文
            **kwargs: 傳遞給 loader 的查詢參數
        """
        try:
            data = batch_loader_func(**kwargs)

            if not data:
                print("No data found to process")
                context.is_last_batch = True

            # 處理批次
            result = batch_processor_func(data, context)

            return result

        except Exception as e:
            _logger.log_text(f"{e}", severity="Warning")
            return {
                "status": "error",
                "message": str(e),
                "batch_number": context.batch_number,
                "uuid": getattr(context, "batch_uuid", None),
                "flow_id": getattr(context, "flow_id", None),
            }

    def _load_geo_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        try:
            import os
            if start_date and end_date:
                sql_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    'sql',
                    'get_geo_query_data_range.sql'
                )
                sql_content = open(sql_path, 'r', encoding='utf-8').read()
                sql_content = sql_content.replace('@start_date', f"'{start_date}'")
                sql_content = sql_content.replace('@end_date', f"'{end_date}'")
            else:
                sql_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    'sql',
                    'get_geo_query_data.sql'
                )
                sql_content = open(sql_path, 'r', encoding='utf-8').read()

            _logger.log_text("Loading geo data from query sql", severity="Info")
            return self.bq.query(sql_content)
        except Exception as e:
            _logger.log_text(f"Error loading geo data: {e}", severity="Error")
            return []

    def _load_failed_retry_rows(self) -> List[Dict[str, Any]]:
        """載入 failed-retry 清單，並映射成處理管線所需欄位名稱。"""
        try:
            sql_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'sql',
                'failed_retry_list.sql'
            )
            sql_content = open(sql_path, 'r', encoding='utf-8').read()
            rows = self.bq.query(sql_content)

            mapped: List[Dict[str, Any]] = []
            for r in rows:
                mapped.append({
                    "cuid": r.get("cuid"),
                    "serial_number": r.get("series_number"),
                    "created_at": r.get("BQ_UPDATED_TIME"),
                    "current_detailed_address": r.get("contact_address"),
                    "permanent_detailed_address": r.get("residence_address"),
                    "tax_code": r.get("tax_code"),
                    "company_name": r.get("company_name"),
                    "longitude": r.get("contract_longitude"),
                    "latitude": r.get("contract_latitude"),
                    "partition_date": r.get("PARTITION_DATE"),
                })

            return mapped
        except Exception as e:
            _logger.log_text(f"Error loading failed-retry rows: {e}", severity="Error")
            return []
        
    @Logging.logtobq(task_code="04")
    def _process_single_batch(
        self,
        data: List[Dict[str, Any]],
        context: BatchContext
    ) -> Dict[str, Any]:
        """
        統一的批次處理方法
        
        - 判斷是否為最後一批（資料筆數 < batch_size）
        - 返回適當的response

        Args:
            data: 當前批次的資料列表
            context: 批次上下文

        Returns:
            處理結果
        """
        try:
            # 記錄批次開始
            print(f"Starting batch processing: batch {context.batch_number}")

            total_records = len(data)

            # 判斷是否為最後一批：如果batch_size > 資料筆數，則為最後一批
            is_last_batch = self.batch_size > total_records
            context.is_last_batch = is_last_batch

            # 處理當前批次
            batch_result, pubsub_message_id = self._process_batch_records(data, context)

            # 準備response
            if not is_last_batch:
                # 還有下一批，觸發下一批處理
                return {
                    "status": "processing",
                    "message": f"Geo-data-resolver batch {context.batch_number} completed, next batch triggered",
                    "total_records": total_records,
                    "the_batch_result": {
                        "success_count": batch_result.success_count,
                        "error_count": batch_result.error_count,
                        "skipped_count": batch_result.skipped_count,
                        "processed_references": batch_result.processed_references
                    },
                    "pubsub_message_id": pubsub_message_id
                }
            else:
                # 最後一批，完成處理
                total_rows = batch_result.success_count + batch_result.error_count + batch_result.skipped_count
                response_payload = {
                    "status": "completed",
                    "message": f"All batches completed at batch {context.batch_number}",
                    "all_batch_records": total_rows,
                    "the_batch_result": {
                        "success_count": batch_result.success_count,
                        "error_count": batch_result.error_count,
                        "skipped_count": batch_result.skipped_count,
                        "processed_references": batch_result.processed_references
                    }
                }

                _logger.log_text(
                    f"final_batch_response | mission={getattr(self.log, 'mission_name', None)} | "
                    f"batch_number={context.batch_number} | payload={json.dumps(response_payload, ensure_ascii=False)}",
                    severity="Info"
                )

                return response_payload

        except Exception as e:
            _logger.log_text(f"Error in _process_single_batch: {e}", severity="Info")
            raise

    @Logging.logtobq(task_code="05")
    def _process_batch_records(
        self,
        data: List[Dict[str, Any]],
        context: BatchContext
    ) -> Tuple[ProcessingResult, Optional[str]]:
        """
        處理批次記錄
        - FOR loop 處理每筆記錄
        - 調用 API
        - 上傳 GCS
        - 寫入 BigQuery
        - 記錄失敗

        Args:
            data: 資料列表
            context: 批次上下文

        Returns:
            Tuple[ProcessingResult, Optional[str]]: 處理結果和 pubsub message id
        """
        try:
            result = ProcessingResult()
            raw_rows: List[Dict[str, Any]] = []

            # 記錄批次處理開始
            print(f"Processing {len(data)} records in batch {context.batch_number}")

            # FOR each record
            for record in data:
                try:
                    latitude = record.get("latitude")
                    longitude = record.get("longitude")

                    # 每筆資料的 scenario -> count 對應（用於 RAW 表 raw_data）
                    scenario_counts: Dict[str, Any] = {}
                    # 若任一情境失敗，該筆資料不應寫入 RAW（僅記錄 failed-retry）
                    had_error_for_record = False

                    # 處理每個 scenario
                    for scenario in POIScenarioEnum:
                        try:
                            api_response = self.api_service.get_area_insights(
                                latitude=latitude,
                                longitude=longitude,
                                scenario=scenario
                            )
                            result.success_count += 1

                            # 累計 scenario -> count
                            scenario_counts[scenario.value] = api_response.get("count")

                        except Exception as api_error:
                            # API 失敗，記錄到失敗表
                            result.error_count += 1
                            had_error_for_record = True
                            try:
                                self.bq.insert_failed_record(
                                    {
                                        "uuid": context.batch_uuid,
                                        "cuid": record.get("cuid"),
                                        "serial_number": record.get("serial_number"),
                                        "contact_address": record.get("current_detailed_address"),
                                        "residence_address": record.get("permanent_detailed_address"),
                                        "tax_code": record.get("tax_code"),
                                        "company_name": record.get("company_name"),
                                        "latitude": latitude,
                                        "longitude": longitude,
                                        "scenario": scenario.value,
                                    },
                                    status_code=str(getattr(api_error, "status_code", "ERROR"))
                                )
                            except Exception:
                                pass
                            # 失敗時該 scenario 設為 None
                            scenario_counts[scenario.value] = "null"

                except Exception as record_error:
                    _logger.log_text(
                        f"Error processing record: {record_error}",
                        severity="Info"
                    )
                    result.error_count += 1
                    continue

                # 僅在該筆資料所有情境皆成功時，才建立 RAW 列
                if not had_error_for_record:
                    try:
                        source_record = {
                            "uuid": context.batch_uuid,
                            "cuid": record.get("cuid"),
                            "serial_number": record.get("serial_number"),
                            "contact_address": record.get("current_detailed_address"),
                            "residence_address": record.get("permanent_detailed_address"),
                            "company_name": record.get("company_name"),
                            "contract_longitude": record.get("longitude"),
                            "contract_latitude": record.get("latitude"),
                            "longitude": record.get("longitude"),
                            "latitude": record.get("latitude"),
                        }
                        raw_rows.append(
                            prepare_geo_raw_row(
                                source_record,
                                api_result={
                                    "scenario_counts": scenario_counts,
                                },
                            )
                        )
                    except Exception as e:
                        _logger.log_text(f"Failed to build raw row: {e}", severity="Warning")

            self._upload_raw_rows_to_gcs(raw_rows, context)
            self._insert_raw_rows_to_bq(raw_rows)

            # 記錄批次完成統計
            print(
                f"Batch {context.batch_number} summary: "
                f"{len(raw_rows)} original records, "
                f"{result.success_count} API scenario calls, "
                f"{result.error_count} errors, {result.skipped_count} skipped"
            )

            # 執行recall logic 
            pubsub_message_id = None
            if context.callback_handler and not context.is_last_batch:
                try:
                    pubsub_message_id = context.callback_handler(context)
                    print(f"Published next batch message after batch {context.batch_number} completed")
                except Exception as e:
                    _logger.log_text(f"Failed to publish recall message: {e}", severity="Error")

            # 若為最後一批，執行後續處理
            if context.is_last_batch:
                self.post_batch_processing(context)

            return result, pubsub_message_id

        except Exception as e:
            _logger.log_text(f"Error in _process_batch_records: {e}", severity="Info")
            raise

    def _upload_raw_rows_to_gcs(self, raw_rows: List[Dict[str, Any]], context: BatchContext) -> None:
        """上傳原始列到 GCS ; 若 raw_rows 為空則直接返回 """
        if not raw_rows:
            return
        try:
            bucket = self.config.gcs_bucket_name
            prefix = self.config.gcs_blob_path
            if not bucket:
                raise RuntimeError("GCS bucket_name not configured")

            partition_date = datetime.now().strftime('%Y-%m-%d')
            upload_result = self.gcs.upload_rows_as_json(
                rows=raw_rows,
                bucket_name=bucket,
                prefix=prefix,
                partition_date=partition_date,
            )
            _logger.log_text(
                f"Batch {context.batch_number}: Successfully uploaded {upload_result['uploaded']} records to GCS",
                severity="Info",
            )
        except Exception as e:
            _logger.log_text(f"GCS upload step failed: {e}", severity="Info")


    def _insert_raw_rows_to_bq(self, raw_rows: List[Dict[str, Any]]) -> None:
        """批次寫入 BigQuery；若 raw_rows 為空則直接返回。失敗時寫入失敗記錄 """
        if not raw_rows:
            return
        try:
            self.bq.insert_rows(raw_rows, table_name=self.config.geo_table)
            print(f"Batch inserted {len(raw_rows)} rows to BigQuery")
        except Exception as e:
            _logger.log_text(f"Raw table insert failed: {e}", severity="Info")
            for raw_row in raw_rows:
                try:
                    self.bq.insert_failed_record(
                        raw_row,
                        status_code="INSERT RAW TABLE FAILED"
                    )
                except Exception as insert_error:
                    _logger.log_text(
                        f"Failed to insert failed record for serial_number {raw_row.get('serial_number')}: {insert_error}",
                        severity="Info",
                    )

    def post_batch_processing(self, context: BatchContext) -> None:
        """
        若為最後一批：
        - 先處理 failed-retry
        - 更新失敗重試清單狀態
        - 執行 flatten SQL
        - 成功時通知匿名化服務
        - 寫入完成 flowlog
        """
        _logger.log_text("Starting post-batch processing: update failed retry status.", severity="Info")

        # - Range 模式：使用 end_date
        # - Daily 模式：使用今天日期
        partition_date = context.end_date or datetime.now().strftime('%Y-%m-%d')

        # 1) 先處理 failed-retry（查詢時間窗口：從 D-1 起算的過去 3 天，排除當日）
        try:
            retry_rows = self._load_failed_retry_rows()
            if retry_rows:
                _logger.log_text(f"Processing failed-retry rows: {len(retry_rows)}", severity="Info")
                # 以 batch_size 切塊處理，避免一次爆量
                for i in range(0, len(retry_rows), self.batch_size):
                    chunk = retry_rows[i:i + self.batch_size]
                    # 避免在 chunk 完成後再次遞迴呼叫 post_batch_processing
                    temp_ctx = BatchContext(
                        batch_number=f"retry-{i//self.batch_size+1}",
                        start_date=context.start_date,
                        end_date=context.end_date,
                        source="failed-retry",
                        batch_uuid=context.batch_uuid,
                        is_last_batch=False,
                    )
                    try:
                        self._process_batch_records(chunk, temp_ctx)
                    except Exception as e:
                        _logger.log_text(f"Error processing failed-retry chunk: {e}", severity="Error")

                _logger.log_text(f"Failed-retry processing completed ", severity="Info")
            else:
                _logger.log_text("No failed-retry rows to process", severity="Info")
        except Exception as e:
            _logger.log_text(f"Failed to load/process failed-retry rows: {e}", severity="Info")

        # 2) 執行 flatten SQL
        flatten_success = False
        try:
            _logger.log_text("Executing flatten SQL.", severity="Info")
            sql_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sql', 'flatten_geo_data.sql')
            flatten_sql = open(sql_path, 'r', encoding='utf-8').read()
            flatten_sql = flatten_sql.replace('@partition_date', f"'{partition_date}'")
            self.bq.query(flatten_sql)
            _logger.log_text("flatten SQL succeeded", severity="Info")
            flatten_success = True
        except Exception as flatten_error:
            _logger.log_text(f"Flatten SQL failed: {flatten_error}", severity="Error")

        # 如果 flatten 成功，才發布匿名化通知
        anonymization_msg_id = None
        if flatten_success:
            anonymization_msg_id = self._publish_anonymization_notification()
            if anonymization_msg_id:
                _logger.log_text(
                    f"Anonymization notification: {anonymization_msg_id}",
                    severity="Notice",
                )

        # Flow 完成紀錄
        if anonymization_msg_id:
            print("all job completed")
            if self.log:
                self.log.flowlog(
                    task_name="process_batch",
                    task_code="01",
                    message="all job completed",
                    status=self.log.status_s,
                    severity=self.log.severity_3,
                )

   