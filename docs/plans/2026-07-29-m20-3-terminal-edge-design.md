# M20.3 Terminal Edge Design

**Status:** Accepted design baseline; implementation not started.

**Goal:** Turn the resident terminal into a stable, attractive, long-running `Device Edge` without turning it into an agent host, a Runtime console, or a shell/tool console.

## Architecture Position

Terminal Edge remains a separate process with one resident public Edge API session:

```text
Terminal TUI -> Terminal Edge local reducer -> Edge Session Link -> Gateway -> Personal Runtime
```

The Edge owns local rendering, composer input, bounded local transcript and receipt state, TTY handling, reconnect behavior, and execution of authorized Edge actions. The Runtime owns proposal formation, Presence, planning, cross-device selection, action dispatch, result correlation, and the authoritative interaction lifecycle.

Terminal Edge must not import Runtime modules, run Hermes, host a local agent loop, invoke shell tools, read Runtime state, or query Runtime execution traces. Every cross-boundary fact arrives through an authenticated, versioned public Edge API frame. A click or keypress expands only receipt data already delivered and retained locally.

## Quiet Edge

`Quiet Edge` is the default visual language. It is a calm personal terminal surface rather than a coding-agent dashboard.

- A thin persistent header shows OpenHalo identity, the local Edge identity, and a human-readable connection state.
- The central scrollable transcript distinguishes user input, OpenHalo's visible outcome, connection/system state, cross-device delivery, and public progress using restrained typography and spacing rather than noisy cards or tool logs.
- The active interaction occupies one small inline progress row while work is ongoing. It updates from M20.2 public phases and clears or settles without altering action ordering.
- A fixed composer stays visible. It supports keyboard-first send, history, slash-command discovery, draft preservation, cancellation, and help. It never becomes a raw Runtime or shell command prompt.
- The line-oriented non-TTY mode preserves the same semantic categories as readable text output.

The high-density `Command Atelier` exploration remains a possible later focus view, but is not the M20.3 default or acceptance target.

## Settled Outcome Receipts

Every visible settled interaction uses a compact receipt in the transcript when it has a meaningful public outcome. The collapsed form is one quiet, scannable row such as:

```text
+ Arrangement completed - Maya's Phone confirmed - 10:43
```

Keyboard focus plus `Enter` or `Space`, and pointer activation where supported, expand or collapse the receipt. Expanded content is a local timeline, for example:

```text
Friday writing time                                  Completed
10:42  Terminal Edge received the request
10:42  OpenHalo started arranging
10:42  Delivered to Maya's Phone
10:43  Maya's Phone confirmed completion

Friday 14:00-17:00 is reserved for writing.
```

This is an execution *outcome* receipt, not an execution trace. The interface must not reveal private reasoning, prompts, provider/model information, Hermes/Nous identity, tool names, tool arguments/results, internal module names, raw device diagnostics, opaque device IDs, internal request IDs, or untrusted remote content.

When a device is relevant to an authorized visible outcome, the receipt displays its real Runtime-registered human-readable name, not a routing identifier. Device names are included only for the requester or other recipients already authorized for the interaction.

## Public Receipt Projection

The current public `interaction_update` frame is the correct delivery surface because it already delivers a settled interaction outcome to the requesting Edge. M20.3 may add an optional `outcome_receipt` object inside its `interaction` payload; it must be additive and safely ignorable by existing Edges.

```json
{
  "type": "interaction_update",
  "interaction": {
    "interaction_id": "interaction-123",
    "status": "completed",
    "summary": "Friday 14:00-17:00 is reserved for writing.",
    "outcome_receipt": {
      "version": 1,
      "state": "completed",
      "entries": [
        {"sequence": 1, "kind": "request_received", "occurred_at": "..."},
        {"sequence": 2, "kind": "delivery", "device_name": "Maya's Phone", "occurred_at": "..."},
        {"sequence": 3, "kind": "confirmed", "device_name": "Maya's Phone", "occurred_at": "..."}
      ]
    }
  }
}
```

`kind` is an allowlisted public semantic enum. Terminal localizes it into concise readable text. Runtime validates every displayed device name against the authorized interaction participant set before Gateway delivery. The receipt contains no free-form tool or diagnostic body. Existing Edges that do not understand the field continue to use `summary`; Terminal safely degrades to the same result-first presentation when the field is missing, malformed, stale, or unauthorized.

## Lifecycle And Recovery

The local reducer correlates public progress and outcome data by `interaction_id`, accepts monotonic sequence numbers, and bounds retained receipt history. A later progress frame cannot reopen a settled receipt. Connection loss marks only local presentation state as disconnected, settles any active indicator, preserves the draft and completed safe receipts, and never creates a synthetic result. On reconnect, the Edge resumes through the normal public session and accepts only newly authorized frames.

No local receipt operation waits for, changes, or observes Runtime execution. Runtime action dispatch and result handling remain correct even when Terminal is disconnected, rendering slowly, or in non-TTY fallback mode.

## Acceptance Additions

- Unit tests cover receipt schema rejection, device-name authorization, timeline ordering, stale/duplicate entry rejection, compact/expanded reducer behavior, keyboard activation, and absence of forbidden fields.
- TUI tests cover narrow/wide layout, long device names, long final summaries, transcript ordering, reflow, reconnect, draft preservation, and non-TTY text parity.
- A human run covers a slow visible interaction, a cross-device action with an involved device's real display name, receipt expansion and collapse, disconnect/reconnect, resize, and clean exit.
- Protocol tests prove a legacy Edge can ignore `outcome_receipt` without affecting interaction delivery or execution.
