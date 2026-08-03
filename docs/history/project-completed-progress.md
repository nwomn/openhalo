# OpenHalo Completed Progress Archive

> This archive preserves detailed historical acceptance notes. `Project.md` remains the canonical current project baseline; load this file only when historical evidence is relevant to the task.

## Completed Sub-goals

### Completed: M17.4 Mobile Edge product UI implementation

Result:

- The Android phone edge foreground is now a product UI rather than a developer diagnostics console: the top-level tabs are `Connect`, `Global Chat`, and `Settings`, with `Connect` as the launch/default product surface.
- `Connect` exposes the accepted product connection states through one large stateful control and keeps the relevant primary action visible for the current state.
- `Global Chat` provides a bounded local global-conversation projection with source labels and real local `HH:mm` timestamps, filters raw protocol/context noise out of the product conversation, anchors to the newest message, and keeps the composer correctly positioned above the Android keyboard.
- Phone-originated messages still submit through the existing `mobile.input` Edge API service path, preserving the normal `Device Edge -> Edge API -> Gateway -> Agent Runtime -> Presence Router -> Action Layer` boundary rather than introducing a phone-local chat shortcut.
- `Settings` now exposes normal user-facing controls for runtime URL, device name, notification/battery/background semantics, reset, clear cache, and build/version, while raw protocol controls, frame traces, token visibility, test notifications, and diagnostics cards are hidden behind a session-local 7-tap developer gesture.
- The repeated foreground-service notification regression from chat sends is fixed: phone-originated `mobile.input` submissions no longer recreate or re-alert the persistent "Presence edge session is running" notification on every send.

Acceptance evidence:

- `.\bin\test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (14 tests)`, covering the M17.4 product navigation, Global Chat, Settings semantics, and hidden diagnostics path.
- Visual QA compared the Android implementation with `docs/design/mobile-edge-ui/openhalo-mobile-edge-ui.pdf` and captured emulator screenshots under `tmp/m17_4_visual_qa/`, including the corrected keyboard-positioning screenshot `global_chat_keyboard_gap_fix_3.png`.
- Human acceptance on 2026-07-05 confirmed the first-version phone Edge UI is "像模像样" and good enough to close the first M17.4 product UI slice.

Status:

- Completed and accepted

### Completed: M17.3 Android Edge daily-use hardening

Result:

- The Android edge now provides a status-first daily home surface with foreground-service start/stop control, connection health, reconnect state, Android notification/full-screen-alert/battery health evidence, recent activity, notification/reply history, and a secondary diagnostics view
- Runtime mode, endpoint, device identity, and token configured state persist locally through Android shared preferences, while public diagnostics and frame displays avoid rendering secrets
- The foreground-service client owns the Edge API session, sends `mobile.context`, announces low-risk mobile capabilities, executes `notification.show`/`notification.alert`/`mobile.reply.render`, records bounded local history, and performs bounded reconnect/backoff with visible timestamps and disconnect reasons
- Phone-originated text commands are represented as public Edge API `event_push` frames with capability `mobile.input`, preserving the normal `Device Edge -> Edge API -> Gateway -> Agent Runtime -> Presence Router -> Action Layer` chain instead of introducing a phone-local chat shortcut
- Runtime-delivered notifications use the urgent alert presenter by default, and notification clicks or alert detail actions return to the app's notification/detail surface
- The Android testing workflow now uses an emulator-first path for normal app-surface regression, backed by JVM protocol/backoff tests, Compose instrumentation tests over stable tags, runtime-side mobile-edge routing verification, real-device installed-build smoke, and manual live-chain acceptance

Acceptance evidence:

- `bin/test_m17_android_emulator.ps1 -AvdName OpenHalo_M17` passed on `emulator-5554` with `OK (9 tests)`, after JVM protocol/backoff tests and APK assembly
- `.\.venv\Scripts\python.exe -B bin\verify_m17_mobile_edge.py` passed and reported `ok: true`, covering runtime-side phone-edge routing and lineage
- A real-device M17.3 installed-build smoke check passed with connection, foreground service, capability announcement, observation, and daily UI evidence
- Human acceptance on the user's phone confirmed that the app home/status flow, phone-originated input, terminal/runtime-to-phone notification path, action-result closure, background/lock-screen behavior, battery-setting handling, and reconnect behavior are good enough for the M17.3 bottom-layer capability baseline

### Completed: M17.2 native Android Presence Edge baseline

Result:

- The native Android app now acts as a first-class `Device Edge` over the public Edge API through a foreground `AndroidEdgeService`, with configurable development/persistent runtime selection, configurable Edge API token support, stable device identity, capability registration, WebSocket connection lifecycle handling, and no backend-internal imports or phone-specific runtime shortcuts
- The foreground Compose diagnostics surface exposes runtime mode, runtime URL, device ID, token configured/missing state without rendering the secret, connection state, service state, registered capabilities, recent observations, recent actions, in-app replies, last error, and last public Edge API frames
- The accepted low-risk Android capability surface includes `mobile.context` observations and runtime-to-phone `notification.show` execution; `notification.alert` is also registered as an explicit high-interruption alias, while camera, microphone, continuous screen interpretation, location, and richer local commands remain later mobile Sensor/Action Edge directions
- The Android phone-alert product decision is now explicit: phone-targeted runtime notifications must visibly pop up to count as effective alerts, so Android `notification.show` executes through the urgent alert presenter by default rather than relying on notification-shade-only delivery
- Runtime-side simulated verification covers Android-like routing and lineage with terminal source edge, Android target edge, competing candidate surfaces, `mobile.context` ingestion, `notification.show` dispatch, `action_result` handling, and interaction lineage preservation
- The adb-based real-device smoke verifier passed, reporting `ok: true`, `connected: true`, `service_foreground: true`, `sent_observation: true`, and registered capability evidence including `notification.show`, `notification.alert`, and `mobile.context`
- Manual live-chain acceptance passed on the persistent runtime path: from terminal edge, the user sent `给手机发送一个hello`, and the Android phone received a pop-up OpenHalo notification showing the delivered `hello` content
- The Android install and M17 Android acceptance docs now describe the runtime mode split, placeholder public endpoint, pairing credential handling, urgent `notification.show` behavior, and the adb/manual verification ladder
- The completion scope is explicitly a baseline/acceptance milestone rather than a daily-use mobile product milestone; long-term usability hardening remains future Android edge work

Acceptance criteria:

- The native Android app can act as a first-class `Device Edge` over the public Edge API with stable device identity, capability registration, WebSocket connection lifecycle, reconnect diagnostics, and no backend-internal imports or phone-specific runtime shortcuts
- The Android edge provides a foreground diagnostics surface that exposes connection state, runtime URL, device ID, last sent/received public Edge API frames, recent observations, recent action requests, and action results
- The Android edge can run as a constrained phone presence surface: background availability is attempted where Android policy allows, foreground/manual operation remains supported, and any background restriction or permission limitation is represented as context evidence rather than assumed away
- The accepted initial capability surface remains intentionally low-risk: `mobile.context` observations plus `notification.show` execution, with camera, microphone, continuous screen-use interpretation, location, and richer local command surfaces recorded as later mobile Sensor/Action Edge direction rather than M17.2 blockers
- The runtime can choose the Android edge as an intervention surface for a notification action while other candidate surfaces are present, and interaction lineage preserves the source edge, Android target edge, action result, and participant devices
- Automated verification includes runtime-side simulated routing/lineage coverage and an adb-based real-device smoke verifier for Android app connection and observation behavior
- Human acceptance demonstrates the full live chain from a non-phone source edge through the runtime to the Android phone edge, with inspectable action result and lineage evidence

