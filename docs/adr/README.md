# Architectural Decision Records

> Type: ADR index
> Status: Current

This directory stores short records for durable architectural decisions.

Use an ADR when a decision shapes long-term code structure, operational behavior,
or product safety policy. Living architecture docs should describe the current
design; ADRs should explain why a durable choice was made and what tradeoffs it
accepted.

## Format

```text
# ADR 000N: Title

Date:
Status: Proposed | Accepted | Superseded

## Context
## Decision
## Consequences
## Alternatives Considered
```

## Records

No ADRs have been extracted yet. The first candidates are:

- Chatwoot as the primary support channel instead of a generic connector.
- LangGraph as an explicit support workflow rather than a free-form agent loop.
- Outbox-based Chatwoot writes instead of writing inside the graph.
- Connector context prepared before graph invocation.
- `observe`, `assist`, and `public_reply` operating modes as the safety ladder.
