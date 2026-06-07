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

Sensitive fields should be redacted before logs and traces:

- API keys.
- Authorization headers.
- Phone numbers.
- Emails.
- Personal documents.
- Access tokens.
- Refresh tokens.
- Full raw customer payloads where not required.