Status:

- Completed and accepted

### Completed: M17.0 public Edge API boundary and internal-runtime encapsulation baseline

Result:

- The public Edge API boundary is documented in `docs/edge-api.md`, covering device registration, authentication shape, capability announcement, user events, observations, action requests, action results, interaction updates, errors, versioning, and compatibility expectations
- The runtime architecture baseline now includes an `M17.0` Edge API interaction flow diagram that shows terminal, host, and external edges using `Edge API v1` before traffic reaches `Gateway`
- A public `edge_api` package defines dependency-free `edge.runtime.v1` frame helpers so external edge authors do not need to import `personal_runtime` internals
- The official Python edge client now builds connect, capability, user-event, observation, and action-result frames through the public API wrapper
- The current terminal edge and host edge preserve their normal runtime behavior while using the public API envelope for edge/runtime traffic
- `Gateway` accepts versioned public frames, normalizes `observation_push` into the existing runtime observation path, supports capability object announcements, and emits versioned `connect_ok`, `event_ack`, `action_request`, `interaction_update`, and `error` frames
- `action_request` frames now carry a public `request_id`, while `interaction_id` continues to preserve interaction lineage through action results and post-action re-entry
- Automated tests include a raw external-edge simulation that connects through public API frames, announces capabilities, pushes an observation and user event, receives an action request, returns an action result, and preserves interaction lineage without importing runtime internals
- Fresh full verification passed with `.venv/bin/python -m unittest discover -s tests -v`, reporting 294 tests OK
- Human acceptance is recorded from real-use feedback that the actual M17.0 API path is stable enough for this milestone

Acceptance criteria:

- A written external Edge API contract exists
- Runtime internals are closed to edge authors behind `Edge API v1 -> Gateway`
- Terminal edge and host edge use the public API contract or official SDK wrapper
- The Python edge client is documented and tested as a convenience wrapper rather than the only integration path
- External-edge raw-frame automated coverage exists
- Existing runtime, terminal-edge, host-edge, model-provider, prompt-contract, proposal-formation, and action-loop tests pass after the API boundary refactor
- Human acceptance confirms the new edge API path is stable enough for the milestone

Status:

- Completed and accepted

### Completed: M17.1 registration-driven multi-device extension baseline

Result:

- The public Edge API now preserves and validates rich capability registration objects, including action metadata and observation-provider contracts, while keeping simple string capability announcements compatible for existing terminal and host edges
- `RuntimeState` now persists a device registry, capability registry, and observation registry, and restores older state payloads without registry fields
- `Gateway` now records rich capability metadata and nested observation schemas at public API ingress, rejects unregistered or schema-mismatched observations with public `error` frames, and keeps bounded compatibility defaults for current terminal and host observation providers
- `Execution Planning` now includes a registry-driven capability resolver sub-step after `Presence Router`, consumes registered provider metadata and online device state, filters invalid candidates, deterministically scores valid candidates, and emits an inspectable planning record
- Action dispatch now uses the finalized execution outcome from `Execution Planning`, while `Action Layer` remains responsible for building action frames rather than choosing semantic providers
- Chain inspection now includes an `Execution Plan` section with candidate, filtered-candidate, chosen-candidate, fallback, and rationale data for replay and later policy-learning work
- Automated coverage now includes rich mobile-style registration, strict observation rejection, schema mismatch rejection, registry persistence, planner candidate resolution, multi-surface phone/speaker/light routing, and dev-env verifier coverage
- Bounded manual acceptance is available through `bin/verify-m17-1-registration-extension --dry-run` and `bin/verify-m17-1-registration-extension`
- Fresh targeted verification passed with `.venv/bin/python -B -m unittest tests.test_protocol_v0 tests.test_edge_client_v0 tests.test_runtime_state_v0 tests.test_runtime_persistence_v0 tests.test_gateway_v0 tests.test_roundtrip_v0 tests.test_execution_planning tests.test_chain_inspection tests.test_dev_env_scripts -v`, reporting 145 tests OK
- Fresh full regression passed with `.venv/bin/python -m unittest discover -s tests -v`, reporting 342 tests OK
- Human acceptance evidence from the bounded verifier shows registered devices, registered capabilities, registered observations, accepted registered observation ingest, strict unregistered-observation rejection, phone notification selected as the primary action, and public speaker / ambient light candidates rejected with planner reasons

Acceptance criteria:

- Rich action-capability registration metadata is supported through the public Edge API
- Explicit observation registration metadata is supported through the public Edge API
- Device, capability, and observation registries are persisted while preserving existing terminal/host compatibility
- Gateway rejects unregistered and schema-mismatched observations with inspectable public errors
- New registered capabilities can participate in planning without device-type-specific runtime branches
- Execution Planning owns capability/provider selection after Presence Router and before Action Layer
- Capability selection uses registered metadata rather than a fixed `intent -> capability` table
- Planning records preserve chosen, fallback, filtered, rationale, and registry-reference data
- Diagnostics and chain inspection expose the Execution Planning / capability resolver boundary
- Automated and bounded manual acceptance cover the multi-surface registration-driven path

Status:

- Completed and accepted

### Completed: Module-boundary diagnostics v1 and runtime orchestration boundary baseline

Result:

- A neutral `openhalo_common` package now owns shared diagnostic primitives, including the structured `diagnostic.v1` event schema, in-memory diagnostic recorder, JSONL writer, correlation helpers, and backward-compatible lightweight trace recorder
- Device-edge runtime paths now use runtime-neutral diagnostics instead of importing `personal_runtime` tracing internals; dependency-boundary coverage verifies ordinary shared, terminal, and host edge runtime paths do not depend on backend internals
- Edge API frames now carry lightweight correlation fields such as `trace_id`, `session_id`, `turn_id`, and `event_id`, while runtime-generated `action_request`, edge-returned `action_result`, and runtime `interaction_update` frames preserve those identifiers and add `request_id` / `interaction_id` where applicable
- `RuntimeOrchestrator` now owns backend runtime-chain coordination for normal turns, direct actions, observation re-entry, and post-action re-entry, while `RuntimeGateway` remains focused on authentication, public frame validation/normalization, connection state, ingress persistence, event acknowledgements, and outbound WebSocket dispatch
- A real `Execution Planning` module now owns the proposal / presence-decision to action-or-completion outcome boundary on the normal runtime path
- Module-boundary diagnostics now record structured input/output events for the normal runtime chain across `Gateway`, `State / Context`, `Grounding / Runtime Memory`, `Proposal Formation`, `Presence Router`, `Execution Planning`, and `Action Layer`
- Edge-side diagnostics now record representative `Local Capability Runtime` and `Edge Session Link` boundary events for both text input normalization and observation frame preparation, so host-edge observation traffic also creates local JSONL diagnostics when `--diagnostic-log-path` is enabled
- Diagnostic recording is now starting to move inside module classes rather than being owned by the outer orchestration path: `Local Capability Runtime`, `Edge Session Link`, `Local Action Executor`, `Proposal Formation`, `Presence Router`, and `Execution Planning` each own their public input/output diagnostic boundaries, while lightweight coordinators such as `SessionClient` avoid writing downstream module logs
- Runtime, terminal-edge, and host-edge entrypoints now accept `--diagnostic-log-path` so manual multi-process acceptance runs can write physically separate local JSONL diagnostic logs without assuming shared frontend/backend storage
- Resident terminal live input now builds its `text.input` frames through the shared `SessionClient`, so manual terminal sessions carry `trace_id`, `session_id`, `turn_id`, and `event_id` like scripted/API edge traffic
- Gateway WebSocket dispatch now emits non-invasive `diagnostic.v1` records for cross-device reply delivery, including target connection presence and send status, and host-edge / terminal-edge local action execution now records its own `Local Action Executor` boundary without importing backend internals
- Host-edge startup observation handling now tolerates runtime observation errors without trapping later `action_request` frames behind an `event_ack` wait, and the compatibility runtime-health contract accepts unknown/null process start time while preserving strict observation validation elsewhere
- Chain inspection now includes `Diagnostic Events` alongside the previous trace, observation, snapshot, grounding, prompt, proposal, presence, intervention, replay, and action-result sections, so local acceptance can inspect architecture-module input/output records directly
- Automated coverage now includes diagnostic schema/JSONL behavior, correlation propagation, edge/backend dependency boundaries, runtime orchestrator delegation, execution planning outcomes, and chain-inspection diagnostic display

