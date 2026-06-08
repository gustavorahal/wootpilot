# Slice 0: Runnable Skeleton

## Running Outcome

- The service starts locally and exposes a health endpoint.
- The local SQLite database profile can be created and migrated.
- Disposable local Chatwoot starts through Docker Compose for manual
  integration testing.
- Tests and linting can run in CI and locally.

## Implementation Scope

- Create Python package.
- Add FastAPI app.
- Add settings foundation for database, logging, bot mode defaults, and local
  development. Reserve real OpenRouter provider settings for Slice 5 unless a
  config placeholder is needed earlier.
- Add `.env.example`, `.env.public-dev.example`, and ignored `.env.local`
  loading through `pydantic-settings`.
- Add health route.
- Add lint/test tooling.
- Add Dockerfile.
- Maintain disposable local Chatwoot Docker Compose stack for manual
  integration testing.
- Set Python 3.14 as the primary runtime and configure CI for supported Python
  versions.
- Add SQLite database profile for local development.
- Add Alembic baseline migration.
- Add minimal `Clock` and `IdGenerator` ports.

## Required Tests

- `GET /health` returns a successful response.
- Settings load from environment variables and test overrides.
- Settings load from `.env.local` and `WOOTPILOT_*` environment variables, with
  explicit test overrides that do not mutate global process state.
- Public-dev settings parse `https://chat.gmrahal.net` as the Chatwoot public
  and local API base URL, and parse Chatwoot-native webhook signature header
  names.
- SQLite database initializes from an empty file.
- Alembic applies the baseline migration to an empty SQLite database.
- Local Chatwoot Compose configuration validates with `docker compose config`.
- Chatwoot dev helper scripts pass shell syntax checks.
- Unit test, lint, and type-check commands run in CI.

## Manual Verification

- Start the app locally.
- Call `GET /health`.
- Run the baseline migration against a new local SQLite database.
- Start local Chatwoot with `./scripts/chatwoot-dev-up`.
- Open `http://localhost:3000` and complete the local onboarding when manual
  Chatwoot integration testing is needed.
- Confirm `GET http://localhost:3000/` returns a successful response or
  redirects to onboarding.
