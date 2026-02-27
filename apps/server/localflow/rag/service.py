from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]{2,}", (text or "").lower())


_QUERY_STOPWORDS = {
    "find",
    "search",
    "locate",
    "where",
    "is",
    "are",
    "the",
    "a",
    "an",
    "of",
    "for",
    "in",
    "on",
    "to",
    "my",
    "local",
    "pc",
    "computer",
    "disk",
    "drive",
    "file",
    "files",
    "folder",
    "folders",
    "directory",
    "document",
    "documents",
}


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _extract_drive_hints(query: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in re.findall(r"\b([a-zA-Z]):\b", query or ""):
        drive = f"{m.upper()}:\\"
        if drive not in seen:
            seen.add(drive)
            out.append(drive)
    return out


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def _dot(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


@dataclass
class RagHit:
    path: str
    score: float
    snippet: str


class RagService:
    """
    Minimal local-first RAG service:
    - User-approved folder permissions
    - Local chunk index on disk (JSONL)
    - Lightweight local embeddings via hashed token vectors
    """

    def __init__(
        self,
        store_dir: str,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        embedding_dim: int = 384,
    ) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.permissions_path = self.store_dir / "permissions.json"
        self.index_path = self.store_dir / "index.jsonl"
        self.meta_path = self.store_dir / "index_meta.json"
        self.chunk_size = max(400, chunk_size)
        self.chunk_overlap = max(50, min(chunk_overlap, self.chunk_size // 2))
        self.embedding_dim = max(128, embedding_dim)
        self.allowed_ext = {
            ".txt",
            ".md",
            ".rst",
            ".json",
            ".csv",
            ".log",
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".sql",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".xml",
            ".html",
            ".css",
            ".sh",
            ".ps1",
            ".bat",
        }
        self.media_ext = {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".webp",
            ".tif",
            ".tiff",
            ".heic",
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
            ".webm",
        }
        self.ignored_dirs = {
            ".git",
            ".hg",
            ".svn",
            "node_modules",
            ".venv",
            "venv",
            "__pycache__",
            ".idea",
            ".vscode",
            "dist",
            "build",
            "target",
            "coverage",
        }

    def _read_json(self, path: Path, default: dict) -> dict:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_json(self, path: Path, obj: dict) -> None:
        path.write_text(json.dumps(obj, ensure_ascii=True, indent=2), encoding="utf-8")

    def _load_permissions(self) -> list[str]:
        data = self._read_json(self.permissions_path, {"roots": []})
        roots = data.get("roots")
        if not isinstance(roots, list):
            return []
        out: list[str] = []
        for root in roots:
            if isinstance(root, dict) and isinstance(root.get("path"), str):
                out.append(_norm_path(root["path"]))
            elif isinstance(root, str):
                out.append(_norm_path(root))
        return sorted(set(out))

    def list_permissions(self) -> list[str]:
        return self._load_permissions()

    def list_available_drives(self) -> list[str]:
        drives: list[str] = []
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            p = f"{c}:\\"
            if os.path.exists(p):
                drives.append(p)
        return drives

    def is_path_allowed(self, path: str) -> bool:
        p = _norm_path(path)
        for root in self._load_permissions():
            if self._is_under_root(p, root):
                return True
        return False

    def set_permissions(self, roots: list[str]) -> list[str]:
        cleaned: list[str] = []
        for root in roots:
            p = _norm_path(root)
            if not os.path.isdir(p):
                raise ValueError(f"Path must be an existing directory: {root}")
            if p not in cleaned:
                cleaned.append(p)
        self._write_json(
            self.permissions_path,
            {"roots": [{"path": p, "granted_at": utc_iso()} for p in cleaned]},
        )
        return cleaned

    def list_subdirs(self, path: str | None, *, limit: int = 300) -> list[str]:
        """
        Return immediate child directories for a given path.
        If path is None/empty, return available drive roots.
        """
        if not path:
            return self.list_available_drives()
        p = Path(_norm_path(path))
        if not p.exists() or not p.is_dir():
            raise ValueError("Path must be an existing directory")
        out: list[str] = []
        try:
            for child in p.iterdir():
                if not child.is_dir():
                    continue
                name = child.name.lower()
                if name in self.ignored_dirs:
                    continue
                out.append(str(child.resolve()))
                if len(out) >= limit:
                    break
        except PermissionError:
            return []
        return sorted(out)

    def grant_permission(self, path: str) -> list[str]:
        root = _norm_path(path)
        if not os.path.isdir(root):
            raise ValueError("Permission path must be an existing directory")
        data = self._read_json(self.permissions_path, {"roots": []})
        roots = data.get("roots")
        if not isinstance(roots, list):
            roots = []
        cleaned: dict[str, dict] = {}
        for item in roots:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                cleaned[_norm_path(item["path"])] = item
        if root not in cleaned:
            cleaned[root] = {"path": root, "granted_at": utc_iso()}
        self._write_json(self.permissions_path, {"roots": list(cleaned.values())})
        return sorted(cleaned.keys())

    def revoke_permission(self, path: str) -> list[str]:
        root = _norm_path(path)
        current = self._load_permissions()
        kept = [p for p in current if p != root]
        self._write_json(
            self.permissions_path,
            {"roots": [{"path": p, "granted_at": utc_iso()} for p in kept]},
        )
        return kept

    def _is_under_root(self, path: str, root: str) -> bool:
        try:
            return Path(path).resolve().is_relative_to(Path(root).resolve())
        except Exception:
            p = _norm_path(path).lower()
            r = _norm_path(root).lower().rstrip("\\/")
            return p == r or p.startswith(r + os.sep)

    def _iter_files(self, roots: Iterable[str], max_files: int) -> Iterable[str]:
        count = 0
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d.lower() not in self.ignored_dirs]
                for fname in filenames:
                    ext = Path(fname).suffix.lower()
                    if ext not in self.allowed_ext:
                        continue
                    full = _norm_path(os.path.join(dirpath, fname))
                    yield full
                    count += 1
                    if count >= max_files:
                        return

    def _iter_all_files(self, roots: Iterable[str], max_files: int) -> Iterable[str]:
        count = 0
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d.lower() not in self.ignored_dirs]
                for fname in filenames:
                    full = _norm_path(os.path.join(dirpath, fname))
                    yield full
                    count += 1
                    if count >= max_files:
                        return

    def _read_text(self, path: str, max_bytes: int = 1_500_000) -> str:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return ""
        if p.stat().st_size > max_bytes:
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def _chunk_text(self, text: str) -> list[str]:
        s = (text or "").strip()
        if not s:
            return []
        if len(s) <= self.chunk_size:
            return [s]
        out: list[str] = []
        step = self.chunk_size - self.chunk_overlap
        i = 0
        while i < len(s):
            chunk = s[i : i + self.chunk_size].strip()
            if chunk:
                out.append(chunk)
            i += step
        return out

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.embedding_dim
        for tok in _tokenize(text):
            idx = hash(tok) % self.embedding_dim
            vec[idx] += 1.0
        return _normalize(vec)

    def rebuild_index(self, *, roots: list[str] | None = None, max_files: int = 1500) -> dict:
        allowed = self._load_permissions()
        if roots:
            wanted = [_norm_path(r) for r in roots]
            for r in wanted:
                if r not in allowed:
                    raise ValueError(f"Root is not approved: {r}")
            roots_to_use = wanted
        else:
            roots_to_use = allowed

        if not roots_to_use:
            raise ValueError("No approved roots. Grant folder permission first.")

        rows: list[dict] = []
        files_indexed = 0
        chunks_indexed = 0
        for path in self._iter_files(roots_to_use, max_files=max_files):
            text = self._read_text(path)
            chunks = self._chunk_text(text)
            if not chunks:
                continue
            files_indexed += 1
            mtime = Path(path).stat().st_mtime
            for idx, chunk in enumerate(chunks):
                rows.append(
                    {
                        "id": f"{path}::{idx}",
                        "path": path,
                        "mtime": mtime,
                        "chunk_index": idx,
                        "snippet": chunk[:700],
                        "embedding": self._embed(chunk),
                    }
                )
            chunks_indexed += len(chunks)

        with self.index_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")

        self._write_json(
            self.meta_path,
            {
                "roots": roots_to_use,
                "files_indexed": files_indexed,
                "chunks_indexed": chunks_indexed,
                "indexed_at": utc_iso(),
            },
        )
        return self.status()

    def _load_rows(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        out: list[dict] = []
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    out.append(row)
        return out

    def status(self) -> dict:
        meta = self._read_json(self.meta_path, {})
        return {
            "approved_roots": self._load_permissions(),
            "index_exists": self.index_path.exists(),
            "index_meta": meta,
        }

    def search(self, query: str, *, top_k: int = 5, roots: list[str] | None = None) -> list[RagHit]:
        q = (query or "").strip()
        if not q:
            return []

        allowed = self._load_permissions()
        if roots:
            filtered_roots = [_norm_path(r) for r in roots]
            for r in filtered_roots:
                if not any(self._is_under_root(r, a) for a in allowed):
                    raise ValueError(f"Root is not approved: {r}")
        else:
            filtered_roots = allowed

        if not filtered_roots:
            return []

        rows = self._load_rows()
        if not rows:
            return []

        qvec = self._embed(q)
        scored: list[RagHit] = []
        for row in rows:
            path = row.get("path")
            emb = row.get("embedding")
            snippet = row.get("snippet")
            if not isinstance(path, str) or not isinstance(emb, list) or not isinstance(snippet, str):
                continue
            if not any(self._is_under_root(path, r) for r in filtered_roots):
                continue
            emb_f = [float(x) for x in emb]
            score = _dot(qvec, emb_f)
            if score <= 0:
                continue
            scored.append(RagHit(path=path, score=score, snippet=snippet))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[: max(1, min(top_k, 12))]

    def find_files(
        self,
        query: str,
        *,
        top_k: int = 8,
        roots: list[str] | None = None,
        max_files_scan: int = 450000,
    ) -> list[RagHit]:
        q = (query or "").strip().lower()
        if not q:
            return []

        allowed = self._load_permissions()
        if roots:
            filtered_roots = [_norm_path(r) for r in roots]
            for r in filtered_roots:
                if not any(self._is_under_root(r, a) for a in allowed):
                    raise ValueError(f"Root is not approved: {r}")
        else:
            filtered_roots = allowed

        if not filtered_roots:
            return []

        drive_hints = _extract_drive_hints(query)
        if drive_hints:
            filtered_roots = [
                r for r in filtered_roots if any(_norm_path(r).lower().startswith(d.lower()) for d in drive_hints)
            ]
            if not filtered_roots:
                return []

        q_tokens = {
            t
            for t in _tokenize(q)
            if len(t) >= 3 and t not in _QUERY_STOPWORDS and not t.isdigit()
        }
        if not q_tokens:
            return []
        q_compact = _compact(q)
        wants_images = any(w in q for w in ["photo", "photos", "picture", "pictures", "image", "images"])
        wants_docs = any(w in q for w in ["document", "documents", "pdf", "doc", "docx", "txt"])

        scored: list[RagHit] = []
        relaxed: list[RagHit] = []
        for path in self._iter_all_files(filtered_roots, max_files=max_files_scan):
            p = path.lower()
            name = Path(path).name.lower()
            ext = Path(path).suffix.lower()
            path_tokens = set(_tokenize(p))
            overlap = len(q_tokens & path_tokens)
            compact_path = _compact(p)
            compact_overlap = sum(1 for tok in q_tokens if _compact(tok) and _compact(tok) in compact_path)
            overlap_total = overlap + compact_overlap
            if overlap_total == 0 and q_compact and q_compact not in compact_path:
                continue
            coverage = overlap_total / max(1, len(q_tokens))

            score = float(overlap_total)
            if wants_images and (ext in self.media_ext or any(seg in p for seg in ["\\pictures\\", "\\photos\\", "\\dcim\\"])):
                score += 2.0
            if wants_docs and ext in {".pdf", ".doc", ".docx", ".txt", ".md"}:
                score += 1.5
            if name in q or any(tok and tok in name for tok in q_tokens):
                score += 1.0
            if q_compact and q_compact in compact_path:
                score += 1.2
            score += coverage
            if len(path) < 140:
                score += 0.2

            hit = RagHit(path=path, score=score, snippet=f"Matched path: {path}")
            if coverage >= 0.34:
                scored.append(hit)
            else:
                relaxed.append(hit)

        scored.sort(key=lambda x: x.score, reverse=True)
        if scored:
            return scored[: max(1, min(top_k, 20))]
        relaxed.sort(key=lambda x: x.score, reverse=True)
        return relaxed[: max(1, min(top_k, 20))]
