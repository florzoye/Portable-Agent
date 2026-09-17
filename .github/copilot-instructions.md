# Copilot instructions for PortableAgent

## Project commands

The project requires Python 3.13 and uses `uv` with the committed `uv.lock`.

### Tests

Run the full suite:

```bash
uv run python -m unittest discover -s tests -p "test*.py"
```

Run one test module:

```bash
uv run python -m unittest tests.test_comprehensive
```

Run one test class or method:

```bash
uv run python -m unittest tests.test_comprehensive.ComprehensiveTests
uv run python -m unittest tests.test_comprehensive.ComprehensiveTests.test_web_profile_transport_uses_cookie_owned_tenant
```

PostgreSQL integration tests are opt-in and require a reachable PostgreSQL
database:

```bash
$env:POSTGRES_TEST_URL="postgresql+asyncpg://user:password@host:5432/db"
uv run python -m unittest tests.test_postgres_integration
```

Without `POSTGRES_TEST_URL`, those tests are skipped.

### Validation and build

Run syntax/bytecode validation and whitespace validation:

```bash
uv run python -m compileall -q src db tests
git diff --check
```

The repository does not define a separate lint or type-check command. CI runs:

```bash
uv run --python 3.13 python -m unittest discover -s tests -p "test_*.py"
```

Build the application image:

```bash
docker compose -f docker-compose.yml -f docker-compose.core.yml \
  -f docker-compose.apps.yml build web-assistant
```

Run the development stack through the Makefile:

```bash
make build
make up
make down
make logs
make core
```

The Makefile's development preset includes `docker-compose.override.yml`,
which publishes Web, MCP, and Flower ports. Do not use that override for a
public deployment.

Migration commands run inside the application image:

```bash
uv run python -m db.sqlalchemy.migration_cli check
uv run python -m db.sqlalchemy.migration_cli upgrade
```

Migrations are ordered and idempotent. The current schema target is version 2.
Run `upgrade` before application traffic and then `check`; do not downgrade a
production schema in place.

## Architecture

PortableAgent is a multi-tenant Telegram-first assistant with a Web/FastAPI
transport. Telegram and Web share a LangGraph ReAct agent, MCP tools, provider
adapters, PostgreSQL persistence/checkpointing, and Redis-backed short-lived
state.

The main runtime path is:

```text
Telegram bot / Web FastAPI + WebSocket
    -> application composition and service facades
    -> LangGraph agent and AgentInvoker
    -> provider runtime model + MCP calendar/reminder tools
    -> PostgreSQL, Redis, Google Calendar, and Celery
```

The Docker deployment is split into:

- `docker-compose.yml`: PostgreSQL, Redis, Flower, network, and volumes.
- `docker-compose.core.yml`: internal Calendar REST and MCP services.
- `docker-compose.apps.yml`: Web, Telegram, and monitoring services.
- `docker-compose.workers.yml`: Celery worker and beat.
- `docker-compose.override.yml`: development host-port exposure only.

### Tenant and model flow

- Telegram user ID is the tenant identity used by profile repositories and
  runtime model creation. Do not substitute an internal database ID or a
  client-provided session label.
- Web login consumes a one-time Telegram code and stores
  `portable_session -> user_id` and `portable_session -> server thread_id` in
  Redis.
- Web profile routes and WebSocket `/ws` derive user/thread ownership only from
  the authenticated cookie and Redis session context.
- Active tenant profiles are constructed by `ModelProfileApplication` and
  `get_user_model`; fallback operator models are separate from tenant profiles.
- Session model selection clears/deactivates the tenant profile as appropriate.
- Runtime model caches must be invalidated after profile activation, deletion,
  or other credential-changing operations.

### Persistence and composition boundaries

- SQLAlchemy repositories own persistence operations; migrations own schema
  creation and upgrades.
- `db/sqlalchemy/migration_cli.py` is the operational entrypoint for
  `check`/`upgrade`.
- Transport handlers must not create schemas, choose ORM repositories, or
  construct provider registries.
- Shared dependencies and application services are composed in
  `src/services/dependencies.py` and related composition modules.
- PostgreSQL is the production database. SQLite is used for isolated unit
  tests and the monitoring compatibility path.
- Fernet-encrypted provider credentials are stored in the database. The
  `TOKEN_ENCRYPTION_KEY` must remain stable for existing data.

## Provider conventions

Provider integrations use `ModelProvider`, `ProviderCapabilities`,
`ProviderAdapter`, and the shared `ProviderRegistry`.

When adding a provider:

1. Add the enum/capabilities entry.
2. Implement local, token-free `validate`.
3. Implement `create_model` and normalize failures into the typed provider
   error hierarchy.
4. Register one adapter in `ProviderRegistry`.
5. Keep user keys in encrypted profile storage; never return or log them.
6. Run the shared contract helper in `tests/provider_contract.py` and add only
   provider-specific tests that the contract does not cover.

`health_check(check_upstream=False)` must remain local and must not construct
or invoke a provider client. Upstream diagnostics are explicit, token-using,
tenant-scoped, and rate-limited.

## Transport and security conventions

- Map invalid profile/configuration input to safe 4xx responses or friendly
  Telegram feedback.
- Cross-tenant profile access must look like not-found/denied and must never
  reveal whether another tenant's profile exists.
- WebSocket origin validation occurs before accepting `/ws`; allowed origins
  come from `CORS_ORIGINS`.
- Monitoring authentication is fail-closed: an unset `MONITORING_API_KEY` is
  a configuration error, not an unauthenticated mode.
- Never put API keys, Fernet keys, raw provider exceptions, prompts, or
  sensitive response headers in logs, audit events, diagnostics, or docs.
- Internal Calendar/MCP services require `INTERNAL_API_KEY` where configured
  and must remain off the public network.
- Preserve server-owned thread IDs for checkpointer and runtime isolation.
- Keep Telegram model setup deterministic and confirmation-gated; bounded
  guidance intents may explain/list providers but must not mutate profiles
  directly.
- Telegram navigation uses slash commands and inline service screens; do not
  reintroduce persistent reply keyboards.
- Chat mode is an explicit FSM state. While active, ordinary text goes to the
  tenant-resolved agent and only `/cancel` or the inline exit action leaves it.
- Calendar and reminders are agent-driven natural-language workflows, not
  Telegram CRUD handlers. Preserve server-owned tenant binding and require
  explicit intent before side effects.

## Test and change-location conventions

- Put broad cross-cutting regressions in `tests/test_comprehensive.py`.
- Put PostgreSQL-only behavior in `tests/test_postgres_integration.py`.
- Keep provider adapter contract coverage in `tests/test_provider_contracts.py`
  and `tests/provider_contract.py`.
- Prefer testing application-service boundaries with mocked provider adapters,
  then test transport ownership with server-session fixtures.
- Update `README.md` or `OPERATIONS.md` when changing provider setup,
  deployment order, migrations, recovery, or public routes.
- Keep changes bounded to the relevant layer: transport, application service,
  repository, provider adapter, or bootstrap/composition.
