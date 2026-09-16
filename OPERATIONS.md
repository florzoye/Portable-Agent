# Production operations runbook

This runbook describes the hosted deployment of PortableAgent. Keep secrets in
the deployment secret store or environment, never in this file, shell history,
logs, or monitoring payloads.

## Service topology

The production stack contains:

- `web-assistant` and `telegram-bot`: tenant-facing transports and agent
  orchestration.
- `fastapi-calendar`: internal calendar REST API; do not publish its port.
- `mcp-calendar` and `mcp-reminders`: internal MCP tool services.
- `celery-worker` and `celery-beat`: asynchronous and scheduled work.
- PostgreSQL: application data and LangGraph checkpoints.
- Redis: broker, result backend, sessions, cooldowns, and short-lived state.
- `monitoring`: operational events and dashboard. Its SQLite file is separate
  from the application PostgreSQL database in the default compose setup.

Only the Web UI, monitoring dashboard, and deliberately configured public
entrypoints should be exposed through a reverse proxy. Calendar REST and MCP
services must remain on the internal Docker network and continue to require
`INTERNAL_API_KEY` where configured.

## First deployment

1. Create a production `.env` from `.env.example` and replace every
   placeholder. Set `DB_TYPE=postgres`, the PostgreSQL connection values,
   `WEB_COOKIE_SECURE=true`, a long random `INTERNAL_API_KEY`, and a
   `TOKEN_ENCRYPTION_KEY` generated once with:

   ```bash
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Restrict `.env` permissions and load secrets through the platform secret
   manager when available. Never reuse development credentials.

3. Start infrastructure and wait for PostgreSQL and Redis health checks:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.core.yml \
     -f docker-compose.apps.yml -f docker-compose.workers.yml up -d
   ```

4. Run the schema check before serving traffic:

   ```bash
   docker compose exec web-assistant \
     uv run python -m db.sqlalchemy.migration_cli check
   ```

5. Upgrade a new or pending database, then check it again:

   ```bash
   docker compose exec web-assistant \
     uv run python -m db.sqlalchemy.migration_cli upgrade
   docker compose exec web-assistant \
     uv run python -m db.sqlalchemy.migration_cli check
   ```

6. Verify `/health` for Web and monitoring, then send a test Telegram
   `/web` login and confirm that the one-time code works.

Migrations must run before application traffic is enabled. They are
idempotent, but only one deployment job should perform an upgrade at a time.

## Backup and recovery

Create a consistent PostgreSQL backup before every migration and before
rotating secrets:

```bash
docker compose exec -T postgres pg_dump \
  -U "$DB_USER" -d "$DB_NAME" --format=custom \
  > backups/portableagent-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Store backups outside the host running the containers and test restoration
regularly. Do not print `DB_PASSWORD` or include it in a command line.

To restore into a stopped application stack:

```bash
docker compose stop web-assistant telegram-bot celery-worker celery-beat
cat backups/portableagent-YYYYMMDDTHHMMSSZ.dump | \
  docker compose exec -T postgres pg_restore \
    -U "$DB_USER" -d "$DB_NAME" --clean --if-exists
docker compose exec web-assistant \
  uv run python -m db.sqlalchemy.migration_cli check
docker compose start web-assistant telegram-bot celery-worker celery-beat
```

Restore the Redis data only when the incident requires it. Redis contains
short-lived state and can normally be recreated; restoring stale sessions or
cooldowns can reintroduce expired authentication state.

## Fernet key preservation and rotation

`TOKEN_ENCRYPTION_KEY` encrypts user provider keys and stored credentials.
Losing it makes existing encrypted values unrecoverable. Keep the active key
in the secret manager and include it in the disaster-recovery record.

Changing the key directly is not a rotation: it makes existing credentials
undecryptable. For a planned rotation:

1. Back up PostgreSQL and verify the backup.
2. Stop profile mutations and application traffic.
3. Run a dedicated re-encryption procedure that reads with the old key and
   writes with the new key. Do not implement this by blindly replacing values.
4. Deploy the new key and verify representative profiles with local and
   upstream diagnostics.
5. Keep the old key only for the controlled migration window, then revoke it.

If no re-encryption procedure is available, preserve the old key and ask users
to recreate credentials only as an explicit data-loss fallback.

## Monitoring and provider setup

- Set `MONITORING_URL` and `MONITORING_API_KEY` on Web and Telegram services.
- Keep the monitoring API private or protect it with its API key.
- Back up `MONITORING_DB_PATH` if monitoring history is operationally
  important; it is not a replacement for PostgreSQL backups.
- Ollama is operator-managed. Confirm its endpoint/model availability before
  enabling it for tenants.
- OpenAI and xAI user keys are encrypted per tenant. Never put them in
  compose files, diagnostics, audit events, support tickets, or logs.
- Use the authenticated model-profile diagnostic endpoint for validation.
  Upstream checks are rate-limited; local checks do not spend provider tokens.

## Rollback

Application rollback is safe only when the previous application version is
compatible with the current schema. For a code-only rollback, deploy the
previous image and run its schema check before reopening traffic.

If a migration is not backward-compatible, do not downgrade the schema in
place. Stop traffic, restore the pre-migration PostgreSQL backup into a
controlled database, deploy the matching previous application version, and
verify health, Telegram login, Web sessions, and a representative model
diagnostic before switching traffic back.

Record the deployed image, migration version, backup identifier, and
verification results for every release.
