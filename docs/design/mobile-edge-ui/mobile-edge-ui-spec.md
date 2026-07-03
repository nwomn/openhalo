# OpenHalo Mobile Edge UI Spec

Status: design baseline for `M17.4` Mobile Edge product UI implementation.

Source assets:

- `docs/design/mobile-edge-ui/openhalo-mobile-edge-ui.pix`
- `docs/design/mobile-edge-ui/openhalo-mobile-edge-ui.pdf`

## Product Position

OpenHalo Mobile Edge is the phone-side `Device Edge` for the user's
presence-first `Personal Runtime`. It is not a standalone chatbot and should
not become a mobile backend shortcut.

The foreground phone UI should stay small, calm, and product-grade. Its job is
to let a normal user connect the phone edge, view the global runtime
conversation, and adjust only the settings required for safe day-to-day use.
Diagnostics and developer controls remain secondary or hidden from the normal
foreground product surface.

Architecture boundary:

```text
Android Device Edge -> Edge API v1 WebSocket -> Gateway -> Personal Runtime
```

## Information Architecture

The product-facing app has three primary tabs:

1. `Connect`
2. `Global Chat`
3. `Settings`

The selected Pixso design already matches this shape:

- Connect page: large connection-state button as the visual signature.
- Global Chat page: cross-edge conversation view with source labels.
- Settings page: runtime endpoint, device name, permissions, and safe reset
  actions.

## Page 1: Connect

Purpose:

- Be the first screen after launch.
- Show whether this phone edge is connected to the user's runtime.
- Provide one obvious primary control for connect, disconnect, retry, or
  reconnect depending on state.

Important implementation note:

- The row of `Disconnected / Connecting / Connected / Error` controls in the
  Pixso design is a design-state selector, not a production control group.
- The production UI should show only the current state and the relevant primary
  action.

Required visible data:

- App title: `OpenHalo`.
- Current connection state.
- Runtime URL summary or endpoint label.
- Device name or identity summary.
- Connection health details when available:
  - latency
  - secure connection indicator
  - last successful connection time
  - last disconnect or error reason

Connection states:

- `needs_setup`: no usable runtime URL or required local permission is missing.
- `disconnected`: configured but not connected.
- `connecting`: connection attempt in progress.
- `connected`: WebSocket session is active and the edge has announced
  capabilities.
- `reconnecting`: bounded reconnect/backoff is in progress.
- `restricted`: Android permission, battery, background, or local network state
  limits expected operation.
- `error`: last attempt failed and needs a user-visible retry path.

Primary button behavior:

- `needs_setup`: open Settings or endpoint setup.
- `disconnected`: start/connect.
- `connecting`: disabled or cancellable depending on implementation maturity.
- `connected`: disconnect/stop edge session.
- `reconnecting`: show pending state and optional stop.
- `restricted`: open the relevant permission or system settings path.
- `error`: retry.

Visual requirements:

- The large circular connection button is the page's brand-level visual
  element.
- Button state should be legible without relying only on color.
- State text must fit on small Android screens and in Chinese localization.
- Avoid showing raw frames, logs, model provider state, or protocol traces on
  the Connect page.

## Page 2: Global Chat

Purpose:

- Show the user's global conversation with `Personal Runtime` across all
  participating edges.
- Let the phone send explicit user input into the normal runtime chain.

Product definition:

- This is a global conversation projection, not a phone-local chat session.
- Messages from terminal, phone, desktop, and future edges can appear in the
  same timeline.
- Phone-originated messages must still travel through the public Edge API and
  normal runtime chain.

Required visible data:

- Conversation title: `Global Chat` / `全局对话`.
- Sync/source summary, such as `跨设备 · 3 条设备记录`.
- Scrollable message history.
- Message composer.
- Send button.
- Connection-aware send state.

Message types:

- `user_message`: explicit user input from any edge.
- `runtime_reply`: natural language reply from `Personal Runtime`.
- `action_result_summary`: concise user-facing result of a runtime action.
- `system_notice`: quiet status note, such as sync, offline, or permission
  state.

Message metadata:

- `message_id`
- `conversation_id`
- `interaction_id` when available
- `source_edge_id`
- `source_edge_label`, for example `iPhone`, `MacBook Pro`, `Terminal`
- `sender_kind`: `user`, `runtime`, `system`, or `action`
- `created_at`
- `delivery_state`: `sending`, `sent`, `delivered`, `failed`, or `cached`

