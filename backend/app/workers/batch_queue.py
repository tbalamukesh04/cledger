import time
from typing import List, Dict, Any
from app.ai.config import MAX_BATCH_PAYLOAD_SIZE, AI_BATCH_TIMEOUT_SECONDS, AI_BATCH_SIZE

class BatchQueue:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self._last_flush_time = time.time()

    def add_message(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)

    def should_flush(self) -> bool:
        """
        Determines if the queue should be flushed based on:
        1. Batch size reached
        2. Max payload size reached
        3. Timeout reached since last flush
        """
        if not self.messages:
            return False
        
        if len(self.messages) >= AI_BATCH_SIZE:
            return True
        
        if len(self.messages) >= MAX_BATCH_PAYLOAD_SIZE:
            return True
        
        time_elapsed = time.time() - self._last_flush_time
        if time_elapsed >= AI_BATCH_TIMEOUT_SECONDS:
            return True
        
        return False

    def flush(self) -> List[Dict[str, Any]]:
        """
        Returns the current batch and resets the queue.
        """
        batch = self.messages.copy()
        self.messages.clear()
        self._last_flush_time = time.time()
        return batch

    @property
    def current_size(self) -> int:
        return len(self.messages)
        