Acceptance criteria:

- Frontend and backend diagnostics use the same structured event shape while remaining locally recorded and physically separate
- Cross-boundary frames carry correlation identifiers that allow Edge and Runtime logs to be aligned without shared storage
- Manual runtime, host-edge, and terminal-edge processes can opt into local JSONL diagnostic logs through startup arguments
- Device-edge runtime code no longer depends on backend tracing internals for ordinary operation
- Gateway-to-runtime orchestration and execution planning are represented by explicit tested modules, with regression coverage ensuring `RuntimeOrchestrator` does not fall back to Gateway private runtime-chain implementations
- Inspect-chain output exposes module-boundary diagnostic events in the architecture chain

Status:

- Completed and accepted

### Completed: Project-level AGENTS enforcement baseline

Result:

- Project-level Codex hooks have been added in `.codex/hooks.json`
- Shared enforcement logic has been added in `agent_guard/codex_hooks.py`
- `AGENTS.md` now documents the internal per-turn audit and the conditional `Project.md Check` exception path
- Project progress updates are now also hook-enforced: when the user asks for a progress report, the response must include separate `Goal 1` through `Goal 5` sections with explicit architecture-aware labels for `状态`, `架构位置`, `本批完成`, `对整体链路的作用`, and `还缺什么`
- Edited turns are now also hook-enforced: when a turn uses `apply_patch`, the final response must include a `架构实现小结` block with explicit `架构位置`, `本步完成`, and `影响链路` labels
- A minimal automated test suite validates audit parsing and enforcement rules
- The hook entrypoint is now path-portable through `.codex/run_hook.py`, so `.codex/hooks.json` no longer hard-codes the repository checkout path

Acceptance criteria:

- The repository has project-level Codex hooks for session start and turn-end enforcement
- The enforced workflow validates that `Project.md` was read at session start
- The enforced workflow validates that every meaningful interaction performs a `Project.md` progress check
- The enforced workflow validates the required `Goal 1` through `Goal 5` architecture-aware structure for project progress updates
- The enforced workflow validates the required `架构实现小结` structure for edited turns
- The enforced workflow blocks inconsistent `Project.md` update claims while keeping normal responses free of mandatory visible audit output
- The hook configuration can survive repository folder renames by deriving the repository root from the checked-out project path

Status:

- Completed

### Completed: 3.1. Select the first project folder and documentation baseline

Result:

- A dedicated project folder has been created
- `Project.md` has been created as the project baseline document
- `AGENTS.md` has been created to guide future collaboration

Acceptance criteria:

- A dedicated root folder exists for the new project
- The project has a central document describing background, goals, and progress
- The collaboration contract for future Codex sessions is documented

Status:

- Completed

### Completed: Architecture orientation agreement

Result:

- The current direction is to split the system into `Device Edge` and `Personal Runtime`
- The backend is understood as a runtime core, not a generic web backend
- The system likely requires a `Gateway` or control-plane layer

Acceptance criteria:

- There is an explicit statement that the project is organized into frontend and backend halves
- There is an explicit statement that a central runtime/gateway layer is required

Status:

- Completed

### Completed: OpenClaw gateway reuse decision

Result:

- The project has moved past the stage where OpenClaw gateway reuse is needed to bootstrap a working runtime baseline
- The repository now has its own tested minimal protocol helpers, edge session client, and runtime gateway covering the current v0 and early M2 transport needs
- OpenClaw gateway server code is no longer treated as a primary reuse target for implementation
- `packages/gateway-protocol` and `packages/gateway-client` remain useful as reference material and possible selective inspiration, not as planned integration dependencies
- A minimal replacement gateway is now the active project path, with OpenClaw transport and protocol pieces retained only as optional future reference

Acceptance criteria:

- The project has an explicit decision on direct reuse versus replacement for the OpenClaw gateway server surface
- The decision reflects the current implementation baseline rather than only the earlier source audit
- The remaining role of OpenClaw protocol/client code is documented clearly enough to guide future work

Status:

- Completed

### Completed: Initial v0 runtime slice definition

Result:

- The first usable product slice is now defined as a single-edge closed loop
- The first-class v0 device surface is a desktop/CLI edge client
- The minimum v0 backend module set is `Gateway`, in-memory `State / Context / Task`, a same-device presence rule inside a minimal `Agent Runtime`, and an `Action Layer`
- The minimum v0 capability loop is `text.input -> event -> response -> notification.show`
- A concrete implementation plan has been written in `docs/plans/2026-06-16-v0-single-edge-loop-plan.md`

Acceptance criteria:

- The first milestone is small enough to implement without solving the whole system
- The v0 scope names which backend modules are first-class
- The v0 scope names which device surface is first-class
- The v0 path forms a complete user-visible roundtrip

Status:

- Completed

### Completed: First v0 implementation foundation batch

Result:

- The repository has been initialized as a git project with a safe `.worktrees/` workflow
- The Python project scaffold has been added with `pyproject.toml`
- The `personal_runtime` and `device_edge` package roots have been created
- Shared protocol helpers now validate supported v0 frame types and build `connect` frames
- In-memory runtime state and the same-device presence routing stub have been implemented
- Automated tests now cover scaffold imports, protocol helpers, and runtime state basics

Acceptance criteria:

- The repository can support branch and worktree based iteration safely
- The v0 scaffold can be imported as Python packages
- The shared protocol has a tested minimal contract for `connect` and frame validation
- The runtime has a tested minimal in-memory device/capability registry and same-device response rule

Status:

- Completed

### Completed: First v0 single-edge closed loop implementation

Result:

