# Production Readiness

This checklist records the minimum checks and operator notes for taking the
current WootPilot MVP from local/public-dev validation toward an alpha release.

## Default Release Check

Run the deterministic release gate before merging deployment changes:

```sh
./scripts/release-check
```

The default gate runs:

- `uv run ruff check .`
- `uv run pyright`
- `uv run pip-audit`
- `uv run pytest`
- `uv run wootpilot eval-golden`
- `uv run alembic upgrade head`
- `docker compose -f infra/chatwoot-dev/compose.yml config`
- a lightweight secret-marker review for committed fixtures and env templates

Run the public-dev readiness check when `.env.local` is configured for
`https://chat.gmrahal.net` and the laptop tunnel should be verified:

```sh
./scripts/release-check --public-dev
```

That adds `./scripts/public-dev-doctor`, which checks Chatwoot reachability,
webhook URL/subscriptions, local webhook secret matching, and local health.

Run the optional Postgres dependency smoke before enabling a production profile:

```sh
./scripts/release-check --postgres-extra
```

That command runs the default release gate and verifies that
`psycopg[binary]` and `langgraph-checkpoint-postgres` import through the
`wootpilot[postgres]` extra.

## Verification Strategy

The default verification path should stay fast, deterministic, and provider-free:
unit tests, ASGI route tests, repository tests, migration checks, linting,
type-checking, fixture validation, mocked HTTP integrations, and golden
conversation evals.

Opt-in integration checks may start local services such as Chatwoot Docker
Compose, Postgres, or the public-dev laptop tunnel. These checks prove wiring
and operator readiness; they should not become the correctness contract for
business behavior.

Manual smoke checks cover browser/UI inspection, public-dev Chatwoot at
`https://chat.gmrahal.net/`, Meta-connected message flow, and live provider
calls that require credentials or human judgment.

Never require real OpenRouter, WooCommerce, Chatwoot Cloud, or production
credentials in default CI. Live checks should prove integration wiring; the
correctness contract belongs in deterministic tests.

For code changes, "done" means the app still starts, automated checks pass, new
behavior has focused use-case coverage, schema changes include migrations, and
any non-automated behavior has explicit manual verification steps.

## Runtime Profiles

Local and public-dev laptop profile:

```text
WOOTPILOT_DB_URL=sqlite+aiosqlite:///./data/wootpilot-public-dev.db
WOOTPILOT_CHECKPOINTER=sqlite
WOOTPILOT_BOT_MODE=shadow
WOOTPILOT_LIMITED_AUTO_PRODUCTION_ALLOWED=false
```

SQLite enables WAL mode, foreign keys, and a busy timeout at connection time.
The SQLite LangGraph checkpointer uses a sibling database such as
`wootpilot-public-dev-checkpoints.db` so checkpoint writes do not contend with
application transactions.

Production profile:

```text
WOOTPILOT_DB_URL=postgresql+psycopg://wootpilot:...@db.example/wootpilot
WOOTPILOT_CHECKPOINTER=postgres
WOOTPILOT_LIMITED_AUTO_PRODUCTION_ALLOWED=true
```

Postgres is required for production public auto-send and multiple outbound
workers. Queue workers compile the dequeue query with
`FOR UPDATE SKIP LOCKED` on Postgres. Install the optional dependency profile
before enabling `WOOTPILOT_CHECKPOINTER=postgres`:

```sh
uv sync --extra postgres
```

## GMR Public-Dev Deployment Notes

The sibling infra repository documents the host:

```text
ssh deploy@167.172.143.73
app root: /srv/apps
repo: /srv/apps/repo
env root: /srv/apps/env
Chatwoot env: /srv/apps/env/platform/chatwoot.env
client envs: /srv/apps/env/clients/*.env
```

If WootPilot is deployed server-side beside Chatwoot, use:

```text
WOOTPILOT_CHATWOOT_BASE_URL=http://chatwoot-web:3000
WOOTPILOT_CHATWOOT_PUBLIC_URL=https://chat.gmrahal.net
WOOTPILOT_PUBLIC_BASE_URL=https://wootpilot.gmrahal.net
```

The internal Chatwoot URL keeps API calls on the Docker network while public
links and browser verification continue to use `https://chat.gmrahal.net`.

## Chatwoot Configuration

Required Chatwoot account webhook subscriptions:

```text
message_created
message_updated
conversation_updated
conversation_status_changed
```

Chatwoot must sign webhooks with:

```text
X-Chatwoot-Timestamp
X-Chatwoot-Signature
X-Chatwoot-Delivery
```

The configured Chatwoot API token must be able to:

- read account conversations for final public-send safety checks
- create private notes
- create public messages only when limited-auto is explicitly enabled

## Worker Operation

Run the outbound executor as a single worker on SQLite:

```sh
uv run wootpilot execute-outbound --limit 10
```

On Postgres, multiple workers may run because queued rows are selected with
`FOR UPDATE SKIP LOCKED`. Public message execution still performs final checks
for bot mode, content leakage, local human-active state, local pause/replyable
state, and fresh Chatwoot conversation safety.

## Rollback And Queue Draining

Before rollback or maintenance:

1. Set `WOOTPILOT_BOT_MODE=shadow`.
2. Stop outbound workers.
3. Confirm no queued actions remain:

```sh
sqlite3 ./data/wootpilot-public-dev.db \
  "select status, action_kind, count(*) from outbound_actions group by status, action_kind;"
```

4. If queued public actions exist, inspect them manually before restarting
   workers. Private-note actions are lower risk but should still be idempotent.
5. Apply rollback or migration changes.
6. Restart the API in shadow mode and run `./scripts/public-dev-doctor`.

## Manual Smoke Matrix

The deterministic tests are the correctness contract. Live smoke tests only
prove wiring:

- signed Chatwoot webhook intake through the tunnel
- shadow run creates an audited proposal and no outbound action
- copilot mode creates one private note and ignores the echo webhook
- limited-auto low-risk public send only after explicit approval
- human public reply suppresses later public automation
- `wootpilot-paused` blocks automation
- `wootpilot-auto-ok` permits a later eligible customer turn but does not bypass
  deterministic policy, replyability, pause, resolved-state, or content-safety
  rules

Keep live public replies disabled unless a specific conversation and message are
approved for testing.
