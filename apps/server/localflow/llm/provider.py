from abc import ABC, abstractmethod
from .schemas import DraftResponse

class LLMProvider(ABC):
    @abstractmethod
    async def generate_draft(self, mode: str, user_message: str) -> DraftResponse:
        raise NotImplementedError