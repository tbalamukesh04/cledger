# backend/app/schemas/parsing_metadata.py
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime, timezone

class ParsingMetadata(BaseModel):
    """
    Structured metadata format for storing scoring and classification results.
    Designed for compatibility with PostgreSQL JSONB columns.
    """
    score: int = Field(..., description="The computed score from the deterministic scoring engine")
    threshold: int = Field(..., description="The threshold used to determine if it is a transaction candidate")
    is_transaction: bool = Field(..., description="True if the message score met or exceeded the threshold")
    rule_breakdown: Dict[str, int] = Field(..., description="Detailed breakdown of points awarded/deducted per rule")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="The exact time this metadata was generated")
    
    ai_extraction: Optional[Dict[str, Any]] = Field(default=None, description="Container for AI extraction metadata")

    def to_jsonb(self) -> Dict[str, Any]:
        """
        Serializes the Pydantic model into a fully JSON-compatible dictionary.
        Automatically handles datetime conversions to ISO-8601 strings.
        """
        return self.model_dump(mode='json')