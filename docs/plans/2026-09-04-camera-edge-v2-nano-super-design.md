# Camera Edge v2 — Jetson Orin Nano Super Validation Design

Status: September 2026 validation plan. This is a separate Camera Edge v2
line, not an expansion of the completed MaixCAM-based Camera Edge v1 validation
and not a production-hardware decision.

## 1. Objective

Validate room-scale reality sensing for one fixed high-mounted camera in a
roughly 5 m × 5 m bedroom or workspace. A confirmed visual or audio change
must yield a short free-form natural-language event label within five seconds
at P95, then enter Personal Runtime as bounded evidence for context and
Presence-governed behavior.

Examples are descriptive rather than an activity enum: “you stood up and
turned toward the desk”, “you stopped typing and picked up the phone”, or
“the action is partly occluded”. `unclear` is a correct output when the source
does not support a reliable description.

## 2. Hardware boundary

- Host: Jetson Orin Nano Super Developer Kit, 8 GB.
- Camera: separately verified 4K/30 camera, with its exact sensor, lens,
  resolution/frame-rate modes, and Jetson driver support recorded before it is
  accepted as the v2 source.
- Audio: use the bundled microphone/speaker hardware only after its Linux/
  Jetson input/output interfaces and driver behavior are verified.
- Storage and cooling: NVMe and active cooling are required for bounded local
  video buffering and sustained validation.

The hardware is a validation host. It does not choose the later production
Camera Edge or M24 cellular hardware.

## 3. Processing path

```text
4K source retained locally
  -> 720p/960p whole-frame detector, tracker, and change signals
  -> confirmed change and person/region selection
  -> 4K person/hand/desk/bed ROI plus bounded pre/post-change context
  -> local or LAN low-latency visual/audio understanding worker
  -> natural-language event-label evidence
  -> Edge Session Link -> Gateway -> ContextFact/ContextEnvelope
  -> Runtime context, Presence, and governed response/action
```

Whole-frame sensing is a frequent low-latency path; detailed semantic
understanding is event-triggered. The design must not run unrestricted VLM
reasoning over every full 4K frame.

## 4. Evidence contract

Every v2 event-label envelope includes at least:

- `source` and device/model versions;
- event `interval`, observation time, and pre/post coverage or coverage gap;
- label text, confidence, and explicit uncertainty/limitation;
- local evidence reference and retention availability, never raw media by
  default.

The label is evidence, not an authoritative owner identity, user intent,
command, or action authorization. Runtime alone admits ContextFacts and applies
Presence, privacy, permission, action validation, and result recording.

## 5. September acceptance gates

1. Sustained 4K source capture, bounded local buffer, thermal stability, and
   known camera mode/frame-rate evidence.
2. Whole-frame change/person tracking operates continuously without requiring
   a semantic-model request for every frame.
3. From a confirmed change, natural-language label completion is P95 <= 5 s;
   measure detector confirmation, ROI/evidence selection, understanding,
   transport, and Runtime admission separately.
4. Labels and their provenance reach Runtime through the ordinary authenticated
   Edge Session Link and are materialized as bounded context evidence.
5. Runtime combines the label with broader context; no label alone triggers a
   user-facing or external action.
6. Test the bedroom and workspace at near and far positions, desk/bed regions,
   occlusion, low light, and `unclear`/failure behavior.

## 6. Explicit non-goals

- Error-free person identity or open-world activity understanding from one
  camera.
- A production hardware lock, moving-camera acceptance, or automatic action
  from perceived interaction.
- Continuous raw audio/video upload or Runtime persistence of raw media.
- Reopening, changing, or reclassifying Camera Edge v1 acceptance evidence.

## 7. Relationship to v1

Camera Edge v1 used the received MaixCAM to validate bounded Feature,
authentication, and Edge-to-Runtime contract behavior. Its resolution and local
compute did not satisfy this room-scale semantic-perception target. Camera Edge
v2 reuses only the public Device Edge, evidence, ContextFact, and Presence
boundaries; its hardware, capture pipeline, semantic worker, and acceptance
criteria are independent.