- A minimal `RuntimeGateway` now handles `connect`, `capability_announce`, and `event_push` frames
- A minimal `Agent Runtime` slice now generates text replies and the `Action Layer` converts them into `notification.show` requests
- A minimal `SessionClient` now builds connect, capability, and text-event frames and returns `action_result` payloads after local execution
- A minimal CLI edge runner can execute the whole loop locally from typed text input to printed notification output
- End-to-end tests now verify the single-edge roundtrip through gateway, edge session client, and local action execution
- Manual command-line verification now demonstrates the closed loop with `python3 -m device_edge.cli.cli_edge`

Acceptance criteria:

- The backend can accept the minimal v0 frame sequence and emit an action request
- The edge can execute the returned `notification.show` action and produce an `action_result`
- The single-edge roundtrip is covered by automated tests
- The loop can be exercised manually from the command line in the worktree

Status:

- Completed

### Completed: First real WebSocket single-edge closed loop

Result:

- The backend now exposes a real WebSocket gateway server path in addition to the in-process simulation helpers
- The edge session client now supports real WebSocket client roundtrips against an explicit runtime URL
- The runtime records returned `action_result` payloads in memory after local edge execution
- The project now uses a worktree-local `.venv` for Python dependency isolation, including `websockets`
- Manual verification now proves a true two-process flow: runtime server process plus CLI edge process over `ws://127.0.0.1`
- Automated tests now cover real WebSocket handshake, event delivery, action request delivery, and action-result return flow

Acceptance criteria:

- A local runtime server can bind a WebSocket endpoint and accept the minimal v0 frame sequence
- A local edge client can connect over WebSocket, send text input, receive an action request, execute it, and return an action result
- The real WebSocket path is covered by automated tests
- The real two-process loop can be exercised manually from the command line

Status:

- Completed

### Completed: Explicit direct-action fast path baseline

Result:

- The edge session client can now build an explicit `direct_action` event payload for urgent edge-requested actions
- The gateway now detects `direct_action` requests on `event_push` frames and converts them directly into `action_request` frames without going through the normal routed reply generation path
- Direct-action events are still appended to runtime state and persisted before dispatch so continuity and auditability are preserved
- Returned `action_result` payloads continue to be recorded and persisted through the shared gateway action-result path after local edge execution
- Automated tests now verify that a direct-action event bypasses the normal routing path while still being persisted

Acceptance criteria:

- An edge can send an explicit direct-action request through the normal gateway transport
- The gateway can bypass the normal `Agent Runtime` path for that request, including `Presence Router`, and emit the requested action directly
- The runtime still records the event and resulting action outcome in shared state on the existing persistence path
- The direct-action behavior is covered by automated tests

Status:

- Completed

### Completed: Minimal runtime continuity persistence

Result:

- Runtime state can now be serialized to and restored from a file-backed JSON snapshot
- The gateway now persists device registration, capability registration, recent events, and action results automatically after state changes
- The runtime server entrypoint now supports a configurable `--state-path` and restores state on startup
- The project ignores generated runtime snapshot directories so persistence artifacts do not pollute git state
- Automated tests now verify state serialization, state store load/save, gateway-triggered persistence, and runtime restart recovery

Acceptance criteria:

- Core runtime state survives process restarts through disk-backed snapshots
- State writes happen automatically on the main v0 state transition paths
- Runtime startup restores previously persisted state from disk
- The persistence path is covered by automated tests

Status:

- Completed

### Completed: First same-template multi-edge routing slice

Result:

- The runtime can now keep two live instances of the same edge template connected at once under different `device_id`s
- The normal routed path can now target another connected edge instance for `notification.show` instead of always replying to the source device
- The WebSocket gateway now maintains a minimal online connection registry so `action_request` frames can be delivered to a different live edge connection
- The ordinary routing path now prefers online peers and falls back to the source device when only offline residual device state is available
- Automated tests now cover capability-based target selection, sync cross-edge routing, real WebSocket cross-edge delivery, and fallback behavior when a peer is not online

Acceptance criteria:

- Two instances of the same edge template can connect to one runtime with distinct device identities
- A normal routed action can be delivered from one connected edge to another over the real WebSocket path
- The runtime still records events and action results correctly while routing across edge instances
- Offline residual device state does not hijack ordinary routed actions away from the currently active edge

Status:

- Completed

### Completed: Repository development environment workflow baseline

Result:

- The repository now documents a default shared-venv workflow in `docs/dev-env.md`
- The repository-level development workflow now also documents the local Android edge path, including opening `device_edge/android_edge/` in Android Studio, verifying devices with `adb devices -l`, and using Android Studio as the normal debug install/run surface for the first M17 phone edge
- `bin/test` now provides a server-safe root-venv helper: on systemd hosts it runs tests in one bounded transient service with private external networking, loopback fixture access, CPU/memory/task/wall-clock limits, descendant recovery, and nested-scope prevention; explicit local isolation opt-out remains available only through `OPENHALO_TEST_ISOLATION=0`
- Terminal Edge now bounds deferred inbound frames while awaiting a protocol acknowledgement, so a malformed or non-acknowledging peer fails explicitly instead of accumulating an unbounded in-memory queue; regression coverage reproduces and rejects the former 2 GiB OOM path, and the M20.2 server-side focused suite completes 69 tests in one bounded service
- M20.2 now streams visible pre-dispatch progress phases, including `executing`, through the Gateway while the synchronous Harness work is still pending, and Terminal renders those frames even while waiting for its event acknowledgement; the slow-Harness WebSocket regression requires `deliberating` to render before the final interaction result, while the action-chain regressions require `event_ack -> action_request -> awaiting_action_result` delivery and preserve the real source-Terminal action-output-before-post-action-progress order
- The M20.2 Android Edge advertises `interaction.progress`, safely reduces only authorized version-1 progress frames into bounded in-memory lifecycle state, clears it for terminal interaction states or session loss, and renders localized native phase feedback with a pulsing visual indicator in Global Chat. Incoming progress diagnostics are reconstructed from the safe public fields instead of retaining a raw frame. Android-focused coverage passes 17 unit tests, and both debug and instrumentation APKs build. User-reported local-development real-device acceptance on 2026-07-19 completed the acceptance gate; the session had exited before follow-up inspection, so its final evidence is not independently retained in a state or diagnostics artifact.
- `bin/bootstrap-worktree-venv` now provides an explicit opt-in path for isolated worktree environments during dependency or packaging experiments
- Automated tests now verify the helper scripts and the documented shared-versus-isolated environment rules
- The default day-to-day repository workflow is now explicitly branch-first in the main workspace, with worktrees kept as an advanced optional path rather than the normal baseline
- The repository now documents a verification ladder: CLI device tests are acceptable for early validation, while host-edge verification is required before calling a module implemented and operationally ready

Acceptance criteria:

- The default development workflow for ordinary branch work in the main workspace is explicitly documented
- The isolated worktree environment exception path is explicitly documented
- The repository includes helper commands for both modes
- The environment workflow is covered by automated tests
- The project-level documentation explicitly distinguishes early CLI validation from host-edge operational verification

Status:

- Completed

### Completed: First M3 presence-context foundation batch

Result:

