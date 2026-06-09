# MVP Conversation Behavior

This document describes what WootPilot's MVP agent actually does in a Chatwoot
conversation. It is the product contract that the architecture and slices should
implement.

## Channel Path

The MVP path is:

```text
Customer on WhatsApp or web chat
  -> Meta / Chatwoot channel infrastructure
  -> Chatwoot conversation
  -> Chatwoot webhook to WootPilot
  -> WootPilot policy, context, and agent workflow
  -> WootPilot outbound action
  -> Chatwoot API write
  -> Chatwoot delivers through the original channel
```

WootPilot does not talk directly to Meta in the MVP. Chatwoot owns the Meta
WhatsApp Cloud API integration, inbox, customer identity, conversation thread,
agent UI, and final delivery. WootPilot integrates with Chatwoot webhooks and
Chatwoot APIs.

The public development Chatwoot server is:

```text
https://chat.gmrahal.net/
```

This server is the MVP live integration target for Meta-reachable Chatwoot
testing. Local disposable Chatwoot remains useful for fast manual checks, but
the public dev server should be used to verify real channel back-and-forth with
Meta once WootPilot has webhook and outbound API wiring.

For the initial MVP loop, WootPilot runs on this laptop behind a public tunnel.
Chatwoot posts signed webhooks to the tunnel URL. WootPilot calls the public
Chatwoot API at `https://chat.gmrahal.net` to write private notes or safe public
replies.

The configured public-dev laptop tunnel hostname is:

```text
https://wootpilot-local-dev.gmrahal.net
```

Use the harness in `infra/public-dev-laptop` to start the tunnel, sync the
Chatwoot webhook, and run readiness checks while implementing each slice.

## MVP Features

The MVP agent offers these behaviors:

- Receive customer messages from Chatwoot webhooks.
- Ignore non-customer events, private notes, outbound messages, bot echoes, and
  duplicate deliveries.
- Track whether a human operator is active in the conversation.
- Classify customer intent with deterministic rules before model calls.
- Load structured WooCommerce product context from mock data or public Store API
  reads.
- Produce an auditable agent proposal with a structured model response.
- Run in observe mode, assist mode, or public reply mode.
- Write Chatwoot private notes in assist mode for human review.
- Send public replies only for low-risk cases in public reply mode.
- Stop public replies when deterministic policy says the case needs a human.
- Persist raw events, normalized messages, context snapshots, policy decisions,
  agent runs, outbound actions, and audit records.

The MVP does not perform refunds, discounts, order changes, account changes,
authenticated WooCommerce mutations, or custom Chatwoot UI approval flows.

## Mode Behavior

`observe`:

- WootPilot evaluates the message and stores what it would have done.
- It never writes a private note or public reply to Chatwoot.
- Use this for live observation against the public dev Chatwoot server before
  enabling writes.

`assist`:

- WootPilot writes a private note with a suggested reply, useful context, and
  risk reasons.
- The customer does not see the private note.
- A human agent replies from Chatwoot if they want to use or edit the suggestion.
- This is the safest customer-support write mode. The current alpha templates
  default to `public_reply` so public-dev testing exercises the full delivery
  pipeline.

`public_reply`:

- WootPilot can send a public message only when the final policy check says the
  exact content is safe.
- It may answer simple approved-context questions, ask a clarifying question,
  share a safe product link, or mention an exact product price only when the
  price snapshot allows it.
- It must not send public messages for sensitive, ambiguous, account-specific,
  billing, refund, compatibility, technical diagnosis, or policy-heavy cases.

## Handoff To Humans

In the MVP, "handoff" means WootPilot stops public replies and leaves the
conversation for a human in Chatwoot. Chatwoot remains the handoff surface.

WootPilot should hand off when:

- A human agent has replied publicly recently.
- The conversation is assigned to a human and local policy treats assignment as
  active handling.
- The conversation has a WootPilot pause label or custom attribute.
- The customer asks for a person, manager, callback, cancellation, refund,
  discount, legal/policy decision, account change, or other sensitive action.
- Product matching is ambiguous or the requested claim requires human review.
- The customer sends unsupported media or a message WootPilot cannot safely
  interpret.
- Prompt injection or private/internal-information requests are detected.
- Final pre-send policy rejects the exact proposed public content.

Handoff actions by mode:

```text
observe
  Record the handoff decision only.

assist
  Write a private note explaining the suggested response, context, and risk
  reasons.

public_reply
  Prefer a private note and no public reply. A short public "someone will review
  this" message is allowed only when policy permits it and no human is already
  active.
```

WootPilot should not send a public handoff confirmation if a human is already
active, because that creates noise and can make the customer feel bounced around.

## Human Control Signals

The MVP should treat these Chatwoot-side signals as human control:

```text
human public reply
  A human agent sent a customer-visible message. Public auto replies are
  suppressed for a configured window. The default window is 15 minutes.

assignment
  A human or team assignment suppresses public replies.

status
  Open means the customer is waiting. Pending can be used by teams to indicate
  bot/AI handling. Resolved means the case is done until the customer replies.

labels or custom attributes
  WootPilot-specific labels/custom attributes can pause automation.
```

Suggested MVP labels:

```text
wootpilot-paused
  Do not send public AI replies. Private assist notes may still be allowed.

wootpilot-needs-human
  WootPilot detected a case that needs human review.
```

Labels are a product contract, not an implementation requirement for every
slice. Early slices can model them as fixture fields or conversation state.
Once the Chatwoot writer supports labels or custom attributes, WootPilot can
write `wootpilot-needs-human` and read `wootpilot-paused`.

## Handoff Back To AI

The MVP should support conservative return-to-AI behavior.

WootPilot may resume handling a conversation when all of these are true:

- A new customer message arrives.
- Automation mode for the tenant/inbox allows the relevant behavior.
- The conversation is replyable and not resolved in a way that blocks replies.
- For public replies, the human-active suppression window has expired and the
  conversation is not assigned to a human or team.
- The conversation does not have `wootpilot-paused`.
- Pre-model and post-model policy pass.

WootPilot should not automatically resume just because a human stopped typing or
because time passed inside an existing customer turn. A new customer message is
the clean MVP boundary for another AI decision.

If a human wants WootPilot to resume, the sane default is to wait for the next
eligible customer message after the human-active window expires, or remove
`wootpilot-paused` if the conversation was manually paused.

## Public Dev Back-And-Forth

The public dev environment should prove this loop:

```text
customer sends message through Meta-connected channel
  -> message appears in https://chat.gmrahal.net/
  -> Chatwoot sends webhook to WootPilot
  -> WootPilot records the event and decides a mode action
  -> WootPilot writes private note or public reply through Chatwoot API
  -> human can reply in Chatwoot
  -> WootPilot observes the human reply and suppresses public replies
  -> next eligible customer message can be handled after the suppression window
```

This public loop should be an opt-in integration smoke test, not default CI.
Default CI should use fixtures and mocked HTTP for determinism.
