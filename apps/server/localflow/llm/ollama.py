import json
import httpx
from pydantic import ValidationError
from ..core.config import settings
from .provider import LLMProvider
from .schemas import DraftResponse

SYSTEM_PROMPT = """You are LocalFlow Assistant.
Return ONLY valid JSON matching this schema:
{
  "assistant_message": "string",
  "draft": { "type": "email|routine|code|linkedin", "title": "string", "content": "string" },
  "tool_plan": { "actions": [ { "tool": "open_links", "risk": "LOW|MEDIUM|HIGH", "params": { ... } } ] } | null
}
No markdown, no extra text.
"""

class OllamaProvider(LLMProvider):
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    async def generate_draft(self, mode: str, user_message: str) -> DraftResponse:
        prompt = f"{SYSTEM_PROMPT}\nMODE: {mode}\nUSER: {user_message}\n"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4},
        }

        r = await self.client.post(f"{self.base_url}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
        raw = (data.get("response") or "").strip()

        try:
            obj = json.loads(raw)
            return DraftResponse.model_validate(obj)
        except (json.JSONDecodeError, ValidationError) as e:
            # TODO (Phase 2): bounded "repair loop" prompt.
            raise RuntimeError(f"LLM output invalid: {e}")