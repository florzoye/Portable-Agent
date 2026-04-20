# 🤖 PortableAgent

A modular AI-powered assistant with Google Calendar integration, LangGraph agents, persistent memory, and Celery-based reminders and follow-ups. Accessible via **Telegram bot** and a **Web UI**.

---

## ✅ Features

### Ready
- 📅 **Google Calendar API integration** — create, update, search and delete events via natural language
- ⏰ **Reminder & task management** — schedule reminders and follow-ups through MCP tools
- 🧠 **User-specific memory** — persistent conversation history across sessions (PostgreSQL)
- 💬 **Telegram Chat Bot interface** — powered by aiogram + LangGraph ReAct agent
- 🖥️ **Web Chat UI** — browser-based chat interface with WebSocket streaming (FastAPI + uvicorn)
- 🐳 **Dockerized deployment** — modular compose files, easy self-hosting

### Upcoming / In Planning
- 🔍 **Hybrid RAG** (dense + sparse) for smart retrieval
- 🎯 **Polymarket API integration** (prediction markets)
- 📊 **Lifetime activity tracker**
- 🐙 **GitHub commit/activity tracker**

---

## Architecture

```
┌──────────────────────┐    ┌──────────────────────┐
│    Telegram Bot      │    │    Web Assistant      │
│  (aiogram + agent)   │    │  (FastAPI + WS + UI)  │
└────────┬─────────────┘    └──────────┬────────────┘
         │                             │
         └──────────────┬──────────────┘
                        │
           ┌────────────▼────────────┐
           │     LangGraph Agent     │
           │   (ReAct + MCP tools)   │
           └──────┬──────────┬───────┘
                  │          │
     ┌────────────▼──┐  ┌────▼─────────────┐
     │  MCP Calendar │  │  MCP Reminders   │
     │  (port 8002)  │  │  (port 8003)     │
     └───────┬───────┘  └────────┬─────────┘
             │                   │
     ┌───────▼───────┐  ┌────────▼─────────┐
     │FastAPI Calendar│ │  Celery Worker   │
     │  (port 8001)  │  │  + Celery Beat   │
     └───────┬───────┘  └────────┬─────────┘
             │                   │
     ┌───────▼───────────────────▼──────────┐
     │         PostgreSQL + Redis           │
     └──────────────────────────────────────┘
```

### Services

| Service | Host port (dev) | Container port | Description |
|---|---|---|---|
| `fastapi-calendar` | 8001 | 8001 | Google Calendar REST API |
| `mcp-calendar` | 8002 | 8002 | MCP server wrapping Calendar API via SSE |
| `mcp-reminders` | 8003 | 8003 | MCP server for scheduling reminders and follow-ups |
| `telegram-bot` | — | — | aiogram bot with LangGraph agent |
| `web-assistant` | 8080 | 8000 | Browser-based chat UI with WebSocket |
| `celery-worker` | — | — | Async task execution |
| `celery-beat` | — | — | Periodic task scheduling |
| `flower` | 5555 | 5555 | Celery monitoring UI |
| `postgres` | — | 5432 | Persistent storage + LangGraph checkpoints |
| `redis` | — | 6379 | Celery broker and result backend |

> Host ports are only exposed in dev mode (via `docker-compose.override.yml`).

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- `make` (optional but recommended)
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Google OAuth 2.0 credentials
- Ollama running locally (or an OpenAI API key)

### 1. Clone and configure

```bash
git clone <repo-url>
cd PortableAgent
cp .env.example .env
```

