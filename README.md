# LocalFlow

LocalFlow is a local-first AI assistant with a chat UI, draft approval gate, and controlled tool execution.

## Current Project State

- Backend: FastAPI (`apps/server`) with conversation storage, draft lifecycle, approval hashing, and tool execution policy.
- UI: React + Vite (`apps/desktop/ui`) with a ChatGPT-inspired layout, history sidebar, inline draft studio, and assistant message actions.
- Desktop shell: Tauri scaffolding exists (`apps/desktop/src-tauri`) for future packaging.
- Primary runtime today: local dev via Vite + FastAPI + Ollama.

## Major Implemented Features

### Conversational Chat + Conditional Drafting

- Conversational chat per conversation thread.
- Draft generation is conditional:
  - Draft Studio appears only for deliverable-style requests (email/post/reply/code-style outputs).
  - Generic Q&A stays in plain chat flow (no draft workflow forced).
- Draft fields:
  - `title` (shown when needed, e.g. email-like requests)
  - `content`
- Conversation history list with previews and reload support.
- Conversation detail restores latest draft + latest tool plan.

### Approval Gate + Audited Execution

- User edits draft, then approves (`Approve`) to create hash-locked approval.
- Execution is blocked unless:
  - draft hash matches approved hash,
  - tool plan hash matches approved hash,
  - tool input exactly matches an approved action in tool plan.
- Local execution audit is persisted (`Execution` records with request/result/meta timing).

### Tooling (Registered)

- `open_links`
- `search_web`
- `browser_search`
- `browser_automation`

### Permissioned Local File Search (RAG)

- Explicit File Search mode in chat input.
- Permission-first workflow before local disk access:
  - full access,
  - disk-only access,
  - advanced folder-path access.
- Permission scope is saved and can be reused on next enable.
- Local index is built only from approved roots and reused when scope is unchanged.
- File search can run as broad scan across approved roots (without requiring a folder hint).
- Search pipeline includes noise filtering (e.g., `node_modules`, `.git`, virtual env/build artifacts) and stronger filename/path token matching.

### Tool Policy Enforcement

- Risk-aware policy in execution service:
  - `LOW`: no extra confirmation
  - `MEDIUM/HIGH`: requires `confirmation` payload
- Browser automation requires explicit per-action confirmation:
  - `confirmation.approved_actions` must include each action `id`
  - `HIGH` risk additionally requires `confirmation.allow_high_risk=true`

### Chat Tool-Plan Normalization / Safety

- URL sanitization before persisting/executing `open_links` actions.
- Prevents trusting model-guessed LinkedIn profile slugs unless user supplied an explicit URL.
- If needed, falls back to safer generic behavior:
  - `browser_search` with normalized query
  - optional Google search URL in `open_links`

## Architecture

### Backend

- Entrypoint: `apps/server/localflow/main.py`
- API routes: `apps/server/localflow/api/v1`
- LLM providers:
  - Ollama provider
  - Gemini provider (supported, but subject to external quota/limits)
- Prompt packs loaded from directory (`prompt_pack_dir`)
- Tool registry bootstrapped in app lifespan

### Frontend

- Main chat route: `apps/desktop/ui/src/routes/App.tsx`
- Overlay route: `apps/desktop/ui/src/routes/Overlay.tsx`
- API client: `apps/desktop/ui/src/lib/api.ts`

## API Summary

Base URL: `http://127.0.0.1:7878/v1`

- `GET /health`
- `POST /chat`
- `POST /drafts/{draft_id}/update`
- `POST /drafts/{draft_id}/approve`
- `POST /executions`
- `GET /conversations?limit=&offset=`
- `GET /conversations/{conversation_id}`
- `GET /conversations/{conversation_id}/audit`
- `GET /rag/permissions`
- `POST /rag/permissions/grant`
- `POST /rag/permissions/revoke`
- `POST /rag/permissions/set`
- `GET /rag/drives`
- `POST /rag/list_dirs`
- `GET /rag/status`
- `POST /rag/index`
- `POST /rag/search`

## Environment Variables

Configured via `apps/server/.env` (`pydantic-settings`).

Core keys:

- `APP_NAME` (default `LocalFlow`)
- `ENV` (default `dev`)
- `DATABASE_URL` (default `sqlite:///./localflow.db`)
- `LLM_PROVIDER` (`ollama` or `gemini`)
- `LLM_TIMEOUT_S` (default `120`)
- `PROMPT_PACK_DIR` (default `localflow/llm/prompt_packs/default`)
- `CORS_ORIGINS` (optional; defaults include localhost dev origins)
- `RAG_STORE_DIR` (default `.localflow_rag`)
- `RAG_CHUNK_SIZE` (default `1200`)
- `RAG_CHUNK_OVERLAP` (default `200`)
- `RAG_EMBEDDING_DIM` (default `384`)

Ollama:

- `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (default `qwen2.5:3b-instruct`)

Gemini:

- `GEMINI_API_KEY`
- `GEMINI_MODEL` (default `gemini-2.0-flash`)

> Note: For local reliability and zero external quotas, Ollama is the recommended default.

Example `.env` (Ollama):

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:3b-instruct
```

## Quick Start

### 1. Start Ollama

Make sure Ollama is running and your model is pulled.

### 2. Start backend

```powershell
cd apps/server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn localflow.main:app --host 127.0.0.1 --port 7878 --reload
```

Health check:

```text
GET http://127.0.0.1:7878/v1/health
```

### 3. Start UI

```powershell
cd apps/desktop/ui
npm install
npm run dev
```

UI expects backend at `http://127.0.0.1:7878/v1`.

### 4. (Optional) Enable local RAG

Grant a folder:

```powershell
curl -X POST http://127.0.0.1:7878/v1/rag/permissions/grant -H "Content-Type: application/json" -d "{\"path\":\"D:\\\\Docs\"}"
```

Build index:

```powershell
curl -X POST http://127.0.0.1:7878/v1/rag/index -H "Content-Type: application/json" -d "{\"max_files\":1500}"
```

Try retrieval:

```powershell
curl -X POST http://127.0.0.1:7878/v1/rag/search -H "Content-Type: application/json" -d "{\"query\":\"project roadmap\",\"top_k\":5}"
```

Explore drives and directories for permission setup:

```powershell
curl http://127.0.0.1:7878/v1/rag/drives
curl -X POST http://127.0.0.1:7878/v1/rag/list_dirs -H "Content-Type: application/json" -d "{\"path\":\"C:\\\\Users\"}"
```

Set permission scope in one request:

```powershell
curl -X POST http://127.0.0.1:7878/v1/rag/permissions/set -H "Content-Type: application/json" -d "{\"paths\":[\"C:\\\\Users\\\\123\\\\Downloads\",\"D:\\\\Projects\"]}"
```

## Test / Validation

Server tests:

```powershell
cd apps/server
pytest
```

Frontend build:

```powershell
cd apps/desktop/ui
npm run build
```

## Near-Term Next Steps

- Improve ranking quality for ambiguous file names across very large approved roots.
- Add incremental/background re-index scheduling for large local corpora.
- Expand execution tests for file-search mode + permission transitions.
- Package desktop runtime via Tauri once web workflow is finalized.
