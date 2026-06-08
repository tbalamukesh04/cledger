from abc import ABC, abstractmethod
from app.schemas.preprocessing import ProcessingContext
from app.ai.llm_extraction.extraction_models import TransactionExtractionResult

class ILLMExtractionService(ABC):
    """
    Standardized contract for the LLM extraction module.
    Ensures the worker pipeline interacts with a stable interface.
    """
    
    @abstractmethod
    def extract_transaction(
        self, 
        normalized_text: str, 
        raw_message_id: int, 
        processing_context: ProcessingContext
    ) -> TransactionExtractionResult:
        """
        Receives normalized text and metadata, returning a structured extraction result.
        """
        pass