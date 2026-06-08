# AGENTS.md

These rules apply to this entire repository.

## Very Important

- **ALPHA PHASE**: structural changes are welcome. Prefer the right architecture over local patches.
- This repository is a VERY EARLY WIP. Proposing sweeping changes that improve long-term maintainability is encouraged.
- When in doubt between duplicating logic and extracting shared logic, extract it.

## Reference Source Code

- The local Chatwoot source code lives in `../chatwoot` and can be used to investigate behavior, models, jobs, integrations, and self-hosting details.
- The local Chatwoot mobile app source code lives in `../chatwoot-mobile-app` and can be used to investigate the mobile agent experience.

## Code Documentation

- When writing code, add docstrings or inline documentation where they help humans understand intent, behavior, or rationale.
- Prefer documentation that explains why something exists, what assumptions or tradeoffs shaped it, and how it should be used.
- Public functions, classes, modules, non-obvious algorithms, domain rules, and important architectural boundaries should usually have docstrings.
- Avoid documentation that merely restates obvious implementation details. The goal is educational clarity, not noise.
- Treat code as something future contributors will learn from: it should be readable on its own, and documented where context would otherwise be lost.

## Validation

- For Python code changes, run `./scripts/dev-check` before calling the work done unless the change is docs-only or there is a clear blocker.
- For narrow edits, targeted checks are fine while iterating, but the final validation should include Ruff, Pyright, and pytest.
- Use `./scripts/release-check` before release-oriented changes or when touching packaging, migrations, deployment, security-sensitive code, or public-dev tooling.
- If any expected validation is skipped, say exactly what was skipped and why.

## Database Changes

- Do not add ad hoc schema upgrades to application startup.
- Any schema change that affects persisted tables must be represented as a proper Alembic migration.
- If Alembic is not configured yet, pause and propose adding Alembic rather than hiding migration logic in application code.

## Commits

- Commit messages must be explanatory, not just a short one-line message.
- Use an objective first line that summarizes the change.
- Include a body explaining context, main changes, and validation performed when applicable.
