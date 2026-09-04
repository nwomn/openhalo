# Distributed Edge Media Memory Design

Status: Camera Edge short-term video memory is physically accepted: a local
Hot Ring records independently decodable MP4 segments, and a normal Runtime
chat can dispatch a source-bound query to the Edge for direct provider
Understanding before Main Hermes gives the user-facing response. The approved
next design is immediate asynchronous Episode generation while evidence is
still in Hot Ring; Episode persistence/sync/retrieval, Archive Ring, audio
memory, and full M17.10 acceptance remain future implementation work.
Date: 2026-09-01  
Scope: Camera Edge, Proxy Interaction Edge screen surfaces, future audio-capable
Edge surfaces, and their normal `Edge Session Link <-> Gateway <-> Personal
Runtime` integration.

## 1. Decision

OpenHalo media memory is distributed by source.  A Camera Edge, Proxy screen
surface, or later audio source retains and understands its own media locally;
Personal Runtime holds the small, searchable, provenance-bearing replicated
memory index needed for cross-Edge queries and Main Hermes context.

This is not a second Runtime lifecycle and not a Camera-specific prompt path.
It extends the existing generic evidence and `ContextFact -> ContextEnvelope ->
Main Hermes` direction with source-scoped media memory.

The first functional version intentionally prefers a direct, inspectable
closed loop over credential, audit, and adaptive-policy sophistication:

- an owner-enabled Edge retains configured local media buffers;
- an event- and sampling-driven Episode worker asynchronously selects bounded
  already-closed local media while it is still in Hot Ring, then directly calls
  the selected cloud model to write a local natural-language Episode note;
- Runtime receives only the Episode envelope, Markdown note, sync state, and
  source metadata, not the continuous raw media;
- detailed recent queries are sent as a normal source-bound `media.memory.query` action. The selected Edge extracts only the bounded local interval, calls its chosen video/audio model directly, and returns a textual `Understanding` plus small coverage/provenance metadata; clip bytes never enter Runtime.

## 2. Why two local perception roles exist

The Edge has two deliberately different outputs.

### 2.1 Narrow local Features are the fast trigger path

Local detectors must remain narrow, typed, temporalized, and cheap: camera
availability, person count and transition, allowlisted object count, region
occupancy, VAD, or a screen-state feature.  These are high-information-density,
low-resolution signals.  They may create ContextFacts and wake Runtime
deliberation, but they are not by themselves the evidence for rich historical
claims.

Each Feature must preserve source, time, freshness, model/version, confidence,
and `unavailable` rather than silently reporting an absence.  A Feature-specific
reducer is responsible for debounce/hysteresis and for emitting a confirmed
transition.  This follows the useful boundary in small robotics systems such as
MicroDuck: local perception publishes constrained features for timely local
consumption instead of pretending to be a general scene narrator.

### 2.2 Media Episode notes are the slow semantic path

An Edge's sealed video or audio window can carry substantially richer temporal
context than a sequence of narrow Features.  Its model-generated long-term
Episode is therefore the principal semantic description of that source's past,
subject to its coverage and limitations.  It does not replace the fast Feature
path and it cannot create an action or Presence decision by itself.

## 3. Source-scoped local lifecycle

Every participating media source is named by:

```text
edge_id + surface_id + capability + media_kind
```

Examples are `camera-living-1/camera.main/camera.capture/video` and
`proxy-edge-1/phone-screen/proxy.screen/screen`.

Each source independently owns the following local lifecycle:

```text
hardware encoder
  -> Hot Ring (high-detail, recent original media)
       -> Feature / transition candidate scheduler
       -> low-frequency stable-scene sampler
       -> bounded asynchronous Episode worker
            -> local EpisodeRecord + Markdown EpisodeNote + sync outbox
            -> Runtime replicated index/note
  -> Archive Ring only when a pending/failed episode would otherwise lose raw
     evidence as the relevant interval rotates out of Hot Ring
```

