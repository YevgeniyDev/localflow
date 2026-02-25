from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from .schemas import DraftResponse

class LLMProvider(ABC):
    @abstractmethod
    async def generate_draft(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> DraftResponse:
        raise NotImplementedError
