# M17.10 Ambient Camera Edge Design

Status: design baseline; implementation has not started.

This document records the proposed first implementation shape for a fixed home/desk camera Edge. It is intentionally a bounded ambient-observation design, not a commitment to continuous raw camera or microphone streaming.

## 1. Architecture position

The camera is a normal `Device Edge`, not a backend-owned camera adapter and not a second agent runtime. Its physical path is:

```text
Camera sensors
  -> local Edge processing and bounded evidence buffer
  -> Edge API
  -> Edge Session Link
  -> Gateway
  -> Personal Runtime
```

`Personal Runtime` remains authoritative for:

- scene/profile confirmation and change governance;
- feature subscription policy, privacy, permissions, and retention;
- high-level video/audio understanding;
- evidence correlation, Presence, and action decisions.

The camera Edge is responsible for local capture, low-cost feature extraction, candidate-event detection, and bounded pre/post-event evidence buffering. A Runtime model may be local or a governed remote provider, but the camera Edge does not directly depend on a model provider.

## 2. Core vocabulary

The implementation must keep these objects separate:

| Object | Meaning | Owner |
| --- | --- | --- |
| `Feature` | A registered, versioned extractor or detector capability, such as person presence or VAD | Runtime capability/feature registry |
| `Observation` | One timestamped, schema-valid structured result from a Feature | Edge, with Runtime provenance |
| `Event` | A bounded temporal change inferred from one or more Observations | Edge proposes; Runtime evaluates |
| `Evidence` | A bounded video/audio segment that supports an Event or a Runtime query | Edge stores/captures; Runtime governs retrieval |
| `Understanding` | Runtime model interpretation of Observations plus Evidence | Personal Runtime |

The Edge should emit typed, schema-validated observations rather than asking a small model to freely generate arbitrary JSON. Model-assisted extraction, if later needed, must still terminate at a registered Feature schema.

## 3. Scene and feature subscription flow

The intended setup flow is:

```text
Camera Edge registers
  -> Runtime inspects capability and initial bounded evidence
  -> Runtime proposes or confirms a Scene Profile
  -> user confirms or edits the profile when needed
  -> Runtime selects allowlisted Features
  -> Runtime sends a versioned Feature Subscription
  -> Edge continuously emits structured Observations
```

A first profile might be:

```text
scene: living_room
placement: fixed_camera
features:
  - person_presence
  - person_entered
  - object_present
  - door_state
  - speech_activity
  - known_person_candidate   # only with explicit enrollment and consent
```

The Runtime may propose a profile from an initial scene sample, but one model guess must not permanently become a fact. The user or an explicit policy must be able to confirm, edit, pause, or revoke the profile.

Feature subscriptions are selected from a capability/feature registry and include a feature identifier, version, parameters, output schema, sampling/debounce policy, privacy class, and expiry/revision information. The Runtime must not ask the Edge to execute arbitrary model-generated code or an unregistered monitoring task. Adding a new Feature requires registry, version, permission, and compatibility checks.

## 4. Local Edge responsibilities

The first Edge implementation can use small, bounded components for:

- person/object detection and tracking;
- region entry/exit and coarse state changes;
- object appeared/disappeared detection;
- VAD and optionally bounded local ASR;
- authorized known-person candidate matching;
- a local circular video buffer and optional audio buffer.

These components are detectors, not the source of high-level meaning. For example, `person_presence=true` is useful immediate evidence; deciding that a delivery person left a package, that two people are arguing, or that an action is needed belongs to Runtime understanding and Presence governance.

Each Observation should include at least:

```json
{
  "type": "person_presence",
  "schema_version": "1",
  "observed_at": "2026-08-05T12:00:00Z",
  "value": {"present": true, "count": 1},
  "confidence": 0.94,
  "source": {"device_id": "camera-edge-1", "feature_version": "..."},
  "privacy": {"raw_media_included": false},
  "expires_at": "2026-08-05T12:00:10Z"
}
```