`HotRing` is segmented rather than a monolithic rewritten movie so an Edge can
locate and extract a bounded time interval, survive a partial write, and report
which exact time range remains available.  It answers recent detailed questions.

`SealedChunk` is a closed, independently readable local interval. It is eligible
for Episode work as soon as it enters Hot Ring; it does not wait for Hot Ring
expiry. An Episode worker is bounded, deduplicates and merges adjacent candidate
events, and never queues raw frames. It may retain only local segment handles
until work starts. A pending/failed/offline interval moves into a separate
fixed-length Archive Ring only when it would otherwise rotate out of Hot Ring.
Archive rotation drops the oldest unsummarized media and writes a deterministic
`coverage_gap`; it never pressures the independently configured Hot Ring.
Pinned user/incident evidence may extend this retention.

The first version uses Edge cold configuration, not Runtime adaptive policy:

```text
video_enabled
audio_enabled
hot_ring_minutes
archive_chunk_minutes
archive_video_bitrate
archive_sample_rate
raw_archive_retention_minutes
episode_retention_days
cloud_video_model
```

Per-source policy is essential.  A Proxy screen normally needs a shorter and
more restrictive default retention than an owner-approved room camera; sharing
the same Runtime records does not mean sharing the same capture policy.

## 4. First-version cloud-model invocation

The owner-selected first version permits a paired Edge to retain the cloud
model's primary API key in its device-private configuration and call that model
directly.  This avoids routing every source's raw media through Personal
Runtime and makes the first end-to-end feature implementable.

For the current implementation slice, Runtime selects one of its own configured
provider/model profiles and delivers the complete projection in a registered
`media.provider.configure` `action_request`: provider name, adapter type,
base URL, wire API, timeout, default headers, API key, and selected model
identity/capabilities.  The Edge keeps that profile only in process memory; a
restart requires another configuration action.  Its success result returns only
non-secret provider/model identity and `configured` state, never the key or
headers.  This is intentionally a functional v1 provisioning mechanism, not a
claim of a mature secret-control plane.

This is explicitly a first-version trade-off, not a production credential
architecture.  The key must never be emitted in logs, diagnostics, ordinary
Observations, Episodes, or UI state.  Revocation, unpairing, or user clear-data
must remove the device-private copy.  Later work may replace it with a
per-device quota key, a scoped credential, or an inference lease without
changing the media-memory contract.

Direct Edge-to-provider calls avoid Runtime ingress and Runtime raw-media
storage.  They do not remove the Edge's own internet bandwidth, provider cost,
or privacy implications.  The user configures sampling/bitrate/retention first;
adaptive activity gating and dynamic budgeting are deliberately deferred.

An ordinary Runtime chat provider is not automatically eligible for direct Edge
traffic. A Runtime provider must explicitly declare `edge_direct_eligible = true`
before Runtime may project it to an Edge. On 2026-09-01, the deployed
`cubence / openai_compatible / gpt-5.6-terra` Runtime profile was rejected for
this purpose: the provider returned an explicit anti-secondary-distribution
error during a minimal image probe, and the corresponding official GPT model
documentation lists video input as unsupported. It must not be dispatched to
Camera Edge. Selecting a direct-Edge provider that permits the traffic and
supports the required media form remains a required next configuration decision.

### 4.1 Current concrete Camera provider

The first configured Camera Edge mapping is intentionally fixed, not selected
by a policy loop:

```text
camera-edge-1 -> camera_video_qwen3_vl_flash
  -> camera_video_dashscope
  -> qwen3-vl-flash
  -> OpenAI-compatible Chat Completions
```

This profile is declared `edge_direct_eligible = true` in the deployed private
Runtime configuration and is projected only to `camera-edge-1`. The concrete
`OpenAICompatibleVideoAdapter` supplies one or more locally selected Hot Ring
segments as `video_url` Base64 data URLs to the compatible Chat Completions
endpoint and asks for Markdown Understanding. It sends no media to Runtime.
For this inline path, each raw segment is constrained to 7 MiB, so the encoded
data URL remains within the provider's documented 10 MiB Base64 ceiling. Larger
segments need a separately designed public-URL/OSS path and are not silently
uploaded in v1.

