# Edge Attention Profile Baseline

Status: architecture baseline; Profile delivery implementation is deferred.

## Decision

An Edge Profile is not a second lossy observation filter.  OpenHalo keeps the
safe, bounded, structured base Observation vocabulary from a registered Edge
available to Runtime independently of an Attention Profile.  Raw screen,
video, and microphone media remains local by default and never becomes normal
Main Hermes context.

`ContextFact` retains accepted base Observations with source, freshness,
privacy, and confidence.  `ContextEnvelope` selects the bounded facts relevant
to the current Interaction and scene before Main Hermes deliberates.  It must
not replace that selection by injecting every raw or historical Observation
into a prompt.

## Attention Profile

The future profile mechanism is an explicit, short-lived `Attention Profile`
overlay proposed by Main Hermes from the current scene and then validated by
Runtime.  It expresses what additional information is worth acquiring from one
exact Edge target or surface, such as registered Feature subscriptions,
sampling/debounce, evidence-window retention, and evidence-query triggers.  It
cannot carry arbitrary detector code, authorize raw-media streaming, or bypass
privacy, permission, Runtime validation, Presence, or action governance.

Runtime validates the profile against the Edge capability registry, owner
consent, privacy class, resource/evidence budget, and target/surface binding.
A future delivery component may reliably send, renew, retry, and audit an
accepted overlay, but it must not invent the attention policy.  Main Hermes
receives a bounded status projection of accepted overlays in its grounding
context rather than being interrupted by delivery mechanics.

## Existing Proxy Protocol

The current Proxy Edge `proxy.screen.profile.configure` protocol is retained as
a bounded host/runtime protocol experiment.  Its current rule that no screen
Feature frame is emitted before a Profile is active is not the durable
architecture for visual, audio, or microphone Edges.  Do not add a Runtime
Profile delivery controller or automatic lease manager yet.  Future work must
migrate it to base facts plus an Attention Profile overlay before treating
Profile dispatch as a product or hardware-acceptance prerequisite.

The first migration slice exposes the Profile-independent Proxy facts through
`proxy.screen.base_observe`: capture health, bounded digest-based change, and
action-correlated change. They carry exact target/surface binding and no raw
pixels, Profile identifier, or GUI interpretation. `proxy.screen.features`
preserves the old hard-Profile experiment separately. When Hermes needs to
read a screen, it uses ordinary `proxy.screen.read` with `freshness:"latest"`
and a byte bound. The Edge returns one JPEG in the correlated ordinary
`action_result.payload`; Gateway validates MIME, size, and SHA-256, removes the
encoded bytes before persistence, and exposes only transient visual text to the
continuing Hermes turn. A Profile is not a prerequisite.

## Near-Term Priority

The immediate implementation priority is the visual Edge plus audio/microphone
Edge perception-and-control closed loop: local safe Features -> Runtime
ContextFact/ContextEnvelope -> Main Hermes scene reasoning -> Presence and
validated action -> correlated result/verification.  This work should reuse
the existing M17.10 bounded-media, evidence, privacy, and failure semantics;
it must not wait for Attention Profile delivery.
