# Slice 5: OpenRouter Model Proposals

## Running Outcome

- WootPilot can call OpenRouter through `ModelProposalPort` and convert a
  structured model response into a WootPilot `AgentProposal`.

## Implementation Scope

- Add OpenRouter-backed `ModelProposalPort`.
- Use `langchain-openrouter` for LangChain/LangGraph chat model integration.
- Prefer `ChatOpenRouter.with_structured_output(...)` for the first adapter.
  Use LangChain `create_agent(..., response_format=...)` only if middleware or
  agent-loop behavior becomes useful inside the adapter boundary.
- Select provider-native JSON Schema structured output when the chosen
  OpenRouter model supports it well; otherwise fall back to tool/function-calling
  structured output.
- Use direct HTTPX calls to OpenRouter only if the dedicated integration blocks a
  required MVP feature.
- Add structured model proposal schema.
- Capture model provider, model id, latency, token usage, and retryable/permanent
  error outcomes.
- Preserve raw response metadata outside the domain model so audits can inspect
  provider routing, usage, and schema failures without leaking provider payloads
  into domain services.
- Keep provider-specific schemas outside the domain layer.

## Required Tests

- Agent proposal schema validation rejects malformed model output.
- OpenRouter adapter maps structured responses into `AgentProposal`.
- Adapter tests cover provider-native and fallback structured-output paths when
  both are supported by selected test fixtures.
- Usage metadata, model id, latency, and provider error details are captured.
- Retryable OpenRouter errors map to retryable WootPilot result types.
- Permanent OpenRouter errors map to permanent WootPilot result types.
- Provider-specific response shapes do not leak into domain models.
- Shadow workflow can run with the OpenRouter adapter mocked by `respx`.

## Manual Verification

- Run the shadow workflow against a mocked OpenRouter response.
- Confirm model metadata is captured on the agent run or related model-call
  record.
