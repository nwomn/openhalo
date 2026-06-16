# OpenClaw Gateway Code Audit

Date: 2026-06-16
Status: Preliminary source audit

## Purpose

This document records a first-pass source audit of the OpenClaw repository focused on one question:

- Can the OpenClaw gateway be reused as a product-neutral control-plane component for the personal runtime project?

The goal is not to review all of OpenClaw. The goal is to classify the gateway-related code into:

- likely reusable
- reusable only with refactoring
- too coupled to import as-is

## Repositories and Areas Inspected

The audit focused on these areas in the official `openclaw/openclaw` repository:

- `packages/gateway-protocol`
- `packages/gateway-client`
- `src/gateway`
- `src/gateway/server`
- `src/gateway/server-methods`
- `src/node-host`

## High-Level Conclusion

OpenClaw does have a real transport/control-plane layer, but the current gateway implementation is not cleanly isolated as only that layer.

The codebase already separates out a few reusable pieces:

- wire protocol and schemas
- reusable gateway client behavior
- some auth and socket lifecycle helpers

But the main gateway server surface is strongly entangled with:

- sessions
- chat history
- agent execution
- node command orchestration
- plugin runtime scopes
- device and node lifecycle state

So the answer is:

- Reuse of selected gateway infrastructure looks plausible
- Reuse of the OpenClaw gateway server as a whole does not currently look clean

## Strong Reuse Candidates

### `packages/gateway-protocol`

This package contains the cleanest reusable protocol substrate, but not every exported schema in the package should be treated as reusable.

Why:

- it is a standalone workspace package
- it contains protocol versioning, client info, frame envelopes, connect schemas, validators, and startup-unavailable contracts
- its lower-level frame and connect surface is reusable in concept

Important caveat:

- the package barrel also exports many OpenClaw product-level schemas such as sessions, chat, tasks, skills, and talk
- that means the package is not "clean" as a whole in the same way a tiny dedicated control-plane protocol package would be
- the reusable target is the frame/connect/auth subset and the packaging pattern, not the entire semantic schema surface

Implication:

- this is a good candidate to reuse conceptually, and possibly selectively at the file level, as a starting point for a control-plane protocol layer

### `packages/gateway-client`

This also looks intentionally reusable.

Why:

- the package comment explicitly says it stays reusable through host callbacks for OpenClaw-owned state
- it depends on `@openclaw/gateway-protocol` rather than on the full runtime
- it encapsulates websocket connection behavior, handshake, timeouts, reconnect, and device auth assembly

Implication:

- this is a strong candidate for direct reuse or adaptation for edge-side client transport

### `src/gateway/auth.ts`

This is relatively self-contained compared with the rest of the gateway.

Why:

- it focuses on gateway connection authorization
- it handles token, password, Tailscale, trusted proxy, rate limiting, and local loopback checks
- it does not directly depend on chat/session/agent execution logic

Implication:

- the auth logic looks extractable, though it may still need adaptation around config types and surrounding helpers

### `src/gateway/server/http-listen.ts`

This is a small utility layer.

Why:

- it only deals with HTTP listen retry and gateway lock errors
- it has no semantic dependency on sessions or agent runtime

Implication:

- low-risk extraction candidate

## Partial Reuse Candidates

### `src/gateway/server/ws-connection.ts`

This file is partly transport and partly runtime-aware.

Transport-ish responsibilities:

- websocket connection handling
- preauth budgeting
- connect challenge
- payload limit handling
- handshake timeout logic

But it also directly imports runtime-linked concerns such as:

- runtime config
- system presence updates
- remote node info cleanup
- node wake state cleanup
- plugin node capability surfaces
- request context builders and gateway method registry

Implication:

- the transport skeleton may be reusable
- the current file is too mixed to lift cleanly without refactoring

### `src/gateway/server/plugins-http.ts`

This layer looks useful, but not neutral.

Why:

- it routes plugin HTTP traffic and upgrades
- but it also depends on plugin runtime request scopes and gateway request context

Implication:

- good reference material
- not a clean drop-in for a minimal personal-runtime gateway

## Poor Reuse Candidates

### `src/gateway/server-methods`

This directory is the clearest sign that the current gateway is no longer just a thin control plane.

Evidence:

- it contains handlers for `chat`, `sessions`, `agents`, `devices`, `nodes`, `tasks`, `config`, `talk`, `skills`, `cron`, and more
- `chat.ts` imports agent scope, embedded agent runner pieces, auto-reply flows, transcript handling, media staging, outbound reply pipelines, and session history utilities
- `sessions.ts` imports embedded agent run controls, session compaction, session patching, transcript access, and chat handler reuse
- `nodes.ts` includes node pairing, APNs wake, node policy, node invoke handling, pending work queues, and plugin surface refresh
- `devices.ts` includes device pairing and device token lifecycle management

Implication:

- this is not a neutral boundary layer anymore
- it is effectively part of the runtime semantic surface
- importing this wholesale would pull OpenClaw's worldview into the new project

### `src/gateway/methods/core-descriptors.ts`

This file exposes the scope of the problem very clearly.

Why:

- the canonical core method table includes a very wide surface: `chat.*`, `sessions.*`, `agents.*`, `tasks.*`, `skills.*`, `talk.*`, `cron.*`, `node.*`, `device.*`, and more
- the gateway method policy table is therefore describing not just transport operations but much of the product runtime API

Implication:

- OpenClaw's gateway is structurally a control plane plus a large portion of the application runtime API

### `src/gateway/boot.ts`

This is not a generic gateway concern.

Why:

- it runs `BOOT.md` checks via `agentCommand`
- it manipulates session mappings and agent boot sessions

Implication:

- should not be treated as reusable gateway infrastructure

## Node-Related Observation

`src/node-host` appears to be a relatively distinct execution-side area for remote node operations such as invoke handling and system-run policy.

That separation is useful conceptually.

But the control path that exposes node behavior through the gateway is still routed through gateway server-methods and node-specific runtime logic.

So:

- node-host separation exists
- gateway-to-node orchestration is still tightly bound to OpenClaw semantics

## Practical Assessment For This Project

If the goal is a minimal gateway for the personal runtime project, the code audit suggests this strategy:

### Worth borrowing directly or conceptually

- protocol schemas and versioning patterns
- edge client transport patterns
- selected auth logic
- selected socket and connection lifecycle patterns

### Worth using only as reference, not as imported architecture

- websocket server request handling
- plugin HTTP gatewaying
- node invocation routing patterns

### Not worth carrying over as-is

- gateway method surface
- session/chat/agent runtime handlers
- boot/session management inside gateway

## Current Recommendation

Current recommendation after source inspection:

1. Treat the frame/connect/auth subset of `packages/gateway-protocol`, plus `packages/gateway-client`, as the strongest reuse candidates.
2. Treat `src/gateway/auth.ts` and a few small server utilities as selective extraction candidates.
3. Do not plan around reusing `src/gateway/server-methods` or the OpenClaw core gateway method table wholesale.
4. Assume a minimal replacement gateway is still the safer default unless deeper code extraction proves otherwise.

## Decision Impact

This audit does not fully close the gateway question, but it narrows it substantially.

It suggests that the likely practical path is:

- borrow protocol and transport ideas
- possibly extract a few infrastructure layers
- rebuild the semantic gateway surface around the personal runtime model