Runtime sends this profile immediately after this Camera Edge authenticates and
registers `media.provider.configure`. It does so only for the explicit device
mapping, never by scoring alternative profiles. The Edge retains it only in
process memory and must receive it again after restart; its result exposes only
`configured`, provider name, and model name, never the API key.

## 5. Markdown Episode notes are the primary semantic memory

The model is not required to satisfy a complex structured-output schema.  The
first implementation stores a human-readable Markdown `EpisodeNote` alongside a
small deterministic envelope.  Markdown is the primary semantic memory read by
Main Hermes as a bounded excerpt; it is not merely a display rendering of a
machine record.  Natural-language episode documents are more resilient to
optional fields, partial descriptions, model-provider variations, and statements
of uncertainty than a strict JSON generation contract.

The Edge/system, never the model, writes the envelope fields:

```text
episode_id, source identity, window start/end, capture completeness,
sampling/codec metadata, model/provider identifier, generation status,
raw-media availability, local persistence status, sync status, and hashes.
```

The model writes `episode.md` using a requested but non-parser-critical shape:

```md
# 10:00–10:05 Living room

## Overview
...

## Timeline
- Around 10:02: ...

## Cannot confirm
- ...
```

If the note is incomplete but readable, it is a `partial` Episode rather than a
schema error.  If provider invocation fails, the deterministic envelope records
`generation_failed` or `retry_pending`; it never fabricates an empty scene.
Runtime can index the text as text and later use semantic/vector retrieval.  If
future retrieval needs a mechanical time index, that index comes from local
confirmed Features/transitions, not from treating model prose as an
authoritative event database.  Optional derived structure may later be produced
by Runtime from the note plus those facts, but first-version correctness must
not depend on an Edge-invoked model reliably emitting or Main Hermes reliably
consuming strict JSON.

An Episode note must distinguish observed source facts from semantic inference
in its language, preserve occlusion/low-resolution/sparse-sampling limitations,
and state unknowns instead of naming an unseen object or person.

## 6. Runtime replication, retrieval, and Main Hermes context

The Edge is the source authority for capture state, Hot Ring availability, its
local Episode note, and unsynchronised intervals.  Runtime holds a durable,
searchable replicated copy of the small Episode envelope/note.  This permits
phone and cross-Edge recall without retaining every original media file in
Runtime.

On reconnect, an Edge synchronizes Episode envelopes and Markdown notes through
the normal Gateway.  It does not upload continuous source video as a side effect
of synchronization.  Runtime tracks at least:

```text
last_synced_at
sync_lag
unsynced_interval
source_unreachable
```

An absent or offline source never means that nothing happened.  Main Hermes
must receive that coverage gap when it answers a question.

For each Interaction, Runtime deterministically retrieves a bounded set of
relevant notes and current ContextFacts, then compiles a `MemoryContext` through
the existing ContextEnvelope path.  Main Hermes receives only:

- a time anchor and relevant source(s);
- selected Episode excerpts and stable IDs;
- source, time interval, provenance, availability, and limitations;
- conflicts/unknowns and unsynchronised coverage;
- references to policy-eligible Hot Ring or retained evidence.

Main Hermes does not receive raw media, every Episode ever recorded, or an
unbounded timeline.  For a precise recent question, Runtime dispatches one
registered, source-bound `media.memory.query` action.  The relevant Edge
extracts the local bounded interval, calls its selected provider directly, and
returns only a textual `Understanding` plus deterministic source, interval,
model, coverage, and limitation metadata through Gateway.  Runtime checks the
source/action registration and availability, then injects that result into the
next semantic turn.  No video or audio bytes cross into Runtime.

## 7. Multi-Edge correlation

Runtime never stores a source-less global camera memory.  Source Episodes are
independently retrievable.  At query time, Runtime may correlate aligned
episodes/facts from different sources only when their source timestamps and
clock uncertainty support the relation.  The result is a provenance-preserving
composite view, not a destructive merge:

