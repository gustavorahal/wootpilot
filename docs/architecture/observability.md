# Observability

WootPilot currently uses structured JSON logs, local developer workflow traces,
and durable audit records. There is no required hosted tracing service.

## Structured Logs

Application logs are emitted as JSON through
[`src/wootpilot/observability.py`](../../src/wootpilot/observability.py). Key
events include:

- `webhook_authentication_failed`;
- `webhook_handled`;
- `support_workflow_completed`;
- Chatwoot API latency events;
- outbound execution completion events.

Workflow completion logs include correlation identifiers and operational fields:

- raw event id;
- normalized message id;
- agent run id;
- tenant/channel/conversation ids;
- automation mode;
- workflow status and action kind;
- policy rule ids and risk reasons;
- model provider/model metadata;
- latency and high-latency flag.

Customer message bodies and generated response text are not included in normal
structured workflow logs.

## Local Workflow Trace

`WORKFLOW_TRACE=true` enables a developer-facing LangGraph trace in `local` and
`public_dev` environments. It is ignored in `test` and `production`.

Trace output prints graph node progress and pretty JSON payloads. Unlike normal
logs, this local trace intentionally includes customer messages and model-visible
text so a developer can debug end-to-end Chatwoot tests from the terminal.

## Audit Records

Audit records persist product-relevant explanations in the database. They connect
raw events, normalized messages, agent runs, policy decisions, context snapshots,
and outbound actions.

Audit records are the durable operator ledger. Logs are operational telemetry;
they are not the source of truth for explaining a workflow run.

## Sensitive Data

The code avoids logging raw provider payloads, API tokens, webhook secrets, and
normal customer/model text in structured logs. Local workflow traces are
content-rich by design and are limited to local/public-dev profiles.
