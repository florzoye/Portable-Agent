# 🤖 PortableAgent

A modular AI-powered Telegram bot with Google Calendar integration, LangGraph agents, persistent memory, and Celery-based reminders and follow-ups.

---

## ✅ Features

### Ready
- 📅 **Google Calendar API integration** — create, update, search and delete events via natural language
- ⏰ **Reminder & task management** — schedule reminders and follow-ups through MCP tools
- 🧠 **User-specific memory** — persistent conversation history across sessions (PostgreSQL)
- 💬 **Telegram Chat Bot interface** — powered by aiogram + LangGraph ReAct agent
- 🐳 **Dockerized deployment** — easy self-hosting with a single `docker compose up`

### Upcoming / In Planning
- 🔍 **Hybrid RAG** (dense + sparse) for smart retrieval
- 📈 **Quant/Trading sub-agent**
- 🎯 **Polymarket API integration** (prediction markets)
- 📊 **Lifetime activity tracker**
- 🖥️ **Custom chatbot UI**
- 🐙 **GitHub commit/activity tracker**

---

##  Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Telegram Bot                        │
│              (aiogram + LangGraph agent)                │
└────────────┬───────────────────────┬────────────────────┘
             │                       │
     ┌───────▼──────┐       ┌────────▼─────────┐
     │  MCP Calendar │       │  MCP Reminders   │
     │   (port 8002) │       │   (port 8003)    │
     └───────┬───────┘       └────────┬─────────┘
             │                        │
     ┌───────▼───────┐       ┌────────▼─────────┐
     │FastAPI Calendar│       │  Celery Worker   │
     │   (port 8001) │       │  + Celery Beat   │
     └───────┬───────┘       └────────┬─────────┘
             │                        │
     ┌───────▼────────────────────────▼─────────┐
     │           PostgreSQL + Redis              │
     └───────────────────────────────────────────┘
```

### Services

| Service | Port | Description |
|---|---|---|
| `fastapi-calendar` | 8001 | Google Calendar REST API |
| `mcp-calendar` | 8002 | MCP server wrapping Calendar API via SSE |
| `mcp-reminders` | 8003 | MCP server for scheduling reminders and follow-ups |
| `telegram-bot` | — | aiogram bot with LangGraph agent |
| `celery-worker` | — | Async task execution |
| `celery-beat` | — | Periodic task scheduling |
| `postgres` | 5432 | Persistent storage + LangGraph checkpoints |
| `redis` | 6379 | Celery broker and result backend |

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
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
docker compose up --build
```

### 3. Start chatting

Open your bot in Telegram and send any message. The agent will respond using the configured LLM.

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

# Services
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
│   │   ├── llms/
│   │   │   ├── initializer.py       # Dynamic LLM module loader
│   │   │   ├── ollama_llm.py        # Ollama LLM wrapper
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
│   │   └── telegram/
│   │       └── bot/
│   │           ├── dependencies.py  # DI (agent, tools)
│   │           ├── handlers.py      # aiogram message handlers
│   │           └── main.py          # Bot entry point
│   └── tasks/
│       ├── celery_app.py            # Celery app + Beat schedule
│       └── tasks.py                 # Task definitions
├── data/
│   ├── configs/
│   │   ├── base_config.py           # Base config
│   │   ├── callbacks_config.py      # LangSmith/Langfuse config
│   │   ├── database_config.py       # DB config
│   │   ├── google_config.py         # Google OAuth config
│   │   ├── llm_config.py            # LLM base config
│   │   ├── ollama_config.py         # Ollama config
│   │   ├── openai_config.py         # OpenAI config
│   │   ├── redis_config.py          # Redis config
│   │   └── tg_config.py             # Telegram config
│   └── init_configs.py              # App-wide config initialization
├── db/
│   ├── sqlalchemy/
│   │   ├── google_crud.py           # Google token CRUD (PostgreSQL)
│   │   ├── models.py                # SQLAlchemy ORM models
│   │   ├── session.py               # DB session management
│   │   └── user_crud.py             # User CRUD (PostgreSQL)
│   ├── sqlite/
│   │   ├── google_crud.py           # Google token CRUD (SQLite)
│   │   ├── manager.py               # SQLite manager
│   │   ├── schemas.py               # SQLite schemas
│   │   └── user_crud.py             # User CRUD (SQLite)
│   ├── database.py                  # DB abstraction layer
│   └── database_protocol.py        # DB protocol/interface
├── utils/
│   ├── client_session.py            # Async HTTP client
│   ├── const.py                     # Ports, URLs, shared constants
│   ├── helpers.py                   # Utility functions
│   ├── metaclasses.py               # Metaclasses
│   ├── model_selector.py            # Interactive/auto LLM selector
│   └── setup_logger.py              # Logger setup
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

---

## 🧠 Agent

The bot uses a **LangGraph ReAct agent** with:

- **Persistent memory** via `AsyncPostgresSaver` (PostgreSQL checkpointer)
- **MCP tools** — Google Calendar and Reminders tools loaded at startup
- **Dynamic LLM selection** — auto-selects the first available LLM in Docker, interactive selection in TTY

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

## 📅 Celery Tasks

| Task | Trigger | Description |
|---|---|---|
| `send_reminder` | On demand (via MCP tool) | Sends a reminder message to a user |
| `followup_after_event` | On demand | Agent generates and sends a follow-up question |
| `check_finished_events` | Every 5 minutes | Checks for events that ended 10–20 min ago, triggers follow-ups (deduped via Redis) |
| `morning_digest` | Daily at 09:00 UTC | Agent sends a summary of the day's events |

---

## 🔐 Google Calendar Auth

1. User sends any message to the bot
2. Bot checks if user is authorized
3. If not, agent calls `get_auth_url` and sends the link
4. User opens the link and grants access
5. Google redirects to `http://localhost:8001/calendar/oauth/callback`
6. Token is saved; subsequent requests work automatically

---

## 🛠 Development

### Run a single service

```bash
docker compose up --build mcp-reminders
```

### View logs

```bash
docker compose logs -f telegram-bot
docker compose logs -f celery-worker
```

### Rebuild after code changes

```bash
docker compose up --build
```

### Access the database

```bash
docker exec -it portableagent-postgres-1 psql -U postgres -d portableagent
```

---

## 🧩 Adding a New LLM

1. Create `src/agents/llms/your_llm.py` with a class named `GetYourLLM`
2. Implement `get_llm()` returning a LangChain chat model
3. Implement `__repr__()` returning a display name
4. The `LLMInitializer` will pick it up automatically on next startup

---

## 📝 Notes

- **Timezone**: Celery Beat runs in UTC. Morning digest at 09:00 UTC = 12:00 Moscow time.
- **Memory**: Agent conversation history is stored per `tg_id` in PostgreSQL.
- **Model selection**: Without a TTY (Docker), the first LLM in the list is selected automatically. In a terminal, an interactive selector is shown.
- **OpenAI**: Requires network access. If blocked, use Ollama instead.
- **MCP_REMINDERS_HOST**: Must be set to `mcp-reminders` in `.env` — required for the bot to connect to the reminders service.