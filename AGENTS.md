# AGENTS.md

These rules apply to this entire repository.

## Very Important

- **ALPHA PHASE**: structural changes are welcome. Prefer the right architecture over local patches.
- This repository is a VERY EARLY WIP. Proposing sweeping changes that improve long-term maintainability is encouraged.
- When in doubt between duplicating logic and extracting shared logic, extract it.

## Reference Source Code

- The local Chatwoot source code lives in `../chatwoot` and can be used to investigate behavior, models, jobs, integrations, and self-hosting details.
- The local Chatwoot mobile app source code lives in `../chatwoot-mobile-app` and can be used to investigate the mobile agent experience.

## Code Quality Standards

- All Python code MUST include type hints and return types.
- Use descriptive, self-explanatory variable names.
- Attempt to break up complex functions that are more than 20 lines into smaller, focused functions where it makes sense.

```python
def filter_unknown_users(users: list[str], known_users: set[str]) -> list[str]:
    """Single line description of the function.

    Any additional context about the function can go here.

    Args:
        users: List of user identifiers to filter.
        known_users: Set of known/valid user identifiers.

    Returns:
        List of users that are not in the `known_users` set.
    """
```

## Testing Requirements

- New features and bugfixes should include tests unless the change is documentation-only or there is a clear reason tests would not add value.
- Tests currently live under `tests/`. Keep test files organized by behavior or module, following existing project patterns.
- Prefer fast, deterministic tests that do not make network calls.
- Use fakes, fixtures, recorded payloads, or local SQLite databases for external systems and persistence behavior.
- Do not add live network calls to the default test suite.
- If a test requires real external services, credentials, or long-running infrastructure, mark it explicitly and keep it out of the default `./scripts/dev-check` path.
- Use pytest as the testing framework; if in doubt, check other existing tests for examples.
- The test suite should fail when the behavior under test is broken.

Checklist:

- Tests fail when your new logic is broken.
- Happy path is covered.
- Edge cases and error conditions are tested.
- Fixtures or mocks are used for external dependencies.
- Tests are deterministic and not flaky.
- The test suite fails if your new logic is broken.

## Security and Risk Assessment

- Do not use `eval()`, `exec()`, or `pickle` on user-controlled input.
- Use proper exception handling. Do not use bare `except:`, and use a `msg` variable for error messages.
- Remove unreachable or commented-out code before committing.
- Consider race conditions and resource leaks, including file handles, sockets, and threads.
- Ensure proper resource cleanup for file handles, connections, and other external resources.

## Documentation Standards

- When writing code, add docstrings or inline documentation where they help humans understand intent, behavior, or rationale.
- Prefer documentation that explains why something exists, what assumptions or tradeoffs shaped it, and how it should be used.
- Public functions, classes, modules, non-obvious algorithms, domain rules, and important architectural boundaries should usually have docstrings.
- Avoid documentation that merely restates obvious implementation details. The goal is educational clarity, not noise.
- Treat code as something future contributors will learn from: it should be readable on its own, and documented where context would otherwise be lost.
- Use Google-style docstrings for public functions. Include `Args`, `Returns`, and `Raises` sections when they apply; do not add empty or filler sections.
- Put types in function signatures, NOT in docstrings.
- If a default is present, DO NOT repeat it in the docstring unless there is post-processing or the value is set conditionally.
- Document parameters, return values, and exceptions when doing so adds useful context beyond the type signature.
- Ensure American English spelling, for example `behavior`, not `behaviour`.
- Do NOT use Sphinx-style double backtick formatting like ``code``. Use single backticks such as `code` for inline code references in docstrings and comments.

### Module Public API

- Use `__all__` in modules that are intended to expose a stable import surface, especially boundary modules used across layers.
- Do not add `__all__` mechanically to every file. Prefer it where it clarifies what other modules should import.
- If a package `__init__.py` re-exports the intended public API, leaf modules do not also need `__all__` unless they are themselves a documented import target.
- Use leading underscores for module-local helpers, internal DTOs, wiring functions, and implementation details that should not be treated as supported API.
- Tests may import underscored names when intentionally exercising implementation details, but prefer public behavior tests when practical.

```python
def send_email(to: str, msg: str, *, priority: str = "normal") -> bool:
    """Send an email to a recipient with specified priority.

    Any additional context about the function can go here.

    Args:
        to: The email address of the recipient.
        msg: The message body to send.
        priority: Email priority level.

    Returns:
        `True` if email was sent successfully, `False` otherwise.

    Raises:
        InvalidEmailError: If the email address format is invalid.
        SMTPConnectionError: If unable to connect to email server.
    """
```

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
