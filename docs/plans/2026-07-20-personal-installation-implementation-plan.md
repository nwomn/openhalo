# Personal Installation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Deliver a personal-owner OpenHalo Runtime and Terminal Edge installation that exposes global commands, persists user data in one `~/.openhalo` home, and can be safely installed, upgraded, or removed without system-service administration.

**Architecture:** The installed command is a Python console entry point, not a wrapper around a repository checkout or a systemd unit. It resolves `OPENHALO_HOME` (default `~/.openhalo`) into private configuration, runtime state, pairing records, logs, and a PID file; Runtime release programs remain separate under `~/.local/share/openhalo/releases`. The Runtime supervisor launches the existing `personal_runtime.main` with explicit home-derived paths, and `openhalo-edge` stores a terminal-specific paired-device credential in that same personal home before delegating to the existing Terminal Edge daemon.

**Tech Stack:** Python 3.11+, setuptools console scripts, standard-library JSON/TOML path handling, `subprocess`, `venv`, `websockets`, `unittest`/`pytest`, GitHub immutable commit or Release artifacts.

### Task 1: Personal Home and Secure Configuration

**Files:**
- Create: `openhalo/__init__.py`
- Create: `openhalo/home.py`
- Create: `tests/test_personal_home.py`

**Step 1: Write failing tests**

Cover default and `OPENHALO_HOME` path resolution, private directory/file modes, atomic configuration writes, preservation of a terminal-edge section while Runtime setup changes, and rejection of malformed configuration.

**Step 2: Run the focused test and verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_personal_home.py`

Expected: import failure because `openhalo.home` does not exist.

**Step 3: Implement the minimal personal-home model**

Create a single JSON configuration document under `~/.openhalo/config.json`, explicit paths for Runtime state, pairing registry, diagnostics, Runtime log, PID, and a copied Runtime model configuration. Use secure atomic writes and mode `0600` for files that can contain credentials.

**Step 4: Run the focused test and verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_personal_home.py`

Expected: PASS.

### Task 2: Runtime Lifecycle Supervisor

**Files:**
- Create: `openhalo/runtime_supervisor.py`
- Create: `tests/test_runtime_supervisor.py`

**Step 1: Write failing tests**

Cover command construction from the personal configuration, a detached start that writes a PID, idempotent start, stale PID detection, safe stop refusal for a non-OpenHalo process, and bounded log tailing.

**Step 2: Run the focused test and verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_runtime_supervisor.py`

Expected: import failure because `RuntimeSupervisor` does not exist.

**Step 3: Implement the smallest safe supervisor**

Launch the existing Runtime with explicit state/pairing/config/log paths and the owner secret through an environment variable. Keep the Runtime loopback by default, require an identifiable OpenHalo process before signaling it, and leave the legacy systemd service untouched.

**Step 4: Run the focused test and verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_runtime_supervisor.py`

Expected: PASS.

### Task 3: Global Runtime Command

**Files:**
- Create: `openhalo/cli.py`
- Create: `tests/test_openhalo_cli.py`
- Modify: `pyproject.toml`

**Step 1: Write failing tests**

Specify `openhalo setup`, `start`, `stop`, `status`, `logs`, `doctor`, `pair`, `devices`, and `revoke` against a temporary `OPENHALO_HOME`. Assert JSON output never includes the Runtime shared token or paired device credentials.

**Step 2: Run the focused test and verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_openhalo_cli.py`

Expected: import failure because the global CLI entry point does not exist.

**Step 3: Implement the command surface**

Register the `openhalo` console script in `pyproject.toml`. `setup` creates the home and an editable model-config template or securely imports an explicit model config; pairing commands use the existing `PairingStore` through home-derived paths. Keep command output safe and user-facing.

**Step 4: Run the focused test and verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_openhalo_cli.py`

Expected: PASS.

### Task 4: Paired Terminal Edge Command

**Files:**
- Create: `openhalo/edge_cli.py`
- Create: `tests/test_openhalo_edge_cli.py`
- Modify: `edge_api/protocol.py`
- Modify: `device_edge/shared/edge_session_link.py`
- Modify: `device_edge/shared/session_client.py`
- Modify: `device_edge/cli/terminal_daemon.py`

**Step 1: Write failing tests**

Cover `openhalo-edge setup --url --pairing-code`, receipt and private persistence of the issued device credential, use of `auth.kind=device` for later Terminal Edge connections, a clear unconfigured error, and delegation to the existing Terminal daemon without exposing the credential in output.

**Step 2: Run the focused test and verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_openhalo_edge_cli.py`

Expected: import failure because `openhalo.edge_cli` does not exist.

**Step 3: Implement the pairing handoff**

Use the existing public Gateway pairing exchange, persist only the returned per-device credential in the home configuration, and add an opt-in `auth.kind` parameter to the existing session client while retaining legacy defaults for tests and the managed Host Edge.

**Step 4: Run focused edge and protocol tests and verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_openhalo_edge_cli.py tests/test_protocol_v0.py tests/test_terminal_daemon_m8.py`

Expected: PASS.

### Task 5: Immutable Release Installer and Update Boundary

**Files:**
- Create: `openhalo/release_manager.py`
- Create: `scripts/install.sh`
- Create: `tests/test_release_manager.py`
- Modify: `openhalo/cli.py`

**Step 1: Write failing tests**

Cover parsing a release manifest, SHA-256 verification, refusal of `main`/`master` references, staged installation before an atomic `current` switch, retention of the prior release on health-check failure, and explicit failure when no release feed is configured.

**Step 2: Run the focused test and verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_release_manager.py`

Expected: import failure because the release manager does not exist.

**Step 3: Implement the minimal immutable-release path**

The installer accepts only an explicit immutable commit or Release artifact, creates the versioned program directory, installs console scripts, and selects a `current` release atomically. `openhalo update --check`, `openhalo update`, and `openhalo rollback` operate only from a configured signed/checksummed manifest; they never fall back to a branch checkout or reset personal data.

**Step 4: Run the focused test and verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_release_manager.py`

Expected: PASS.

### Task 6: Documentation, Acceptance, and Legacy Cleanup

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/runtime-deploy.md`
- Modify: `Project.md`

**Step 1: Document only the owner-facing workflow**

Document installation, setup, Runtime lifecycle, pairing, Terminal Edge setup, update/rollback, and clean removal. Retain an explicit transition note for the existing systemd deployment without presenting it as the product mode.

**Step 2: Run verification**

Run: `git diff --check`

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_personal_home.py tests/test_runtime_supervisor.py tests/test_openhalo_cli.py tests/test_openhalo_edge_cli.py tests/test_release_manager.py`

Run the full Python suite through `bin/test`.

**Step 3: Clean the legacy deployment after code verification and push**

Confirm the old `openhalo-runtime.service` is the only target, stop and disable it, remove the service unit and its `/opt/openhalo`, `/etc/openhalo`, `/var/lib/openhalo`, and `/var/log/openhalo` artifacts, reload systemd, and verify port `8765` is unused. Do not remove `/root/openhalo` or the separate `18765` development path.

**Step 4: Commit and push**

Commit the tested implementation directly to `master`, push it, and provide the immutable installation reference for the clean-server test.
