from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ..core.config import settings

@dataclass(frozen=True)
class PromptPack:
    system: str
    repair: str

class PromptManager:
    """
    Loads prompts from a directory (prompt pack).
    This is 'product-grade' because:
      - prompts are editable without code changes
      - can support multiple packs later
      - cached in memory (loaded once at startup)
    """
    def __init__(self, pack_dir: str | None = None):
        self.pack_dir = Path(pack_dir or settings.prompt_pack_dir)
        self.pack: PromptPack = self._load_pack(self.pack_dir)

    def _read(self, p: Path) -> str:
        if not p.exists():
            raise FileNotFoundError(f"Missing prompt file: {p}")
        return p.read_text(encoding="utf-8").strip()

    def _load_pack(self, pack_dir: Path) -> PromptPack:
        system = self._read(pack_dir / "system.txt")
        repair = self._read(pack_dir / "repair.txt")

        return PromptPack(system=system, repair=repair)

    def get_system(self) -> str:
        return self.pack.system

    def get_repair(self) -> str:
        return self.pack.repair