Edit `.env` with your credentials (see [Environment Variables](#environment-variables) below).

### 2. Run

```bash
make build
```

Or without `make`:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.core.yml \
  -f docker-compose.apps.yml \
  -f docker-compose.workers.yml \
  -f docker-compose.override.yml \
  up -d --build
```

### 3. Open the interfaces

- **Telegram**: open your bot and send any message
- **Web UI**: `http://localhost:8080`
- **Flower** (Celery monitor): `http://localhost:5555`

---

## 🐳 Docker Compose Structure

The project uses **split compose files** that can be combined depending on what you need:

| File | Contents |
|---|---|
| `docker-compose.yml` | Base infra — postgres, redis, flower, shared networks & volumes |
| `docker-compose.core.yml` | Core services — fastapi-calendar, mcp-calendar, mcp-reminders |
| `docker-compose.apps.yml` | App services — telegram-bot, web-assistant |
| `docker-compose.workers.yml` | Background workers — celery-worker, celery-beat |
| `docker-compose.override.yml` | Dev overrides — exposes ports to the host machine |

### Makefile commands

```bash
make build   # Build images and start the full stack with dev ports
make up      # Start the full stack without rebuilding
make dev     # Alias for up
make down    # Stop all services
make logs    # Tail logs from all services
make core    # Start only infra + core services (no apps, no workers)
```

#### Compose presets used internally

```
COMPOSE_BASE = docker-compose.yml + docker-compose.core.yml
COMPOSE_FULL = COMPOSE_BASE + docker-compose.apps.yml + docker-compose.workers.yml
COMPOSE_DEV  = COMPOSE_FULL + docker-compose.override.yml   ← used by make build/up/down/logs
```

### Running individual services

```bash
# Only infra + core (no bot, no workers, no ports)
make core

# Web assistant only (with all its dependencies, dev ports)
docker compose \
  -f docker-compose.yml -f docker-compose.core.yml \
  -f docker-compose.apps.yml -f docker-compose.override.yml \
  up -d web-assistant

# Telegram bot only
docker compose \
  -f docker-compose.yml -f docker-compose.core.yml \
  -f docker-compose.apps.yml -f docker-compose.override.yml \
  up -d telegram-bot
```

---

## ⚙️ Environment Variables

```env
# Telegram
BOT_TOKEN=your_bot_token

# Google OAuth
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8001/calendar/oauth/callback

# Database
DB_NAME=portableagent
DB_USER=postgres
DB_PASSWORD=your_db_password
DB_HOST=postgres
DB_PORT=5432

# Redis
REDIS_PASSWORD=your_redis_password
REDIS_HOST=redis
REDIS_PORT=6379

# Services (internal Docker hostnames — do not change unless remapping)
FASTAPI_CALENDAR_HOST=fastapi-calendar
FASTAPI_CALENDAR_PORT=8001
MCP_CALENDAR_HOST=mcp-calendar
MCP_CALENDAR_PORT=8002
MCP_REMINDERS_HOST=mcp-reminders
MCP_REMINDERS_PORT=8003

# Ollama (local LLM)
OLLAMA_MODEL=your_model_name

# OpenAI (optional)
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=your_model_name

# xAI Grok (optional)
XAI_API_KEY=your_xai_api_key
XAI_MODEL=your_model_name

# LLM config
TEMPERATURE=0.1
MAX_TOKENS=30000
TOP_P=0.7
TIMEOUT=60
VERBOSE=False

# Observability (optional)
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=your_project_name
LANGFUSE_SECRET_KEY=your_langfuse_secret
LANGFUSE_PUBLIC_KEY=your_langfuse_public
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

---

## 📁 Project Structure

```
PortableAgent/
├── src/
│   ├── agents/
|   |   ├── chat/
|   |   |   ├── base.py              # Base class for WebSocket Reciever 
|   |   |   └── invoker.py           # Invoker for invoke agents response 
│   │   ├── llms/
│   │   │   ├── initializer.py       # Dynamic LLM module loader
│   │   │   ├── ollama_llm.py        # Ollama LLM wrapper
|   |   |   ├── grok_llm.py          # Grok LLM wrapper
│   │   │   └── openai_llm.py        # OpenAI LLM wrapper
│   │   ├── prompts/
│   │   │   └── system.py            # Agent system prompt
│   │   └── tools/
│   │       ├── calendar.py          # MCP calendar client
│   │       └── reminders.py         # MCP reminders client
│   ├── enum/
│   │   ├── db.py                    # DB type enum
│   │   └── timeframe.py             # Timeframe enum
│   ├── exceptions/
│   │   ├── base.py                  # Base exception classes
│   │   ├── config_exp.py            # Config exceptions
│   │   ├── repo_exp.py              # Repository exceptions
│   │   └── services_exp.py          # Service exceptions
│   ├── factories/
│   │   ├── agents_factory.py        # LangGraph agent factory
│   │   ├── checkpointer_factory.py  # AsyncPostgresSaver singleton
│   │   ├── middleware_factory.py    # Middleware factory
│   │   ├── repository_factory.py    # Repository factory
│   │   └── service.py               # Service factory
│   ├── models/
│   │   ├── events.py                # Event models
│   │   ├── google.py                # Google OAuth models
│   │   ├── return_message.py        # Response message models
│   │   ├── token_model.py           # Token models
│   │   ├── user_model.py            # User models
│   │   └── user_response.py         # User response models
│   ├── services/
│   │   ├── base.py                  # Base service class
│   │   ├── calendar/
│   │   │   ├── auth_service.py      # Google OAuth flow
│   │   │   ├── calendar_service.py  # Calendar business logic
│   │   │   ├── creds_manager.py     # Credentials manager
│   │   │   ├── google_calendar.py   # Google Calendar API wrapper
│   │   │   ├── token_service.py     # Token management
│   │   │   ├── mcp/
│   │   │   │   ├── models.py        # MCP request/response models
│   │   │   │   ├── run.py           # MCP server entrypoint
│   │   │   │   └── server.py        # MCP tools & resources
│   │   │   └── server/
│   │   │       ├── dependencies.py  # FastAPI dependencies
│   │   │       ├── google_calendar_api.py  # FastAPI router
│   │   │       └── run.py           # FastAPI entrypoint
│   │   ├── reminders/
│   │   │   └── mcp/
│   │   │       ├── run.py           # MCP server entrypoint
│   │   │       └── server.py        # Reminders MCP tools
│   │   ├── telegram/
│   │   │   └── bot/
│   │   │       ├── dependencies.py  # DI (agent, tools)
│   │   │       ├── handlers.py      # aiogram message handlers
│   │   │       └── main.py          # Bot entry point
│   │   └── web/
│   │       ├── app.py               # FastAPI app + WebSocket endpoint
│   │       ├── dependencies.py      # DI (agent per session)
│   │       ├── main.py              # Web assistant entry point
│   │       └── static/
│   │           └── index.html       # Browser chat UI
│   └── tasks/
│       ├── celery_app.py            # Celery app + Beat schedule
│       └── tasks.py                 # Task definitions
├── data/
│   ├── configs/                     # Per-service config classes
│   └── init_configs.py              # App-wide config initialization
├── db/
│   ├── sqlalchemy/                  # PostgreSQL or SQLite CRUD + ORM models
│   ├── database.py                  # DB abstraction layer
│   └── database_protocol.py         # DB protocol/interface
├── utils/
│   ├── client_session.py            # Async HTTP client
│   ├── const.py                     # Ports, URLs, shared constants
│   ├── helpers.py                   # Utility functions
│   ├── metaclasses.py               # Metaclasses
│   ├── model_selector.py            # Interactive/auto LLM selector
│   └── setup_logger.py              # Logger setup
├── docker-compose.yml               # Base infra (postgres, redis, flower)
├── docker-compose.core.yml          # Core services (calendar APIs, MCP servers)
├── docker-compose.apps.yml          # App services (telegram-bot, web-assistant)
├── docker-compose.workers.yml       # Background workers (celery-worker, celery-beat)
├── docker-compose.override.yml      # Dev port overrides
├── Makefile                         # Compose shortcuts
├── Dockerfile                       # Single image for all services (uv + Python 3.12)
└── pyproject.toml
```

---

## 🧠 Agent

Both the Telegram bot and the Web UI share the same **LangGraph ReAct agent** with:

- **Persistent memory** via `AsyncPostgresSaver` (PostgreSQL checkpointer)
- **MCP tools** — Google Calendar and Reminders tools loaded at startup
- **Dynamic LLM selection** — auto-selects the first available LLM in Docker, interactive selection in TTY
- **Session isolation** — Telegram uses `tg_id` as `thread_id`; Web UI uses a random 8-digit numeric `session_id`

### Available Tools (via MCP)

**Calendar:**
- `get_events` — upcoming events for N days
- `get_events_by_date` — events on a specific date
- `get_events_range` — events in a date range
- `search_events` — full-text event search
- `get_event` — event details by ID
- `create_event` — create a new event
- `update_event` — update an existing event
- `delete_event` — delete an event
- `get_auth_url` — get Google OAuth link
- `check_auth` — check authorization status

**Reminders:**
- `create_reminder` — schedule a reminder message at a given time
- `create_followup` — schedule a follow-up question after an event ends

---

## 🖥️ Web Assistant

A browser-based chat interface that mirrors the Telegram bot experience.

- Served at `http://localhost:8080` in dev mode (container port 8000, mapped via override)
- Communicates with the agent over WebSocket (`/ws/{session_id}`)
- Session ID is a random 8-digit number, generated in the browser and stored in `sessionStorage`
- Agent responses are rendered as HTML (markdown converted server-side)
- Shares the same MCP tools, LLM, and PostgreSQL checkpointer as the Telegram bot

---

## 📅 Celery Tasks

| Task | Trigger | Description |
|---|---|---|
| `send_reminder` | On demand (via MCP tool) | Sends a reminder message to a user |
| `followup_after_event` | On demand | Agent generates and sends a follow-up question |
| `check_finished_events` | Every 5 minutes | Checks for events that ended 10–20 min ago, triggers follow-ups (deduped via Redis) |
| `morning_digest` | Daily at 09:00 UTC | Agent sends a summary of the day's events |

---

## 🔐 Google Calendar Auth

1. User sends any message to the bot (Telegram or Web)
2. Bot checks if user is authorized
3. If not, agent calls `get_auth_url` and sends the link
4. User opens the link and grants access
5. Google redirects to `http://localhost:8001/calendar/oauth/callback`
6. Token is saved; subsequent requests work automatically

---

## 🧩 Adding a New LLM

1. Create `src/agents/llms/your_llm.py` with a class named `GetYourLLM`
2. Implement `get_llm()` returning a LangChain chat model
3. Implement `__repr__()` returning a display name
4. The `LLMInitializer` will pick it up automatically on next startup

---

## 📝 Notes

- **Timezone**: Celery Beat runs in UTC. Morning digest at 09:00 UTC = 12:00 Moscow time.
- **Memory**: Agent conversation history is stored per `tg_id` / `session_id` in PostgreSQL.
- **Model selection**: Without a TTY (Docker), the first LLM in the list is selected automatically. In a terminal, an interactive selector is shown.
- **OpenAI**: Requires network access. If blocked, use Ollama instead.
- **Port exposure**: Host ports are only exposed in dev mode via `docker-compose.override.yml`. For production, omit it from the compose command.
- **Web session persistence**: Web UI sessions persist across page reloads within the same browser tab (`sessionStorage`). Opening a new tab starts a fresh session.