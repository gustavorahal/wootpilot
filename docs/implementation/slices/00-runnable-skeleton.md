# Slice 0: Runnable Skeleton

## Running Outcome

- The service starts locally and exposes a health endpoint.
- The local SQLite database profile can be created and migrated.
- Tests and linting can run in CI and locally.

## Implementation Scope

- Create Python package.
- Add FastAPI app.
- Add settings, including OpenRouter model-provider settings.
- Add health route.
- Add lint/test tooling.
- Add Dockerfile.
- Add disposable local Chatwoot Docker Compose stack for manual integration
  testing.
- Set Python 3.14 as the primary runtime and configure CI for supported Python
  versions.
- Add SQLite database profile for local development.
- Add Alembic baseline migration.
- Add minimal `Clock` and `IdGenerator` ports.

## Required Tests

- `GET /health` returns a successful response.
- Settings load from environment variables and test overrides.
- SQLite database initializes from an empty file.
- Alembic applies the baseline migration to an empty SQLite database.
- Local Chatwoot Compose configuration validates with `docker compose config`.
- Chatwoot dev helper scripts pass shell syntax checks.
- Unit test, lint, and type-check commands run in CI.

## Manual Verification

- Start the app locally.
- Call `GET /health`.
- Run the baseline migration against a new local SQLite database.
- Start local Chatwoot with `./scripts/chatwoot-dev-up` when manual Chatwoot
  integration testing is needed.
