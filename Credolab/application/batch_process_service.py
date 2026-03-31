"""
批次處理服務 - 主要業務邏輯
負責統籌 VMB 資料處理、Credolab API 呼叫、資料處理及儲存流程
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path

from modules.config import config
from modules.exceptions import CredolabError, DataValidationError, CredolabAPIError
from application.bigquery_service import BigQueryService
from services.credolab_api_service import CredolabAPIService
from utils.data_processor import prepare_raw_data_for_bq
from utils.infra_logging import Logging, _logger
from utils.request_context import get_current_log
from uuid import uuid4
from utils.gcs_services import GCSService
from google.cloud import exceptions as gcloud_exceptions
from utils.pubsub_services import PubSubService


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
    """批次處理的上下文資訊，包含批次編號等處理參數"""
    batch_number: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    device_type: Optional[str] = None
    callback_handler: Optional[Callable] = None
    source: str = "unknown"


class BatchProcessService:
    """批次處理的主要服務類別，負責處理 VMB 資料的批次作業

    功能區塊（方便閱讀）：
    - 公開 API：process_vmb_data*、get_processing_status
    - 批次框架：_process_batch_generic、_initiate_batch_processing、_orchestrate_batch_processing、_process_batch_records
    - 資料載入：_load_vmb_data
    - API 呼叫：_call_credolab_api
    - 批次處理：_batch_upload_to_gcs、_batch_insert_to_bigquery
    - 錯誤處理：_handle_operation_error
    """
    
    def __init__(self):
        self.config = config  # 使用單例配置
        self.bq_service = BigQueryService()
        self.api_service = CredolabAPIService()
        self.gcs_service = GCSService()  # 直接使用 GCS 服務
        self.pubsub_service = PubSubService()

        shared_log = get_current_log()
        self.log = shared_log if isinstance(shared_log, Logging) else Logging(
            mission_name="batch_process_service",
            log_uuid=str(uuid4()),
            flow_code="E05_credolab",
        )
        
        # 設定批次處理大小
        self.batch_size = self.config.credolab_batch_size
        print(f"BatchProcessService initialized with batch_size: {self.batch_size}")

    def _publish_anonymization_notification(self) -> str:
        """在 flatten SQL 完成後，通知 anonymization topic。

        成功時回傳訊息 ID 字串；失敗時不攔截例外，直接拋出以中斷流程。
        """
        file_list = [
            "TRANS_EDEP_DATASET.CREDOLAB_DATA_ANDROID", "TRANS_EDEP_DATASET.CREDOLAB_DATA_iOS"
        ]
        message_id = self.pubsub_service.publish_anonymization(file_list)
        _logger.log_text(
            f"anonymization_publish_completed | mission={getattr(self.log, 'mission_name', None)} | message_id={message_id} | file_list={file_list}",
            severity="Notice"
        )
        return f"NOTICE: anonymization published {message_id}"
    
    def _read_sql_file(self, sql_filename: str) -> str:
        """從 SQL 目錄讀取 SQL 檔案內容

        Args:
            sql_filename: SQL 檔案名稱

        Returns:
            str: SQL 查詢內容

        Raises:
            FileNotFoundError: 當 SQL 檔案不存在時
        """
        sql_path = Path(__file__).parent.parent / "sql" / sql_filename
        
        if not sql_path.exists():
            raise FileNotFoundError(f"SQL 檔案不存在: {sql_path}")
        
        try:
            with open(sql_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            raise Exception(f"讀取 SQL 檔案失敗: {e}")
    
    def _handle_operation_error(self, error: Exception, operation_name: str, context: Optional[Dict[str, Any]] = None) -> CredolabError:
        """統一錯誤處理邏輯"""
        context = context or {}
        
        if isinstance(error, gcloud_exceptions.GoogleCloudError):
            # Google Cloud 服務錯誤
            _logger.log_text(f"Google Cloud error in {operation_name}: {str(error)}", severity="Error")
            return CredolabError(f"Google Cloud service error in {operation_name}: {str(error)}")
        elif isinstance(error, CredolabAPIError):
            # Credolab API 特定錯誤
            _logger.log_text(f"Credolab API error in {operation_name}: {str(error)}", severity="Error")
            return error  # 保持原始錯誤類型
        elif isinstance(error, DataValidationError):
            # 資料驗證錯誤
            _logger.log_text(f"Data validation error in {operation_name}: {str(error)}", severity="Error")
            return error  # 保持原始錯誤類型
        else:
            _logger.log_text(f"Unexpected error in {operation_name}: {str(error)}", severity="Error")
            return CredolabError(f"Unexpected error in {operation_name}: {str(error)}")
    
    def _process_batch_generic(
        self, 
        batch_loader_func: Callable, 
        batch_processor_func: Callable, 
        context: BatchContext,
        **kwargs
    ) -> Dict[str, Any]:
        """通用批次處理框架"""
        try:
            # 記錄流程開始
            # 僅於完成/錯誤由裝飾器寫入 flow_log，不記錄開始
            # 載入數據
            data = batch_loader_func(**kwargs)
            
            if not data:
                print("No data found to process")
                
                # 即使沒有資料，也要執行 flatten SQL 和 anonymization
                partition_date = datetime.now().strftime('%Y-%m-%d')
                flatten_all_success = True
                anonymization_msg_id = None
                
                for sql_name in ("flatten_data_android.sql", "flatten_data_ios.sql"):
                    print(f"Running flatten SQL: {sql_name}")
                    self.bq_service.run_sql_file(sql_name, {"partition_date": partition_date})
                    print(f"Flatten SQL succeeded: {sql_name}")

                if flatten_all_success:
                    anonymization_msg_id = self._publish_anonymization_notification()

                response_payload = {
                    "status": "completed",
                    "message": "No data to process, but flatten and anonymization completed",
                    "total_records": 0
                }
                
                if anonymization_msg_id:
                    response_payload["anonymization_message_id"] = anonymization_msg_id
                else:
                    response_payload["anonymization_skipped"] = "flatten_failed"

                try:
                    self.log.flowlog(
                        task_name="process",
                        task_code="01",
                        message="all job completed",
                        status=self.log.status_s,
                        severity=self.log.severity_3,
                    )
                except Exception as e:
                    _logger.log_text(f"Warning: failed to write final Notice flow log: {e}", severity="Warning")

                return response_payload
            
            # 計算批次資訊
            total_records = len(data)
                        
            # 如果沒有資料，直接回傳完成
            if total_records == 0:
                return {
                    "status": "completed",
                    "message": "No data to process",
                    "total_records": 0
                }
            
            # 處理批次
            result = batch_processor_func(data, context)
            
            return result
            
        except Exception as e:
            _logger.log_text(f"{e}", severity="Warning")
            handled_error = self._handle_operation_error(
                e, 
                "process_batch_generic", 
                {"batch_number": context.batch_number, **kwargs}
            )
            raise handled_error
    
    def _load_vmb_data(
        self, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None, 
        device_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """載入 VMB 資料（統一的數據載入函數）"""
        # 根據是否有日期參數選擇適當的 SQL FILE
        if start_date or end_date:
            sql_query = self._read_sql_file("get_vmb_data_range.sql")
        else:
            sql_query = self._read_sql_file("get_vmb_data.sql")
        
        # 設定查詢參數
        query_params = {}
        partition_date = datetime.now().strftime('%Y-%m-%d')
        query_params["partition_date"] = partition_date

        if start_date:
            query_params["start_date"] = start_date
        if end_date:
            query_params["end_date"] = end_date
        if device_type:
            query_params["device_type"] = device_type.upper()
        
        return self.bq_service.execute_query(sql_query, query_params)
    
    def _orchestrate_batch_processing(self, data: List[Dict[str, Any]], context: BatchContext) -> Dict[str, Any]:
        """協調單一批次的處理流程（包含批次範圍計算、記錄處理、狀態管理）"""
        # 生成批次ID用於 logging
        batch_id = self._generate_batch_id(context)
        
        print(f"Starting batch processing")
        
        # 取得該批次資料
        batch_data = data
        # 提前判斷是否為最後一批（避免在處理結束後才決定 recall）
        is_last_batch = self.batch_size > len(batch_data)
        
        # 設定recall函數（以簡單 callable 封裝）
        def publish_next_batch():
            if context.callback_handler:
                return context.callback_handler(context)
            return None

        try:
            # 處理批次；僅在非最後一批時允許內部發布 recall
            batch_result = self._process_batch_records(
                batch_data,
                context.batch_number,
                publish_next_batch,
                is_last_batch=is_last_batch,
            )
                        
            if not is_last_batch:
                print(f"Batch {batch_id} completed successfully")
                return {
                    "status": "processing",
                    "message": f"Batch {context.batch_number} completed",
                    "batch_number": context.batch_number,
                    "batch_result": {
                        "success_count": batch_result.success_count,
                        "error_count": batch_result.error_count,
                        "processed_references": batch_result.processed_references
                    }
                }
            else:
                # 最後一個批次，執行完成後進行 RAW -> TRANS flatten SQL
                total_rows = batch_result.success_count + batch_result.error_count
                response_payload = {
                    "status": "completed",
                    "message": f"All batches completed",
                    "batch_number": context.batch_number,
                    "final_batch_result": {
                        "total_count": total_rows,
                        "success_count": batch_result.success_count,
                        "error_count": batch_result.error_count,
                        "processed_references": batch_result.processed_references
                    }
                }
                partition_date = datetime.now().strftime('%Y-%m-%d')
                flatten_all_success = True
                for sql_name in ("flatten_data_android.sql", "flatten_data_ios.sql"):
                    print(f"Running flatten SQL: {sql_name}")
                    self.bq_service.run_sql_file(sql_name, {"partition_date": partition_date})
                    print(f"Flatten SQL succeeded: {sql_name}")

                if flatten_all_success:
                    anonymization_msg_id = self._publish_anonymization_notification()
                    if anonymization_msg_id:
                        response_payload["anonymization_message_id"] = anonymization_msg_id
                else:
                    response_payload["anonymization_skipped"] = "flatten_failed"
                try:
                    _logger.log_text(
                        f"final_batch_response | mission={getattr(self.log, 'mission_name', None)} | "
                        f"date_range={getattr(self.log, 'date_range', None)} | payload={json.dumps(response_payload, ensure_ascii=False, default=str)}",
                        severity="Info")
                except Exception as e:
                    _logger.log_text(f"Warning: failed to write final batch log_text: {e}", severity="Error")
                try:
                    self.log.flowlog(
                        task_name="process_recall_batch",
                        task_code="01",
                        message="all job completed",
                        status=self.log.status_s,
                        severity=self.log.severity_3,
                    )
                except Exception as e:
                    _logger.log_text(f"Warning: failed to write final Notice flow log: {e}", severity="Warning")

                return response_payload
        except Exception as e:
            _logger.log_text(f"Batch {batch_id} failed: {str(e)}", severity="Error")
            raise
    
    def _generate_batch_id(self, context: BatchContext) -> str:
        """生成批次ID"""
        # 使用簡單的數字格式：batch_number
        return str(context.batch_number)
    
    def _initiate_batch_processing(self, data: List[Dict[str, Any]], context: BatchContext) -> Dict[str, Any]:
        """處理第一批次並設定recall的統一邏輯"""
        total_records = len(data)
        
        print(f"Retrieved {total_records} VMB records, will process in batches")
        
        # 處理第一批次
        first_batch = data
        is_single_batch = len(first_batch) < self.batch_size
        
        # 設定回調函數（以簡單 callable 封裝）
        def publish_next_batch():
            if context.callback_handler:
                return context.callback_handler(context)
            return None

        # 僅在非最後一批（非單批次）時允許發布 recall
        first_batch_result = self._process_batch_records(
            first_batch,
            1,
            publish_next_batch,
            is_last_batch=is_single_batch,
        )
        
        # 準備response
        if len(data) >= self.batch_size:
            return {
                "status": "processing",
                "message": f"{context.source.title()} batch 1 completed, next batch triggered immediately after API calls",
                "total_records": total_records,
                "batch_result": {
                    "success_count": first_batch_result.success_count,
                    "error_count": first_batch_result.error_count,
                    "processed_references": first_batch_result.processed_references
                }
            }
        else:
            # 單批次情境，直接於完成後執行 flatten SQL
            partition_date = datetime.now().strftime('%Y-%m-%d')
            flatten_all_success = True
            anonymization_msg_id = None
            for sql_name in ("flatten_data_android.sql", "flatten_data_ios.sql"):
                print(f"Running flatten SQL: {sql_name}")
                self.bq_service.run_sql_file(sql_name, {"partition_date": partition_date})
                print(f"Flatten SQL succeeded: {sql_name}")

            if flatten_all_success:
                anonymization_msg_id = self._publish_anonymization_notification()

            response_payload = {
                "status": "completed",
                "message": f"{context.source.title()} processing completed in single batch",
                "total_records": total_records,
                "batch_result": {
                    "success_count": first_batch_result.success_count,
                    "error_count": first_batch_result.error_count,
                    "processed_references": first_batch_result.processed_references
                }
            }
            if anonymization_msg_id:
                response_payload["anonymization_message_id"] = anonymization_msg_id
            else:
                response_payload["anonymization_skipped"] = "flatten_failed"

            _logger.log_text(
                f"single_batch_response | mission={getattr(self.log, 'mission_name', None)} | "
                f"date_range={getattr(self.log, 'date_range', None)} | payload={json.dumps(response_payload, ensure_ascii=False, default=str)}",
                severity="Info"
            )
            try:
                self.log.flowlog(
                    task_name="process",
                    task_code="01",
                    message="all job completed",
                    status=self.log.status_s,
                    severity=self.log.severity_3,
                )
            except Exception as e:
                _logger.log_text(f"Warning: failed to write final Notice flow log: {e}", severity="Warning")

            return response_payload
    
    def _call_credolab_api(self, vmb_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        呼叫 Credolab API 取得洞察資料

        Args:
            vmb_record: VMB 資料記錄

        Returns:
            Dict: 包含 API 回應和記錄資訊的字典
            
        Raises:
            各種例外：由呼叫方處理
        """
        # 1. 取得 reference_id
        reference_id = vmb_record.get('reference_id') or vmb_record.get('referenceNumber')
        if not reference_id:
            raise DataValidationError("Missing reference_id in VMB record")
        
        # 2. 從 Credolab API 取得洞察資料
        api_response = self.api_service.get_credolab_insights(reference_id)

        # 2.1 若回應中含有 status_code 且不是 2xx，則視為失敗
        resp_status_code = str(api_response.get('status_code', '200'))
        if resp_status_code and not resp_status_code.startswith(('2', '20')):
            print(f"Skip saving for reference {reference_id}: api_response status_code={resp_status_code}")
            raise CredolabAPIError(f"Non-success status code in response: {resp_status_code}", status_code=resp_status_code)

        return {
            'reference_id': reference_id,
            'vmb_record': vmb_record,
            'api_response': api_response
        }
    
    def _process_batch_records(self, batch: List[Dict[str, Any]], batch_num: int,
                       next_batch_publisher: Optional[Callable[[], Optional[str]]] = None,
                       is_last_batch: bool = False) -> ProcessingResult:
        """
        處理單一批次中的所有記錄（批次處理模式）
        
        流程：
        1. 逐筆呼叫 API，收集成功的結果
        2. 批次上傳成功記錄到 GCS
        3. 批次插入成功記錄到 BigQuery
        
        Args:
            batch: 該批次的記錄列表
            batch_num: 批次號碼
            next_batch_publisher: 發布下一批訊息的回調（可選）
        """
        result = ProcessingResult()
        successful_records = []  # 收集成功的 API 呼叫結果
        
        # 第一階段：逐筆呼叫 API，收集成功的結果
        for record in batch:
            reference_id = record.get('reference_id') or record.get('referenceNumber') or "unknown"
            try:               
                # 只呼叫 API，不進行儲存
                api_result = self._call_credolab_api(record)
                successful_records.append(api_result)
                result.success_count += 1
                result.processed_references.append(reference_id)
                    
            except CredolabAPIError as e:
                # 處理 API 相關錯誤，記錄 HTTP 狀態碼
                result.error_count += 1
                status_code = str(getattr(e, 'status_code', 'unknown'))
                _logger.log_text(f"API error processing reference {reference_id} in batch {batch_num}: {str(e)}", severity="Info")
                result.errors.append({
                    "reference_id": reference_id,
                    "error": str(e),
                    "status_code": status_code,
                    "batch_num": batch_num
                })
                # 將失敗記錄寫入重試列表，包含 HTTP 狀態碼
                self.bq_service.insert_failed_record(record, status_code, str(e))
                
            except Exception as e:
                # 處理其他類型的錯誤
                result.error_count += 1
                _logger.log_text(f"Error processing reference {reference_id} in batch {batch_num}: {str(e)}", severity="Info")
                result.errors.append({
                    "reference_id": reference_id,
                    "error": str(e),
                    "batch_num": batch_num
                })
                # 將失敗記錄寫入重試列表，狀態碼為 'failed'
                self.bq_service.insert_failed_record(record, "failed", str(e))
        
        # 第二階段：批次上傳和插入成功的記錄
        if successful_records:
            
            # GCS上傳
            try:
                self._batch_upload_to_gcs(successful_records)
            except Exception as e:
                _logger.log_text(f"Error uploading batch {batch_num} to GCS: {str(e)}", severity="Error")
            
            # BQ上傳
            try:
                self._batch_insert_to_bigquery(successful_records)
            except Exception as e:
                _logger.log_text(f"Error inserting batch {batch_num} to BigQuery: {str(e)}", severity="Error")
            
        
        # 在整個批次所有 API 呼叫和儲存完成後，僅在非最後一批次時發布下一批次訊息
        if next_batch_publisher and not is_last_batch:
            try:
                message_id = next_batch_publisher()
                if message_id:
                    print(f"Batch {batch_num} summary: {result.success_count} records processed and saved in batch mode")
            except Exception as e:
                # 記錄詳細的錯誤資訊
                _logger.log_text(f"CRITICAL: Failed to publish next batch message after batch {batch_num} completed: {str(e)}", severity="Error")
                print(f"  Batch {batch_num + 1} will NOT be processed!")
                print(f"  Current batch: {batch_num}")
        
        return result
    
    def _batch_upload_to_gcs(self, successful_records: List[Dict[str, Any]]) -> None:
        """批次上傳多筆記錄到 Google Cloud Storage
        
        Args:
            successful_records: 成功的記錄列表，每個元素包含 vmb_record 和 api_response
        """
        if not successful_records:
            return
        
        file_list = []
        date_str = datetime.now().strftime("%Y-%m-%d")
        blob_path = self.config.gcs_blob_path
        
        for record in successful_records:
            vmb_record = record['vmb_record']
            reference_id = record['reference_id']
            device_os = vmb_record.get("device_os", "unknown").lower()
            
            file_content = json.dumps(vmb_record, ensure_ascii=False, default=str)
            file_name = f"{blob_path}/{date_str}_{device_os}_{reference_id}.json"
            
            file_list.append({
                'blob_name': file_name,
                'data': file_content,
                'content_type': 'application/json'
            })
        
        # 批次上傳
        uploaded_uris = self.gcs_service.batch_upload_to_gcs(
            file_list=file_list,
            bucket_name=self.config.gcs_bucket_name
        )
        
        print(f"Batch successfully uploaded {len(uploaded_uris)} files to GCS")
    
    def _batch_insert_to_bigquery(self, successful_records: List[Dict[str, Any]]) -> None:
        """批次插入多筆記錄到 BigQuery
        
        Args:
            successful_records: 成功的記錄列表，每個元素包含 vmb_record 和 api_response
        """
        if not successful_records:
            return
        
        # 按照 device_os 分組
        android_rows = []
        ios_rows = []
        
        for record in successful_records:
            vmb_record = record['vmb_record']
            api_response = record['api_response']
            device_os = vmb_record.get("device_os", "").lower()
            
            processed_data = prepare_raw_data_for_bq(vmb_record, api_response)
            
            if device_os == "android":
                android_rows.append(processed_data)
            elif device_os == "ios":
                ios_rows.append(processed_data)
            else:
                print(f"Warning: Unknown device_os: {device_os}")
        
        # 批次插入 Android 資料
        if android_rows:
            table_id = self.config.bq_credolab_table_android
            self.bq_service.insert_rows(table_id, android_rows)
        
        # 批次插入 iOS 資料
        if ios_rows:
            table_id = self.config.bq_credolab_table_ios
            self.bq_service.insert_rows(table_id, ios_rows)