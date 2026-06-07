# AGENTS.md

These rules apply to this entire repository.

## Very Important

- **ALPHA PHASE**: structural changes are welcome. Prefer the right architecture over local patches.
- This repository is a VERY EARLY WIP. Proposing sweeping changes that improve long-term maintainability is encouraged.
- When in doubt between duplicating logic and extracting shared logic, extract it.

## Code Documentation

- When writing code, add docstrings or inline documentation where they help humans understand intent, behavior, or rationale.
- Prefer documentation that explains why something exists, what assumptions or tradeoffs shaped it, and how it should be used.
- Public functions, classes, modules, non-obvious algorithms, domain rules, and important architectural boundaries should usually have docstrings.
- Avoid documentation that merely restates obvious implementation details. The goal is educational clarity, not noise.
- Treat code as something future contributors will learn from: it should be readable on its own, and documented where context would otherwise be lost.

## Commits

- Commit messages must be explanatory, not just a short one-line message.
- Use an objective first line that summarizes the change.
- Include a body explaining context, main changes, and validation performed when applicable.
