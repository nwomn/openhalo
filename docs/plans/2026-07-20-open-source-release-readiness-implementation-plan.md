# Open-Source Release Readiness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish the repository-level legal, security, contribution, dependency, and CI baseline needed for public source collaboration.

**Architecture:** Keep this work outside the Runtime hot path. Root policies establish collaboration and disclosure boundaries; the Python `dev` optional dependency group makes the existing test suite reproducible; GitHub Actions runs offline Python regression and Android local unit tests without credentials or a public Runtime.

**Tech Stack:** Python 3.11+, `pytest`, `coverage`, GitHub Actions, Gradle/JDK 17.

### Task 1: Add a Release-Baseline Regression Gate

**Files:**
- Create: `tests/test_open_source_release.py`

**Step 1: Write the failing test**

Assert that the root contains an MIT license, a private-reporting security policy, a safe contribution guide, a `dev` dependency extra with `pytest` and `coverage`, and a CI workflow that runs Python and Android unit tests.

**Step 2: Run the focused test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_open_source_release.py`

Expected: FAIL because the public-release files and `dev` extra do not yet exist.

**Step 3: Keep the test as a regression gate**

Do not make it reach into Runtime behavior. Its only job is to detect accidental removal of the publishable-repository baseline.

### Task 2: Add Repository Policies

**Files:**
- Create: `LICENSE`
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Step 1: Add the selected MIT license**

Use the canonical MIT license text with `Copyright (c) 2026 OpenHalo contributors`.

**Step 2: Add the security policy**

Require GitHub private vulnerability reporting, forbid public disclosure of sensitive reports, define supported pre-1.0 scope, and state the emergency fallback when the private-reporting form has not been enabled.

**Step 3: Add contribution boundaries**

Document the local install command, contained Python test command, Android unit-test command, documentation expectations, and credential/privacy rules. Contributions are offered under MIT.

**Step 4: Update both README entry points**

Link the policies, use the development extra in the development setup, and state that this alpha repository is not a public hosted Runtime. Do not claim that WSS transport or M17.8 privacy governance is finished.

### Task 3: Make Tests Reproducible and Add CI

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/ci.yml`

**Step 1: Declare development-only test tools**

Add `pytest>=9,<10` and `coverage>=7,<8` to `[project.optional-dependencies].dev`; leave runtime dependencies unchanged.

**Step 2: Add Python CI**

On pushes and pull requests to `master`, install `.[dev]`, run the complete Python suite through `coverage run` over `personal_runtime`, `device_edge`, and `agent_guard`, report coverage, and run `python -m pip check`.

**Step 3: Add Android CI**

On the same triggers, provision JDK 17 and Android SDK, then run `bash ./gradlew testDebugUnitTest` from `device_edge/android_edge`. The workflow must not require runtime tokens, pair codes, a device, or a public endpoint.

### Task 4: Verify the Public Collaboration Baseline

**Files:**
- Modify: `Project.md`

**Step 1: Run focused release checks**

Run: `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_open_source_release.py`

Expected: PASS.

**Step 2: Verify an isolated installation**

Create a temporary virtual environment outside the checkout, install `.[dev]`, run the focused check and the full Python suite, then delete the temporary environment.

**Step 3: Run Android local unit tests**

Run: `cd device_edge/android_edge && bash ./gradlew testDebugUnitTest --console=plain`

Expected: BUILD SUCCESSFUL.

**Step 4: Record scope accurately**

Update `Project.md` to mark the source-collaboration baseline complete while retaining TLS/WSS transport and M17.8 sensitive-screen governance as public Runtime release gates.

**Step 5: Commit and push**

Run the complete verification suite, review the diff for credentials, commit on `master`, and push `origin master`.