- The runtime now has explicit shared context contracts for `Device`, `Capability`, and normalized `RuntimeObservation` records
- Runtime state can now store normalized observations with provenance separately from raw edge event details and round-trip them through serialization
- The project now has a first compact context snapshot reducer module for hot-path presence work
- The first snapshot field, `user.current_location`, now supports concrete value selection as well as explicit `unknown` and `ambiguous` outcomes
- Automated tests now cover the shared contract shapes, normalized observation storage, and compact snapshot reducer behavior

Acceptance criteria:

- Shared runtime context contract types exist for device, capability, and normalized observation records
- Runtime state can record and restore normalized observations with provenance
- A compact snapshot reducer exists for at least one presence-relevant field and preserves `unknown` / `ambiguous` outcomes when evidence is insufficient or conflicting
- The new context and snapshot foundation is covered by automated tests

Status:

- Completed

### Completed: First snapshot-driven presence decision slice

Result:

- The normal runtime path now builds a compact context snapshot from stored normalized observations before user-facing notification routing
- `Presence Router` now returns an explicit inspectable decision object rather than only a target device id
- The first live suppression rules now work on the hot path: ambiguous location context suppresses intervention, and a recent allowed intervention can suppress repeated follow-up actions when an explicit event timestamp is available
- The runtime now records intervention history separately from raw events and action results, and that history survives state serialization
- Automated tests now cover allowed intervention recording, ambiguous-context suppression, cooldown suppression, and intervention-history roundtrips

Acceptance criteria:

- The live runtime path evaluates an explicit presence decision before emitting a normal user-facing notification action
- The first presence decision slice can suppress at least one ambiguous-context case and one repeated-intervention case
- Intervention history is persisted as first-class runtime state for later policy refinement
- The new slice is covered by automated tests without regressing the existing v0 and M2 roundtrip behavior

Status:

- Completed

### Completed: First intervention-proposal live path slice

Result:

- The normal runtime path no longer jumps directly from compact snapshot into presence gating; it now builds an explicit inspectable intervention proposal first
- The early agent layer now exposes a minimal `InterventionProposal` shape for the normal notification path
- `Presence Router` now evaluates proposal-aware notification requests instead of inferring everything only from source device and capability lookup
- Allowed intervention history now records the proposal payload together with the later presence decision and target device choice
- Trace output and automated tests now cover the `snapshot -> proposal -> presence -> action` flow on the normal path

Acceptance criteria:

- The live normal path constructs an explicit proposal before evaluating a presence decision
- Presence evaluation can consume proposal data together with compact snapshot and intervention history
- Proposal-aware routing behavior is covered by automated tests without regressing existing roundtrip or host-edge behavior

Status:

- Completed

### Completed: First M4 mature host-edge runtime milestone

Result:

- The host edge can now run as an independent long-lived daemon process through `python -m device_edge.host.host_daemon`, rather than only as an in-process or one-shot control helper
- The host-edge runtime can now sustain continuous observation behavior with periodic idle-cycle sampling, post-action runtime-health follow-up, bounded reconnect/backoff handling, and bounded local observation history
- Runtime-scoped control remains available through the normal gateway path, including structured `runtime.status`, restart/recovery confirmation flow, and explicit edge-side history retrieval
- The repository now has both bounded automated verification and bounded local operational verification for the mature host-edge path, including `tests.test_host_daemon_v1`, `tests.test_roundtrip_v0`, and `bin/verify-host-edge`
- Manual verification visibility is now materially better on both sides of the edge boundary: the host daemon can emit local trace output, and the runtime now emits neutral startup readiness plus explicit edge-connected events to stdout

Acceptance criteria:

- The host edge can run stably as a standalone real edge surface outside the backend runtime process
- The host edge can continue or resume durable observation/control behavior across idle periods and backend disconnects instead of treating them as terminal failure
- The host-edge control path remains runtime-scoped and inspectable while preserving separate post-action health confirmation
- The host edge can be verified on its own through explicit edge-local and bounded end-to-end verification paths without waiting for later backend-maturity milestones

Status:

- Completed

### M4.1: Runtime-managed Host Edge lifecycle implementation

Result:

- Normal Runtime startup now creates one Runtime-owned supervisor only after Gateway is listening; `--disable-host-edge` remains the explicit opt-out for isolated fixtures and intentionally edge-disabled deployments
- The supervisor creates the ordinary `host-edge-1` session through the loopback WebSocket and public Edge API, preserving registration, capabilities, observations, actions, and action results without a backend shortcut
- `RuntimeState` now persists redacted managed-edge lifecycle status (`starting`, `retrying`, `connected`, `disconnected`), retry metadata, and safe exception classes only
- One supervisor handles indefinite bounded exponential retry with bounded random jitter, resets its delay after an accepted Edge API connection, and cancels the current session during Runtime shutdown
- Automated coverage proves delayed readiness/recovery, retry reset, cancellation, default enablement and opt-out, periodic observations, and a real routed `runtime.status` action through the managed public Edge API path
- Human acceptance on 2026-07-18 started only Runtime and an external source edge: Runtime logged automatic `host-edge-1` registration, persisted a successful `host-edge-1` `runtime.status` action result, and recorded managed-edge state `disconnected` after clean shutdown; no standalone `host_daemon` was launched

Acceptance criteria:

- Runtime-managed startup, recovery, diagnostics, shutdown, and public Edge API behavior meet the M4.1 criteria recorded above
- Human acceptance starts only Runtime plus a Terminal or other source edge, observes automatic `host-edge-1` registration, routes `runtime.status`, and confirms that no separately launched `host_daemon` is required

Status:

- Completed and accepted

### Completed: First M5 observation freshness and expiry slice

Result:

- Compact context snapshot building now supports an explicit snapshot reference timestamp instead of always treating the full stored observation history as equally current
- The first reducer-level freshness policy is now live for `user.location`, so stale location evidence ages out to `unknown` instead of continuing to drive presence decisions indefinitely
- The live gateway path now builds normal-path snapshots against the triggering event's decision time, which prevents expired conflicting location evidence from causing false ambiguity suppression
- Automated tests now cover stale-versus-fresh snapshot behavior and the live runtime path that must ignore stale conflicting location evidence during notification routing

Acceptance criteria:

- Snapshot reducers can evaluate freshness against an explicit reference time
- At least one presence-relevant field uses freshness filtering before returning a compact snapshot value
- The live gateway path uses a decision-time snapshot instead of a timeless observation-history read
- The new freshness slice is covered by automated tests without regressing the existing ambiguity and cooldown presence behavior

Status:

- Completed

### Completed: First M5 freshness-aware runtime health snapshot field

Result:

- The compact snapshot now exposes `runtime.current_health_state` as a first runtime-ingestion field derived from host-edge `runtime.health_state` observations
- Runtime-health snapshot values now use the same explicit snapshot-time freshness pattern as location evidence, so stale host-edge health reports age out to `unknown`
- The runtime can now carry one freshness-aware host-edge health signal in the compact snapshot without widening this batch into broader host-metric aggregation or policy changes
- Automated tests now cover fresh and stale runtime-health snapshot behavior alongside the existing location freshness slice

Acceptance criteria:

- The compact snapshot exposes at least one freshness-aware runtime-health field
- Stale runtime-health evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime-health snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slice

Status:

- Completed

