# Slice 5: OpenRouter Model Proposals

## Running Outcome

- WootPilot can call OpenRouter through `ModelProposalPort` and convert a
  structured model response into a WootPilot `AgentProposal`.

## Implementation Scope

- Add OpenRouter-backed `ModelProposalPort`.
- Use `langchain-openrouter` for LangChain/LangGraph chat model integration.
- Use direct HTTPX calls to OpenRouter only if the dedicated integration blocks a
  required MVP feature.
- Add structured model proposal schema.
- Capture model provider, model id, latency, token usage, and retryable/permanent
  error outcomes.
- Keep provider-specific schemas outside the domain layer.

## Required Tests

- Agent proposal schema validation rejects malformed model output.
- OpenRouter adapter maps structured responses into `AgentProposal`.
- Usage metadata, model id, latency, and provider error details are captured.
- Retryable OpenRouter errors map to retryable WootPilot result types.
- Permanent OpenRouter errors map to permanent WootPilot result types.
- Provider-specific response shapes do not leak into domain models.
- Shadow workflow can run with the OpenRouter adapter mocked by `respx`.

## Manual Verification

- Run the shadow workflow against a mocked OpenRouter response.
- Confirm model metadata is captured on the agent run or related model-call
  record.