The exact wire schema remains an implementation task, but the contract must support freshness, confidence/uncertainty, provenance, privacy classification, and expiry. A feature that cannot produce a meaningful result should report an explicit unavailable/degraded state rather than silently appearing absent.

## 5. Event and evidence path

To preserve useful responsiveness without continuously uploading media, the Edge uses two related paths:

```text
Feature change
  -> immediate candidate_event Observation/Event
  -> Runtime updates compact state quickly

Feature change
  -> Edge freezes bounded pre-event ring buffer
  -> Edge records bounded post-event interval
  -> Runtime requests or receives authorized Evidence
  -> Runtime video/audio model returns Understanding
  -> Runtime records understanding.ready or a bounded failure state
```

The initial buffering target is a configurable 5–10 second pre-event ring plus a finite post-event clip. The exact duration, frame rate, audio inclusion, size limit, and retention are policy values rather than hard-coded assumptions. Raw media remains on the Edge by default and is uploaded only for an accepted/authorized evidence request, an explicitly configured event policy, or a user-initiated inspection.

`candidate_event` is not automatically an accepted event and must not directly trigger an action. Runtime decides whether the candidate is relevant, whether more evidence is needed, and whether the result should enter the normal observation/proposal/Presence path.

The understanding lifecycle should be inspectable:

```text
pending_understanding
  -> understanding_ready
  -> understanding_failed
  -> evidence_unavailable
```

An event can remain useful as structured evidence even when its video is unavailable or model understanding fails. The Runtime records timestamps, model/provider version, confidence, provenance, and evidence references for every returned Understanding.

## 6. Runtime query and model boundary

Runtime may use the public Edge API to request, subject to policy:

- structured Features or Observations for a bounded time window;
- additional details for a known Observation;
- the short Evidence associated with an Event;
- an authorized audio or video segment when the current context justifies it.

These requests still travel through `Edge Session Link <-> Gateway`; Runtime must not bypass the Gateway or access camera internals directly.

Complex interpretation stays in Personal Runtime, including:

- cross-frame event explanation and summarization;
- relations between people, objects, regions, and time;
- combined video/audio interpretation;
- semantic identity reasoning beyond an authorized candidate signal;
- deciding whether an observation warrants an Interaction Proposal.

The model output remains a Runtime candidate/understanding. It cannot bypass privacy checks, Presence Router, action validation, or the normal result/audit path.

## 7. Privacy, retention, and failure boundaries

- Raw camera and microphone data are local by default; structured observations should be minimized and bounded too.
- Identity features, face embeddings, voice, and raw audio/video are sensitive and require explicit authorization, retention, and deletion behavior.
- `known_person_candidate` is opt-in and must not be treated as an unconditional identity assertion.
- Edge and Runtime both need bounded queues, expiry, deletion, and backpressure behavior.
- A disconnected or overloaded Edge reports health/availability and does not cause Runtime to infer that no person or event exists.
- Evidence upload is bounded, resumable or explicitly failed, and correlated to the originating Event.
- All accepted observations and understandings retain safe provenance without copying raw sensitive media into diagnostics by default.

## 8. Implementation sequence and non-goals

The first implementation sequence should be:

1. Register a fixed camera Edge and expose a small Feature Registry.
2. Implement one or two structured Features, such as `person_presence` and region entry/exit.
3. Add freshness-aware Observations, candidate Events, and local ring-buffer retention.
4. Add Runtime Feature Subscription and bounded Feature/Evidence queries.
5. Add Runtime video understanding and the `pending_understanding` lifecycle.
6. Validate the full Gateway boundary, privacy controls, retention, and human acceptance with a real fixed-camera scenario.

The first slice does not require continuous cloud video, full open-vocabulary detection, unrestricted face recognition, a general-purpose Edge agent, or packaged ambient-home hardware. Packaging and provisioning remain later product work under M22.