### Completed: First M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_memory_pressure` as the first host-metric field derived from normalized `host.memory_pressure` observations
- Host memory pressure now uses the same explicit snapshot-time freshness pattern as location and runtime health, so stale host metric evidence ages out to `unknown`
- The runtime can now carry one compact freshness-aware host telemetry signal beyond runtime-specific health state without widening this batch into broader metric aggregation or agent-policy changes
- Automated tests now cover fresh and stale host memory pressure snapshot behavior alongside the earlier location and runtime health freshness slices

Acceptance criteria:

- The compact snapshot exposes at least one freshness-aware host metric field
- Stale host metric evidence resolves to `unknown` instead of remaining indefinitely current
- The new host-metric snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Second M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_cpu_load_ratio` as a freshness-aware host-metric field derived from normalized `host.cpu_load_ratio` observations
- Host CPU load now uses the same explicit snapshot-time freshness pattern as location, runtime-side snapshot fields, and host memory pressure, so stale host CPU evidence ages out to `unknown`
- The runtime can now carry a second compact freshness-aware host telemetry signal without widening this batch into threshold policy, metric aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale host CPU load snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a second freshness-aware host metric field
- Stale host CPU load evidence resolves to `unknown` instead of remaining indefinitely current
- The new host CPU snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Third M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_memory_available_bytes` as a freshness-aware host-metric field derived from normalized `host.memory_available_bytes` observations
- Host available memory now uses the same explicit snapshot-time freshness pattern as location, runtime-side snapshot fields, host CPU load, and host memory pressure, so stale host memory-availability evidence ages out to `unknown`
- The runtime can now carry a third compact freshness-aware host telemetry signal without widening this batch into threshold policy, metric aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale host available-memory snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a third freshness-aware host metric field
- Stale host available-memory evidence resolves to `unknown` instead of remaining indefinitely current
- The new host available-memory snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Fourth M5 freshness-aware host metric snapshot field

Result:

- The compact snapshot now exposes `host.current_memory_used_bytes` as a freshness-aware host-metric field derived from normalized `host.memory_used_bytes` observations
- Host used memory now uses the same explicit snapshot-time freshness pattern as location, runtime-side snapshot fields, and the other host-metric fields, so stale host memory-usage evidence ages out to `unknown`
- The runtime can now carry a fourth compact freshness-aware host telemetry signal without widening this batch into threshold policy, metric aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale host used-memory snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a fourth freshness-aware host metric field
- Stale host used-memory evidence resolves to `unknown` instead of remaining indefinitely current
- The new host used-memory snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: First M5 freshness-aware runtime process presence snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_present` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_present` observations
- Runtime process presence now uses the same explicit snapshot-time freshness pattern as location, runtime health, and host memory pressure, so stale process-presence evidence ages out to `unknown`
- The runtime can now carry a second compact runtime-health-adjacent host signal without widening this batch into presence decisions, agent behavior, or broader reducer refactoring
- Automated tests now cover fresh and stale runtime process presence snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process presence field
- Stale runtime process presence evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process presence snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: First M5 freshness-aware runtime process RSS snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_memory_rss_bytes` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_memory_rss_bytes` observations
- Runtime process RSS now uses the same explicit snapshot-time freshness pattern as location, runtime health, runtime process presence, and host memory pressure, so stale process-memory evidence ages out to `unknown`
- The runtime can now carry a third compact runtime-health-adjacent host signal without widening this batch into threshold policy, aggregation, or agent-behavior changes
- Automated tests now cover fresh and stale runtime process RSS snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process RSS field
- Stale runtime process RSS evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process RSS snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: Second M5 freshness-aware runtime process lifecycle snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_started_at` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_started_at` observations
- Runtime process start time now uses the same explicit snapshot-time freshness pattern as location, the other runtime-side snapshot fields, and the host-metric fields, so stale process-lifecycle evidence ages out to `unknown`
- The runtime can now carry a fourth compact runtime-health-adjacent host signal without widening this batch into restart heuristics, policy changes, or broader time-semantics work
- Automated tests now cover fresh and stale runtime process started-at snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process lifecycle field
- Stale runtime process started-at evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process started-at snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: First M5 freshness-aware runtime process identity snapshot field

Result:

- The compact snapshot now exposes `runtime.current_process_pid` as a freshness-aware runtime-ingestion field derived from host-edge `runtime.process_pid` observations
- Runtime process pid now uses the same explicit snapshot-time freshness pattern as location, the other runtime-side snapshot fields, and the host-metric fields, so stale process-identity evidence ages out to `unknown`
- The runtime can now carry a fifth compact runtime-health-adjacent host signal without widening this batch into restart heuristics, policy changes, or broader reducer refactoring
- Automated tests now cover fresh and stale runtime process pid snapshot behavior alongside the earlier M5 freshness slices

Acceptance criteria:

- The compact snapshot exposes a freshness-aware runtime process identity field
- Stale runtime process pid evidence resolves to `unknown` instead of remaining indefinitely current
- The new runtime process pid snapshot behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: M5 decision-time snapshot contract and evidence baseline

Result:

- `State / Context` now exposes a parallel decision-time snapshot contract view in addition to the compact field dict, so each snapshot field can be inspected as `value + status + bounded supporting evidence`
- The snapshot contract now records explicit field states for `fresh`, `stale`, `missing`, and `ambiguous` outcomes instead of leaving those semantics implicit inside reducer-local behavior only
- The compact hot-path API remains unchanged for current callers, while the broader runtime now has a stable inspection surface for replay, debugging, and later agent-side deeper reasoning
- Automated tests now cover fresh, stale, missing, and ambiguous contract states without regressing the earlier compact snapshot field-pack behavior

Acceptance criteria:

- The runtime exposes a decision-time snapshot contract alongside the compact snapshot field dict
- The contract makes freshness / ambiguity / evidence status explicit per field
- Supporting evidence remains bounded and inspectable rather than widening the compact snapshot into a raw-history mirror
- The new contract behavior is covered by automated tests without regressing the earlier M5 freshness slices

Status:

- Completed

### Completed: M5 gateway-to-presence input verification baseline

Result:

- The live gateway normal path now records the exact decision-time snapshot contract that was used when building a proposal and evaluating a presence decision
- Intervention history can now show whether runtime and host telemetry was consumed as fresh evidence or aged out as stale evidence on the real gateway path, rather than only proving that local reducers return the right value in isolation
- The runtime now has a concrete human-inspectable verification surface for M5 acceptance: recorded interventions include the compact decision input contract together with proposal, decision, reason, and target device
- Automated tests now cover live intervention recording for both fresh and stale runtime-health-adjacent telemetry without widening this batch into richer presence-policy changes

Acceptance criteria:

- The gateway normal path records the decision-time snapshot contract used for intervention evaluation
- Recorded interventions can distinguish fresh versus stale runtime/host telemetry on the live path
- The end-to-end verification surface is inspectable enough for human acceptance of M5 as a runtime-ingestion/context milestone
- The new live-path verification behavior is covered by automated tests without regressing existing gateway routing behavior

Status:

- Completed

### Completed: M5 runtime-ingestion and context-maturity milestone acceptance

Result:

