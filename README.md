# AI Research Assistant — Backend

A production-shaped FastAPI backend for an AI research assistant: JWT auth, a
LangGraph-orchestrated RAG chat pipeline, document ingestion into ChromaDB, and
SSE token streaming. Built as a modular monolith — each concern (auth,
research, documents) is independently maintainable behind a repository +
service layer, with routes kept thin.

## Stack

- **FastAPI** + **Uvicorn**, fully async
- **SQLAlchemy 2.x (async)** + **PostgreSQL** + **Alembic** migrations
- **JWT** auth (access + refresh) via `PyJWT`, **Passlib/bcrypt** hashing
- **Pydantic v2** schemas
- **LangGraph** for the research workflow orchestration
- **LiteLLM** for provider-agnostic LLM calls (OpenAI / Groq / Gemini)
- **ChromaDB** for vector storage
- **pypdf** / **python-docx** for document parsing
- **Redis** (wired for caching/rate-limit backing; see Notes)
- **Loguru** for structured logging
- **Docker Compose** for local orchestration (API + Postgres + Redis + Chroma)

## Architecture

```
app/
  core/            # config, security (JWT/hashing), logging, exceptions
  database/        # async engine/session, declarative base, portable GUID type
  models/          # SQLAlchemy models: User, ResearchSession, Message, Document, ResearchReport
  schemas/         # Pydantic request/response models
  repositories/    # Data access — one repository per model, generic base class
  services/        # Business logic — AuthService, ResearchService, DocumentService, SettingsService
  api/v1/          # Thin route handlers, grouped by resource
  agents/
    llm/           # LiteLLM provider abstraction (model routing, streaming)
    rag/           # parser.py, chunking.py, embeddings.py, vector_store.py
    graph/         # LangGraph workflow: planner -> retriever -> generator -> guardrail -> evaluator
  middleware/       # global exception handling, request logging, rate limiting
  utils/            # file storage helper
alembic/            # async-aware migrations
tests/               # pytest + httpx, run against in-memory SQLite
```

**Layering rule:** routes call services; services call repositories (+ agents
for AI work); repositories touch the DB. Business logic never lives in a
route handler.

## Research workflow (LangGraph)

```
START -> planner -> (retriever, if needed) -> generator -> guardrail -> evaluator -> END
```

- **Planner** — heuristically decides if the query needs document retrieval
  (explicit `document_ids`, or retrieval-hinting language in the query).
- **Retriever** — embeds the query, searches ChromaDB scoped to the user
  (and optionally specific documents), filters by a relevance threshold.
- **Generator** — builds the prompt (system + retrieved context + recent
  conversation history + the new question) and calls the selected LLM.
- **Guardrail** — checks for empty output, prompt-injection patterns, a
  small toxic-term list, and (when retrieval ran) lexical grounding against
  the retrieved chunks.
- **Evaluator** — computes heuristic faithfulness/relevance scores. Latency
  and token usage are captured by the calling service.

The `POST /api/v1/research/chat` endpoint streams tokens over SSE as they're
generated (via `research_service.stream_chat`, which reuses the same node
functions as the compiled graph in `agents/graph/workflow.py`), then runs
guardrail + evaluator on the completed answer, saves the message and a
`ResearchReport` row, and emits a final `citations` event followed by
`[DONE]` — this exactly matches the SSE contract the companion Next.js
frontend expects.

## REST API

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create an account, returns tokens |
| POST | `/api/v1/auth/login` | Returns tokens |
| POST | `/api/v1/auth/refresh` | Exchange a refresh token for a new pair |
| GET | `/api/v1/auth/me` | Current user |
| POST | `/api/v1/research/chat` | **SSE** streaming chat |
| GET | `/api/v1/research/history` | List sessions |
| POST | `/api/v1/research/session` | Create an empty session |
| GET | `/api/v1/research/session/{id}` | Session + messages |
| PATCH | `/api/v1/research/session/{id}` | Rename |
| DELETE | `/api/v1/research/session/{id}` | Delete |
| POST | `/api/v1/documents/upload` | Upload PDF/DOCX/TXT, indexes in the background |
| GET | `/api/v1/documents` | List documents |
| DELETE | `/api/v1/documents/{id}` | Delete (and de-index) |
| GET | `/api/v1/models` | Available models + current selection |
| PUT | `/api/v1/models` | Change default model |

Interactive docs at `/docs` once running.

## Getting started

### With Docker (recommended)

```bash
cp .env.example .env
# fill in OPENAI_API_KEY (and/or GROQ_API_KEY, GEMINI_API_KEY)
docker compose up --build
```

This starts Postgres, Redis, ChromaDB, and the API (which runs
`alembic upgrade head` on boot). API available at `http://localhost:8000`.

For a production-style local deployment, use:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This omits pgAdmin, disables the public docs UI in production, and keeps the
service set focused on the application dependencies.

### Locally

```bash
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # point DATABASE_URL at a local Postgres, set API keys
alembic upgrade head
uvicorn app.main:app --reload
```

### Tests

```bash
pytest -v
```

Tests run against an in-memory SQLite database (see `tests/conftest.py`), so
they need no external services. Models use a portable `GUID` TypeDecorator
(native `UUID` on Postgres, `CHAR(36)` elsewhere) and generic `JSON` columns
so the same model definitions work on both backends.

## Notes / things a real deployment should add next

- **Redis is wired into the stack but not yet used for caching or as the
  rate-limit backend** — `slowapi`'s limiter currently uses in-memory
  storage. Point it at `settings.REDIS_URL` before scaling past one process.
- **Guardrails and evaluation are heuristic** (lexical overlap, regex
  patterns, a short toxic-term list) rather than model-based, by design —
  they're fast and dependency-free. Swap in a moderation model or an
  LLM-as-judge call behind the same node interface for higher fidelity.
- **The initial Alembic migration was written by hand**, not autogenerated
  (no live Postgres was available in the environment this was built in).
  Run `alembic revision --autogenerate -m "check"` against a real database
  once and diff it against `0001_initial_schema.py` to confirm they match.
- **File storage is local disk** (`utils/file_storage.py`). Swap for S3/GCS
  by replacing that module — nothing else depends on the filesystem directly.
- **CORS origins, JWT secret, and API keys** all come from `.env` — make sure
  `JWT_SECRET_KEY` is a long random value in any real deployment.

## Deploying on Render

This repo includes a root-level `render.yaml` blueprint that deploys the API
and a separate private Chroma service backed by a persistent disk.

### What it creates

- `researcher-api` - Docker-based FastAPI service from `server/Dockerfile`
- `researcher-chroma` - private Docker image service using `chromadb/chroma`

### Chroma setup

- Chroma persists data under `/data`
- Keep the Chroma server and Python client on the same `1.5.x` release line
- The API reads `CHROMA_HOST` and `CHROMA_PORT` from the Chroma service's
  private network address
- If you prefer a public Chroma endpoint, set `CHROMA_URL` instead

### Before first deploy

Set these secret values in Render for the API service:

- `DATABASE_URL`
- `REDIS_URL` if you use Redis
- `FRONTEND_URL`
- `BACKEND_CORS_ORIGINS`
- `JWT_SECRET_KEY`
- `OPENAI_API_KEY` / `GROQ_API_KEY` / `GEMINI_API_KEY`
- `GOOGLE_CLIENT_ID`
- `SENTRY_DSN`

If you deploy the frontend to Vercel, point `FRONTEND_URL` and
`BACKEND_CORS_ORIGINS` to that domain before shipping.
# Researcher-Backend
