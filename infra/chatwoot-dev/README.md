# Local Chatwoot Dev Stack

This stack runs a disposable Chatwoot instance for WootPilot development and
manual integration testing.

It starts Chatwoot, Sidekiq, Postgres, and Redis through Docker Compose. The
stack does not define persistent volumes. Running `down` removes containers, and
running `reset` removes containers plus any anonymous volumes.

## Requirements

- Docker with Compose v2.
- Enough local memory for Chatwoot, Postgres, and Redis.

## Start

```sh
./scripts/chatwoot-dev-up
```

Open Chatwoot at:

```text
http://localhost:3000
```

The first boot can take a few minutes while Docker pulls the image and Chatwoot
prepares the database.

## First-Run Setup

1. Open `http://localhost:3000`.
2. Create the first Chatwoot account and user.
3. Create or open an inbox for local testing.
4. Create an API access token from the Chatwoot user profile.
5. Point WootPilot at the local Chatwoot URL and token.

Suggested WootPilot settings:

```text
WOOTPILOT_CHATWOOT_BASE_URL=http://localhost:3000
WOOTPILOT_CHATWOOT_API_TOKEN=<local-user-api-token>
WOOTPILOT_CHATWOOT_ACCOUNT_ID=<local-account-id>
```

## Stop

```sh
./scripts/chatwoot-dev-down
```

## Reset

```sh
./scripts/chatwoot-dev-reset
```

This removes the local Chatwoot containers and starts from an empty database.

## Logs

```sh
./scripts/chatwoot-dev-logs
```

## Configuration

The default Chatwoot image is pinned in `compose.yml`:

```text
chatwoot/chatwoot:v4.14.1
```

Override it from the shell when needed:

```sh
CHATWOOT_IMAGE=chatwoot/chatwoot:v4.14.1 ./scripts/chatwoot-dev-up
```

Override the host port when `3000` is already in use:

```sh
CHATWOOT_PORT=3300 \
CHATWOOT_FRONTEND_URL=http://localhost:3300 \
./scripts/chatwoot-dev-up
```
