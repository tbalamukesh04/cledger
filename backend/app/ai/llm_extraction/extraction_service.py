import json
import logging
from typing import List, Optional
from datetime import datetime, timezone

from app.schemas.preprocessing import PreprocessedPayload
from app.ai.ai_parser import AIParser
from app.ai.batch_request_builder import build_batch_request_payload
from app.ai.llm_extraction.extraction_models import TransactionExtractionResult

logger = logging.getLogger(__name__)

class LLMExtractionService:
    def __init__(self):
        self.model_version = "gemini-2.5-flash"
        self.prompt_version = "v1.1"

    def extract_transaction_batch(
        self, 
        candidates: List[PreprocessedPayload]
    ) -> List[Optional[TransactionExtractionResult]]:
        """
        Wraps the underlying batch AI parser to return strictly typed Day 27 Extraction Models,
        with comprehensive structured logging for each extraction event.
        """
        if not candidates:
            return []
            
        # 1. Capture request timestamp
        request_timestamp = datetime.now(timezone.utc)
        
        logger.info(json.dumps({
            "event_type": "llm_batch_extraction_initiated",
            "batch_size": len(candidates),
            "model_version": self.model_version,
            "request_timestamp": request_timestamp.isoformat()
        }))
        
        # 2. Execute the batch API call
        parser = AIParser()
        batch_request = build_batch_request_payload(candidates)
        raw_results = parser.parse_batch(batch_request)
        
        # 3. Capture completion timestamp
        completion_timestamp = datetime.now(timezone.utc)
        
        final_results = []
        
        # 4. Map results and log structured extraction events
        for idx, res in enumerate(raw_results):
            candidate = candidates[idx]
            raw_msg_id = candidate.raw_message_id
            msg_hash = candidate.message_hash
            
            if res:
                final_res = TransactionExtractionResult(
                    amount=res.amount,
                    currency=res.currency,
                    transaction_verb=res.transaction_verb,
                    transaction_date=res.date,
                    counterparty=res.counterparty, 
                    reference=res.reference,       
                    confidence=res.confidence,
                    model_version=self.model_version,
                    prompt_version=self.prompt_version
                )
                final_results.append(final_res)
                
                # Log Success
                logger.info(json.dumps({
                    "event_type": "llm_extraction_event",
                    "raw_message_id": raw_msg_id,
                    "message_hash": msg_hash,
                    "extraction_request_timestamp": request_timestamp.isoformat(),
                    "extraction_completion_timestamp": completion_timestamp.isoformat(),
                    "extraction_status": "SUCCESS",
                    "extracted_fields": final_res.to_dict()
                }))
            else:
                final_results.append(None)
                
                # Log Failure / Null Return
                logger.warning(json.dumps({
                    "event_type": "llm_extraction_event",
                    "raw_message_id": raw_msg_id,
                    "message_hash": msg_hash,
                    "extraction_request_timestamp": request_timestamp.isoformat(),
                    "extraction_completion_timestamp": completion_timestamp.isoformat(),
                    "extraction_status": "FAILED_OR_NON_TRANSACTION",
                    "extracted_fields": None
                }))
                
        return final_results