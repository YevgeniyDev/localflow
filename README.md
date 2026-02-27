# LocalFlow

LocalFlow is a local-first AI assistant with a chat UI, draft approval gate, and controlled tool execution.

## Current Project State

- Backend: FastAPI (`apps/server`) with conversation storage, draft lifecycle, approval hashing, and tool execution policy.
- UI: React + Vite (`apps/desktop/ui`) with a ChatGPT-inspired layout, history sidebar, inline draft studio, and assistant message actions.
- Desktop shell: Tauri scaffolding exists (`apps/desktop/src-tauri`) for future packaging.
- Primary runtime today: local dev via Vite + FastAPI + Ollama.

## Implemented Features

### Chat + Drafting

- Conversational chat per conversation thread.
- Assistant response is persisted as a draft on every turn.
- Inline Draft Studio appears in chat only when relevant (task/deliverable intent or tool actions), not for generic conversational Q&A.
- Draft fields:
  - `title` (shown when needed, e.g. email-like requests)
  - `content`
- Conversation history list with previews and reload support.
- Conversation detail restores latest draft + latest tool plan.

### Assistant Message UX

- Copy assistant response (icon button + tooltip).
- Regenerate assistant response (icon button + tooltip).
- Regenerate replaces that assistant message in place.

### Approval Gate + Execution

- User can edit draft, then approve (`Approve`) to create hash-locked approval.
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

### Local RAG (Permissioned File Search)

- Local folder permission model (`/v1/rag/permissions/*`).
- Local chunk index (JSONL) built only from approved folders.
- Chat automatically uses top local hits as context when available.
- Assistant responses include a `Sources:` list when RAG context is used.

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
- If needed, falls back to safe generic behavior:
  - `browser_search` with normalized query
  - optional Google search URL in `open_links`

### UI/Design State

- ChatGPT-inspired dark layout and chat composer.
- Send button has loading spinner while request is in-flight.
- Send remains clickable-looking when idle; empty sends are ignored by handler.
- Dark rounded custom scrollbars across major scrollable surfaces.

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

- Improve tool-result grounding so assistant responses cite concrete found links more reliably.
- Add richer browser automation result surfaces in UI (step-by-step outcome cards).
- Add integration tests around tool-plan normalization and per-action confirmation flows.
- Package desktop runtime via Tauri once web UX is finalized.