- `M5` has now been accepted as complete using real host-edge input instead of relying only on inspection-injected sample observations
- The normal `Gateway -> State / Context -> Presence` path now has human-inspectable acceptance evidence across raw edge events, normalized observations, compact snapshot fields, explicit snapshot contract state, and recorded interventions
- Human acceptance can now inspect both runtime-side persisted evidence and edge-side daemon trace output for the same live decision-time chain
- The live-path acceptance pass also closed two real verification gaps: `python -m device_edge.cli.cli_edge --inspect-chain` now executes through the module entrypoint, and snapshot freshness reduction now accepts fractional-second observation timestamps emitted by the real host daemon

Acceptance criteria:

- `M5` is accepted through the normal gateway path using real host-edge telemetry
- Decision-time snapshot input remains inspectable in recorded intervention history rather than only through isolated reducer tests
- Human verification can inspect both runtime-side and edge-side evidence for the same live chain
- Real host-daemon timestamp shape does not break snapshot freshness evaluation on the live path

Status:

- Completed

### Completed: M6 dual-entry proactive runtime milestone acceptance

Result:

- The live runtime now supports both sense-first and agent-initiative proposal entry paths on top of the accepted M5 observation and snapshot surface
- The backend can now trigger an explicit `agent_initiative` proposal from runtime-owned state rather than relying only on an edge-originated text event to start the normal path
- Both entry paths now rebuild a decision-time compact snapshot and snapshot contract, form an inspectable intervention proposal, and converge on the same explicit `Presence Router` before action planning
- The accepted `M6` proposal-formation slice remains intentionally narrow: ordinary sense-first text input still collapses into a reply-shaped `notification.show` proposal rather than a fully generalized proposal-typing system
- The normal allowed path now supports both user-facing `notification.show` actions and narrow host-control actions such as `runtime.status` without falling back to the direct-action bypass
- Initiative proposals can now carry action payload, proposal source, bounded metadata, and a target-device hint while still remaining subject to cooldown and ambiguity suppression on the shared presence path
- The repository now has a dedicated M6 local inspection entrypoint: `python -m device_edge.cli.cli_edge --inspect-agent-initiative`, which prints trace, observations, snapshot, snapshot contract, proposal, presence decision, recorded intervention, and action result for one initiative-triggered run
- Automated tests now cover runtime-triggered initiative entry, cooldown suppression on the initiative path, CLI initiative triggering, initiative chain inspection, and a real websocket host-edge `runtime.status` roundtrip driven by runtime-side initiative dispatch

Acceptance criteria:

- The live runtime supports both sense-first and agent-initiative proposal entry on top of stable real-edge input
- Both proactive entry paths converge on the same explicit `Presence Router`
- Allowed actions can continue into at least one user-facing notification path and one narrow host-control path without using the direct-action bypass
- M6 behavior is covered by automated tests and a human-readable inspection path for manual acceptance

Status:

- Completed

### Completed: M9 cloud-model-backed agent baseline acceptance

Result:

- The runtime now has a formal provider boundary inside `Agent Runtime`, with runtime model configuration split into provider, model, and profile layers instead of hard-coded provider/model selection inside proposal-generation call sites
- The first accepted adapter path is a narrow but mature `openai_compatible` slice, preserving explicit `Presence Router` governance, inspectable proposal metadata, and bounded deterministic fallback behavior on the normal runtime chain
- Normal text replies now carry inspectable `llm_profile`, `llm_provider`, `llm_model`, and `used_deterministic_fallback` metadata through proposal recording and chain-inspection surfaces, so human acceptance can distinguish real model execution from local fallback behavior
- The repository originally accepted a tracked default `config/llm-config.toml`, explicit provider-level header configuration for future multi-provider compatibility hardening, and a runtime startup path that only used non-default LLM config when an explicit config path was provided; M15 has now moved real provider setup to ignored local `config/runtime-config.toml` plus tracked `config/runtime-config.example.toml`, keeping provider route, model/profile selection, and API key together in one runtime-owned config file
- The previously tracked CRS provider path passed the original Cloudflare `1010` gateway block after adding an explicit runtime `User-Agent`, but a fresh real-runtime recheck on 2026-06-25 still showed mixed behavior on the same `https://api-cf.cubence.com/v1` `/responses` route: at least one `crs_main` / `gpt-5.4` proposal call returned a valid structured `reply`, while later calls the same day returned completed payloads with empty `output` plus a Codex-agent instruction envelope instead of plain runtime response content, so that route should now be treated as a non-default comparative provider path rather than the tracked manual-acceptance baseline
- Runtime provider handling now treats that 2026-06-25 CRS response shape as an explicit incompatibility signal and surfaces the real failure reason to the user, rather than fabricating a conversational fallback or hiding the issue behind a generic parse miss
- A same-machine manual comparison on 2026-06-25 also showed that `master` could still complete ordinary natural-language terminal dialogue under the same resident terminal startup path, so the currently observed dialogue regression should no longer be treated as proven provider-wide outage by default; the stronger working hypothesis is now that the feat-branch runtime/provider changes introduced a branch-local regression on top of a still-usable upstream route
- Local runtime and CLI regression tests are now isolated from ambient machine-local config through explicit test config injection, so automated verification stays deterministic while non-default manual acceptance must opt in deliberately

Acceptance criteria:

- The runtime can use a real cloud model for proposal and reply generation through a formal provider/configuration boundary rather than a one-off hard-coded call path
- Real model-backed replies remain subject to the existing normal `Gateway -> State / Context -> Presence -> Action` chain instead of bypassing `Presence Router` governance
- Human inspection can distinguish real provider execution from deterministic fallback through recorded proposal metadata and existing local inspection entrypoints
- The first accepted implementation is covered by automated tests and verified end to end against at least one real `openai_compatible` provider path

Status:

- Completed

### Completed: M10 model grounding and runtime memory baseline acceptance

Result:

- The runtime now builds an explicit runtime-native grounding bundle for model-backed reply and proposal generation instead of passing only raw user text plus compact snapshot into the provider layer
- The first accepted grounding bundle is intentionally small and inspectable: it includes compact snapshot state, active runtime goals, bounded recent runtime memory for user inputs/interventions/action results, and a bounded edge-history window
- Durable runtime goals now live inside persisted `RuntimeState`, so active goal context survives restart and can shape later grounded model calls without inventing a separate side store
- Proposal metadata now records grounding provenance such as bundle version, active-goal count, recent-memory counts, and whether bounded edge history was attached, so inspection and replay can distinguish grounded runtime-native calls from thinner prompt shapes
- The local inspection chain now performs an explicit bounded `runtime.edge_history` retrieval through the host-edge control surface and prints the resulting `Grounding Bundle` alongside the compact snapshot, proposal, presence decision, and recorded intervention for human acceptance
- The repository now has targeted automated coverage for grounding-bundle construction, bounded recent-memory shaping, goal persistence shape, provider-request grounding injection, and inspection visibility for the first `M10` slice
- The resident terminal edge exit path has now been tightened so live `stdin` handling no longer relies only on a background-thread `readline()` path in normal TTY use; the daemon now prefers event-loop reader integration for real terminal input and explicitly cancels pending live-input tasks on session exit, reducing the previous need for repeated `Ctrl+C` to terminate the CLI device cleanly

Acceptance criteria:

