# LocalFlow

LocalFlow is a local, privacy-first drafting assistant with human approval gates.

It includes:
- `apps/server`: FastAPI backend that generates drafts and enforces approval before tool execution.
- `apps/desktop/ui`: React + Vite UI for chat, draft editing, approval, and execution.
- `apps/desktop/src-tauri`: Tauri shell for desktop packaging.

## Features

- Conversation-based chat and draft generation
- Draft edit + approve workflow
- Approval ID locking before execution
- Tool execution endpoint (currently includes `open_links`)
- Conversation history and detail APIs

## Repo Structure

- `apps/server/localflow/main.py`: FastAPI app entrypoint
- `apps/server/localflow/api/v1`: Versioned REST endpoints
- `apps/server/localflow/llm`: LLM provider + prompts
- `apps/server/localflow/storage`: DB models and migrations
- `apps/desktop/ui/src`: Web UI

## Requirements

- Python 3.11+
- Node.js 18+
- Ollama running locally (`http://127.0.0.1:11434`)
- (Optional) Rust toolchain for Tauri desktop app

## Quick Start

### 1. Start Ollama

Make sure Ollama is running and your selected model is available.

### 2. Run backend (FastAPI)

From repo root:

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

### 3. Run desktop UI (Vite)

In a second terminal:

```powershell
cd apps/desktop/ui
npm install
npm run dev
```

UI expects backend at `http://127.0.0.1:7878/v1`.

## Environment Variables

Server settings are loaded from `apps/server/.env` via `pydantic-settings`.

Common keys:
- `APP_NAME` (default: `LocalFlow`)
- `ENV` (default: `dev`)
- `DATABASE_URL` (default: `sqlite:///./localflow.db`)
- `LLM_PROVIDER` (default: `ollama`)
- `OLLAMA_BASE_URL` (default: `http://127.0.0.1:11434`)
- `OLLAMA_MODEL` (default: `qwen2.5:3b-instruct`)
- `LLM_TIMEOUT_S` (default: `120`)
- `PROMPT_PACK_DIR` (default: `localflow/llm/prompt_packs/default`)
- `API_KEY` (optional)

Example `apps/server/.env`:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:3b-instruct
```

## API Summary

Base URL: `http://127.0.0.1:7878/v1`

- `GET /health`
- `POST /chat`
- `POST /drafts/{draft_id}/update`
- `POST /drafts/{draft_id}/approve`
- `POST /executions`
- `GET /conversations?limit=&offset=`
- `GET /conversations/{conversation_id}`

## Tests

From `apps/server`:

```powershell
pytest
```

## Notes

- `README.md` at repo root documents the monorepo.
- Local DB files and `.env` are gitignored.
- Build artifacts (`dist`, `target`, `node_modules`) are gitignored.