```text
Camera Episode: person appeared near desk, 10:02–10:04
Proxy Episode: payment screen shown, 10:02–10:03
Composite recall: both sources report activity in an overlapping interval;
causal relation is unknown unless an evidence-backed Understanding says more.
```

Camera, Proxy, and audio sources may therefore scale independently without
creating Camera-specific or Proxy-specific Runtime lifecycles.

## 8. Query behavior

```text
recent detailed question
  -> Runtime routes a source-bound `media.memory.query`
  -> named Edge reads its local Hot Ring and calls the selected provider directly
  -> textual Understanding + coverage return through Gateway; no media enters Runtime

historical coarse question
  -> retrieve matching Episode notes/excerpts
  -> Main Hermes answers with source and limitations

historical fine-detail question after raw expiry
  -> Episode may provide coarse context
  -> answer that the requested detail cannot be reliably verified
```

User-initiated recall is a normal Interaction.  Historical memories are not
proactive intervention inputs unless a separate owner policy admits a specific
class of historical signal through ordinary Presence governance.

## 9. First implementation acceptance

The first acceptance is deliberately a single source, not a full fleet:

1. An owner-enabled Camera Edge captures segmented local media and maintains a
   configured Hot Ring without Episode work blocking capture or Feature output.
2. A confirmed Feature/transition candidate or low-frequency stable-scene
   sampler triggers one bounded Episode worker job while its closed media is
   still in Hot Ring; adjacent work is merged rather than becoming one note per
   segment.
3. The Edge persists an `EpisodeRecord` (source/time/coverage/gap/state,
   Feature references, raw-evidence availability and provenance) plus a readable
   Markdown `EpisodeNote`; model output is never required to be strict JSON.
4. The Edge synchronizes only that envelope/note through Gateway to Runtime;
   Runtime stores/indexes no MP4, Base64 media, or raw frames.
5. After the relevant raw media has left Hot Ring, an ordinary coarse recall
   retrieves the Episode note; Context compilation injects only a bounded
   source/time/coverage/limitation projection into Main Hermes.
6. A fine-detail or temporal query can escalate to a source-bound
   `media.memory.query` while raw evidence remains in Hot Ring/Archive Ring.
   If the source declares the evidence expired or the Episode reports a gap,
   the answer explicitly refuses to invent the detail.
7. Provider failure or Runtime disconnection leaves pending source media only in
   a bounded Archive Ring. Rotation records `coverage_gap`, preserves Hot Ring
   liveness, and drains/synchronizes completed Episode notes after recovery.
8. Key redaction, user disable/clear, visible recording state, raw retention,
   source-specific deletion, then multi-Edge source isolation and aligned-time
   correlation are manually verified in that order.

This acceptance does not claim full M17.10 acceptance, production credential
security, audio understanding, cross-Edge composite reasoning, automatic
sampling adaptation, or continuous-cloud-media suitability.

## 10. Current single-process implementation topology

The first implementation topology is one `CameraEdgeService` process and one
asyncio event loop.  It is deliberately not a second Edge lifecycle and does
not introduce local IPC:

```text
CameraEdgeService (one process / one capture owner)
  -> ephemeral captured frame
       -> SegmentRecorder -> LocalHotRing
       -> sampled FeatureWorker -> small Observation sink
  <- bounded media.memory.query queue
       -> local HotRing -> direct provider -> text action-result sink
```

The capture owner is the only component allowed to call the physical camera.
Encoder and Feature worker receive the same ephemeral frame during that loop;
neither Runtime nor the service's queues retain it.  The media-query worker is
separate from capture by a bounded in-process async queue so an awaited provider
request does not stall later capture iterations.  It returns only the normal
textual `Understanding` action result.

`CameraHealthDaemon` remains the existing compatibility Gateway/session and
health entry point while real MaixCAM capture and encoding are migrated.  It is
not a second camera owner.  A later product decision may split a control agent
and data-plane service into two processes, but that IPC topology is not implied
or required by this first implementation.
