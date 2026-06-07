# Observability

Minimum useful telemetry:

- Webhook latency.
- End-to-end workflow latency.
- Model latency.
- Tool and channel API latency.
- Connector read latency.
- Connector action latency.
- Token usage.
- Estimated cost.
- Policy decision.
- Bot mode.
- Outbound action type.
- Outbound success/failure.
- Connector capability used.
- Connector action proposed/executed/blocked.
- Human handoff rate.
- Public auto-reply rate.
- Private-note suggestion rate.
- Webhook authentication failures.
- Replay and duplicate-event rejections.
- Outbox queue age, retry count, and permanent failure count.
- Final pre-send policy recheck result.
- Price mention policy decisions.

Sensitive fields should be redacted before logs and traces:

- API keys.
- Authorization headers.
- Phone numbers.
- Emails.
- Personal documents.
- Access tokens.
- Refresh tokens.
- Full raw customer payloads where not required.
- Connector credentials references when they expose secret names that should not
  be broadly visible.
- Raw price display text if tenant policy treats pricing as sensitive.

Traces should link raw event id, normalized message id, agent run id, context
snapshot ids, outbound action id, and provider message id. That correlation is
more useful than logging full payloads, and it keeps auditability separate from
unnecessary data exposure.