- Model-backed proposal and reply generation are grounded in compact snapshot state, active runtime goals, bounded recent runtime memory, and explicit bounded edge-history retrieval rather than behaving like stateless channel chat
- Grounding remains runtime-native and inspectable instead of silently collapsing into opaque chat transcript prompting
- The first accepted implementation keeps edge-history retrieval explicit and bounded rather than continuously mirroring fine-grained device history into backend state
- Human inspection can verify the grounded bundle and proposal grounding metadata through an existing local acceptance entrypoint

Status:

- Completed

### Completed: M11 terminal/CLI interaction maturity acceptance

Result:

- The first resident terminal edge now has a thin but human-usable edge-local UX layer on top of the unchanged normal runtime chain, including readable `[system]`, `[user]`, and `[runtime]` session rendering instead of raw undifferentiated stdout output
- The preferred foreground terminal surface now also includes a first full-screen Textual `--tui` mode with a fixed status bar, scrollable transcript pane, and dedicated input box, while keeping the earlier line-oriented daemon path as a compatibility fallback on the same terminal-edge/runtime session chain
- The terminal daemon now keeps a bounded readable local transcript plus explicit session counters and visibility state, so a foreground terminal user can inspect recent interaction flow and current edge state without digging into backend state files
- The first local command affordances are now implemented directly on the terminal edge as edge-local ergonomics rather than backend special cases: `/help`, `/status`, `/history`, and `/quit` stay local to the edge and do not become normal `text.input` runtime traffic
- Resident terminal behavior remains compatible with the accepted presence-governed runtime architecture: normal user text still flows through the usual `Gateway -> State / Context -> Agent Runtime -> Presence Router -> Action Layer` path, while runtime push still depends on terminal activity evidence and explicit terminal target locking
- The bounded acceptance path now covers both the earlier M8 terminal behaviors and the new M11 CLI maturity affordances: `bin/verify-terminal-edge --dry-run` exposes the local command verification intent, and the real `bin/verify-terminal-edge` run now verifies one pull interaction, one active terminal push allow, one idle terminal push suppress, and persisted terminal-delivery evidence without depending on a provider-specific reply string
- The repository now has targeted automated coverage for local terminal command handling, readable session status/history output, runtime message rendering, resident-session behavior after live stdin EOF, and the updated terminal-edge verification/documentation surface

Acceptance criteria:

- The resident terminal edge exposes materially better session readability and human-usable local CLI affordances without introducing a backend-side chat exception path
- Local terminal commands stay edge-local and do not silently mutate the normal runtime protocol path
- Runtime-delivered terminal output remains presence-governed and verifiable on the real runtime chain rather than being faked through local-only shortcuts
- The milestone is covered by targeted automated tests plus a bounded real `bin/verify-terminal-edge` acceptance run

Status:

- Completed

### Completed: M12 prompt/context engineering and behavior-contract acceptance

Result:

- The runtime now has an explicit prompt/context assembly layer inside `Agent Runtime`, so grounded model-backed reply generation no longer formats compact snapshot and grounding state as ad hoc provider strings only
- The first accepted prompt/context package is versioned as `m12.v1` and keeps its inspectable sections intentionally small: `compact_snapshot`, `active_goals`, `recent_memory`, and bounded `edge_evidence`
- Proposal metadata now records explicit prompt/context provenance such as prompt version, section names, bounded section counts, and behavior-contract check results, so recorded interventions can show whether the normal runtime path actually carried the intended grounded state into the model-facing layer
- The local chain-inspection report now exposes `Prompt Context`, `Behavior Contract`, and `Replay Eval` sections as first-class inspection surfaces on the same live runtime chain that already prints observations, compact snapshot, grounding bundle, proposal, presence decision, and recorded intervention
- The repository now has a bounded local M12 acceptance entrypoint: `bin/verify-prompt-contract` prints one grounded inspection report, verifies the explicit prompt/context and behavior-contract surfaces, and confirms a replay/eval pass on the recorded prompt package without requiring a second provider call
- The repository now has targeted automated coverage for explicit prompt/context assembly, behavior-contract checks, provider-request prompt injection, prompt-contract inspection output, and the new verification/documentation surface

Acceptance criteria:

- Grounded model-backed proposal and reply generation use an explicit prompt/context assembly surface rather than only thin prompt wiring
- Prompt/context versioning is inspectable through recorded proposal metadata and local inspection output
- The runtime exposes a behavior-contract surface that verifies compact snapshot state, active goals, bounded recent memory, and bounded edge evidence are present and internally consistent with the grounding bundle
- A bounded replay/eval acceptance path can re-check the recorded prompt package locally without depending on a fresh provider response

Status:

- Completed

### Completed: M13 proposal-formation maturity acceptance

Result:

- The normal sense-first live chain can now emit inspectable runtime-owned proposal outcomes from ordinary edge-delivered text without bypassing `Presence Router`; after M17.6 hardening, normal outcomes are `action` and `no_intervention`
- Proposal formation now consumes compact snapshot state, active goals, bounded memory, and bounded edge evidence on the actual runtime path, while recorded interventions and inspection output expose structured proposal rationale together with provider/fallback metadata
- The provider boundary now supports structured proposal-plan parsing, provider proposal-type normalization, and deterministic grounded fallback when the model is unavailable, without adding a redundant middle interpretation layer beyond the documented hot path
- The live provider compatibility layer is now more tolerant of real structured-proposal response variants as well: string-valued actions such as `respond`, reply-text aliases such as `response`, and string rationale summaries are normalized onto the accepted `notification.show` / structured-rationale runtime shape instead of silently suppressing delivery after a successful model call
- The local inspection and acceptance ladder includes bounded M13 tooling: `python -m device_edge.cli.cli_edge --inspect-chain` prints proposal type and rationale on the live chain, and `bin/verify-proposal-formation` now exercises visible action, runtime-control action, and `no_intervention` scenarios end to end
- Fresh targeted automated verification and bounded human acceptance prove the runtime-owned proposal taxonomy on representative live terminal/runtime interactions, including the `no_intervention` path recording a proposal and ending with a suppressed action result instead of dispatch
- The accepted first `M13` slice still executes at most one current `primary action` per planning turn; that is an intentional implementation bound for the slice, not a claim that future interaction handling should remain permanently single-step
- The accepted `M13` boundary stops at first-turn proposal typing plus primary-action dispatch; post-action semantic handling remains intentionally out of scope here and is now promoted into explicit `M16` action-loop work rather than being represented by a completion-summary patch

Acceptance criteria:

- The normal live chain can emit inspectable `action` and `no_intervention` proposals from edge-delivered signals without bypassing `Presence Router`
- Proposal formation consumes compact snapshot state, active goals, bounded memory, and relevant edge evidence on the actual runtime path rather than falling back to raw text-only heuristics
- Proposal records expose enough structured rationale to inspect why a given input became a visible/side-effectful action or a no-intervention decision
- The accepted live-chain implementation does not grow redundant middle layers beyond the documented `event -> compact snapshot -> grounding bundle -> prompt/context package -> proposal formation -> Presence Router -> execution planning/action` shape
- Narrow deterministic fallbacks remain available when the model is unavailable, while the provider boundary stays ready for model-backed structured proposal output
- Automated tests cover visible user-facing actions, runtime-control actions, and ambiguity/suppression handling
- Human acceptance demonstrates action and no-intervention outcomes with readable inspection output on the live runtime path

Status:

- Completed