Global chat behavior:

- When online, the composer sends phone-originated input as public Edge API
  input through `Device Edge -> Edge API -> Gateway -> Agent Runtime ->
  Presence Router -> Action Layer`.
- When offline, previously cached global history may remain visible, but new
  sends should be disabled or explicitly queued.
- Source labels should be subtle but readable; do not label every bubble so
  heavily that the chat becomes a diagnostics feed.
- Runtime/action details should be summarized for users, not displayed as raw
  protocol events.

Open implementation questions:

- The current backend has interaction and intervention records, but the formal
  global conversation projection API still needs to be defined before the chat
  can be fully real-data-backed.
- Until that API exists, the UI may use a local projection model backed by
  runtime replies, phone-originated input history, notification/action
  summaries, and later synchronized conversation records.

## Page 3: Settings

Purpose:

- Expose normal user-facing configuration needed for daily operation.
- Keep developer/debug controls out of the product foreground.

Required sections:

- Runtime connection:
  - server/runtime URL
  - device name
  - connection protocol display
- Notifications and permissions:
  - push notification permission
  - background keepalive or battery restriction state
  - local network permission where relevant
- Operations:
  - reset connection
  - clear local cache
- About:
  - app version
  - build/channel summary when useful

Settings visibility rules:

- `Server URL` and `Device name` are editable user settings.
- `Connection protocol` should usually be read-only or hidden under advanced
  settings. A normal user should not need to choose WebSocket manually.
- Token, model provider, runtime profile, raw WebSocket logs, public Edge API
  frame traces, debug flags, and test fixtures must not appear on the normal
  Settings page.
- Diagnostics may remain available through a secondary developer/debug surface
  if required for M17 engineering, but it should not be the primary product
  page.

## Component Inventory

Top-level components:

- `MobileEdgeAppShell`
- `BottomNavigation`
- `ConnectScreen`
- `ConnectionStateButton`
- `ConnectionHealthSummary`
- `GlobalChatScreen`
- `ConversationMessageList`
- `ConversationMessageBubble`
- `MessageComposer`
- `SettingsScreen`
- `SettingsSection`
- `SettingsRow`
- `PermissionStatusRow`

Stable UI test semantics should cover:

- selected tab
- connection state
- primary connection action
- runtime URL display/edit entry
- global chat message list
- message composer
- send action
- settings rows for URL, device name, notification permission, background
  health, reset connection, and clear cache

## Data Mapping

Real data candidates already aligned with current M17 work:

- runtime URL from Android shared preferences.
- device identity from persisted Android edge config.
- connection state, reconnect state, last success, and last error from the
  Android edge service.
- notification permission, full-screen alert state, battery/background health,
  and local network permission from Android platform checks.
- phone-originated input and runtime-delivered notification/reply history from
  bounded local mobile event history.

Data that should remain mock or derived until a runtime API exists:

- complete cross-edge global conversation history.
- terminal/desktop message history synchronized into the phone.
- global conversation unread/sync counters.
- durable cross-device conversation search or pagination.

## Visual Direction

Design qualities:

- calm
- minimal
- trustworthy
- mobile-first
- production-grade
- sparse but not empty

Avoid:

- marketing hero layouts
- dashboard-heavy diagnostics as the first screen
- purple AI gradients
- decorative cards without operational meaning
- raw logs in product pages
- developer-only configuration in foreground settings

Typography and rendering notes:

- The PDF export shows jagged Chinese text in places due to design-export font
  rendering. The implementation should use Android system typography or the
  project-selected app font rather than trying to reproduce PDF glyph artifacts.
- Layout must support Chinese text without clipping.

## Acceptance Checklist

Before treating the UI implementation as product-ready:

- The app launches into the Connect page.
- Connect page renders all defined connection states.
- Only one primary connection action is shown for the active state.
- Global Chat can show cross-edge source labels in the same timeline.
- Offline chat state is understandable and does not silently drop user input.
- Settings expose only normal user-facing configuration.
- Developer diagnostics are secondary or hidden from the normal product flow.
- Desktop/PDF design assets are preserved in the repo for visual comparison.
- Compose UI tests use stable semantics for primary navigation and controls.
- Manual visual QA checks at least one small phone viewport and one modern large
  Android viewport.
