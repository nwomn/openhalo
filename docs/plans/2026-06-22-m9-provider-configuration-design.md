# M9 Provider Configuration Design

Date: 2026-06-22
Status: Working design baseline

## Purpose

This document defines the configuration architecture for `M9` cloud-model-backed agent work.

The goal is to make model integration mature enough for long-term growth without dragging `M10` grounding and runtime memory into the same batch.

The design should satisfy four constraints:

- support more than one mainstream provider
- support more than one model per provider
- keep runtime business logic independent from provider-specific API details
- preserve explicit `Presence Router` governance and bounded deterministic fallback behavior

Reference inspiration:

- OpenClaw/OpenClaw-style model directory and failover layering
- the current Codex session shape, which already separates `model_provider`, `model`, auth method, and wire protocol

## Design Goals

`M9` should introduce a stable provider boundary inside `Agent Runtime`, not just a one-off OpenAI client.

The first accepted implementation should:

- allow multiple configured providers to coexist
- allow multiple configured models to coexist
- let runtime call sites select a named profile instead of hard-coding provider and model pairs
- implement only the `openai_compatible` adapter path at first
- keep provider/model strategy routing out of the first implementation slice

`M9` should not yet solve:

- broad automatic provider/model routing
- runtime memory grounding
- retrieval orchestration
- policy learning
- provider-native support for every vendor-specific API

## Configuration Layers

The configuration model should use four layers.

### 1. Providers

Providers define how to talk to one backend family.

Typical fields:

- `adapter_type`
- `base_url`
- `wire_api`
- auth source such as `auth_env`
- timeout / retry defaults
- optional default headers

Providers are infrastructure entries. They should not encode business-scene choices such as "interactive reply" versus "initiative proposal".

### 2. Models

Models define one concrete model entry under a provider.

Typical fields:

- `provider`
- `model_id`
- static capability tags such as `supports_tools`
- optional default parameter hints

Models should stay mostly declarative. They represent catalog entries, not runtime intent.

### 3. Profiles

Profiles are the runtime-facing selection surface.

Examples:

- `interactive_reply`
- `initiative_proposal`
- `fallback_small`

Profiles map a business scene to one chosen model plus runtime parameters such as reasoning effort and verbosity.

Runtime code should call the model layer through a profile, not through a raw provider/model pair.

### 4. Selection Policy

Selection policy defines how the runtime resolves a call.

For the first `M9` batch:

- each call site explicitly selects one profile
- profile resolution returns one provider/model target
- no automatic routing is performed

Later work may extend this layer with fallback policy and eventually strategy routing.

## Explicit Selection, Fallback, And Routing

The project should follow the same broad maturity pattern used by stronger model systems such as OpenClaw:

- explicit user or runtime selection should remain inspectable
- default-path fallback should be distinct from explicit pinning
- provider auth failover and model failover should not be conflated

For the first `M9` slice:

- explicit profile selection is required
- deterministic local fallback is allowed when provider execution fails or returns unusable output
- automatic provider/model fallback is deferred

The runtime should record whether a response came from:

- the requested profile target
- deterministic local fallback
- a future automatic fallback path

That distinction matters for replay, debugging, and trust.

## Adapter Strategy

The long-term architecture should be hybrid:

- multiple provider families are supported by the configuration shape
- adapters may be either `openai_compatible` or later `provider_native`

The first implementation should land only:

- `adapter_type = "openai_compatible"`

That branch should cover:

- OpenAI directly
- OpenAI-compatible gateways and proxies
- OpenRouter-style compatibility surfaces where the same wire shape is sufficient
- future Azure/OpenAI-compatible support if the configuration can express its differences cleanly

Provider-native adapters may be added later when a mainstream provider cannot be represented cleanly through the shared compatibility surface.

## Runtime Boundary

The provider layer belongs inside `Agent Runtime`.

The model layer may generate:

- candidate reply text
- candidate proposal text
- bounded structured metadata

The model layer should not directly decide:

- final presence allow/suppress outcome
- target edge routing
- direct action execution

The runtime chain remains:

`State / Context -> Agent Runtime proposal generation -> Presence Router -> Execution Planning -> Action Layer`

`M9` changes proposal and reply generation, not the existence of the explicit governance boundary.

## First Implementation Slice

The first implementation should stay narrow.

It should:

- add provider/model/profile configuration support
- add an `openai_compatible` adapter
- let normal runtime text-reply generation use a selected profile
- preserve deterministic local fallback
- expose provider/profile/fallback provenance in inspection output

It should not yet:

- add automatic provider/model routing
- add automatic model failover chains
- add memory-grounded prompting
- add provider-native adapters

## Later Milestones

This design intentionally leaves room for later expansion.

Recommended sequence:

- `M9`: provider boundary, model catalog, profile selection, `openai_compatible` adapter, deterministic local fallback
- `M10`: grounding and runtime memory for model calls
- post-`M10`: explicit provider/model fallback policy
- later milestone: strategy routing that can choose among providers and models using task type, latency, cost, or capability constraints

Automatic provider/model strategy routing is intentionally a later milestone and is not part of the first accepted `M9` baseline.
