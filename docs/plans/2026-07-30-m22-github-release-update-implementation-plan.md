# M22 GitHub Release Update Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Let an installed owner update a running Personal Runtime from the latest stable GitHub Release through `openhalo update`, with archive verification, atomic program switching, readiness validation, and automatic rollback.

**Architecture:** `GitHubReleaseFeed` reads only the public GitHub Release API for `nwomn/openhalo`, rejects draft or prerelease releases, and resolves the release manifest and source archive from its declared assets. `ReleaseUpdater` stages the verified archive below the existing private immutable release root, then coordinates the existing `RuntimeSupervisor`: it stops a running Runtime, activates the candidate with `ReleaseLayout`, starts it with the candidate release's Python executable, and restores the prior release if candidate startup fails. `OPENHALO_HOME` remains untouched; this slice rejects neither compatible state nor changes it, because persistent-state migrations are not yet defined.

**Tech Stack:** Python 3.11+, standard-library `urllib`, `json`, `tarfile`, `venv`, `subprocess`, existing `ReleaseLayout` / `RuntimeSupervisor`, pytest, GitHub Releases API.

### Task 1: Specify the GitHub Release Contract

**Files:**
- Modify: `openhalo/release_manager.py`
- Modify: `tests/test_release_manager.py`
- Create: `tests/test_github_release_feed.py`

**Step 1: Write the failing release-feed tests**

Create fixtures for a GitHub `releases/latest` response, `release-manifest.json`, and a source archive. Require all of the following:

- draft and prerelease metadata are rejected;
- the release contains exactly one `release-manifest.json`, one matching archive asset, and one `SHA256SUMS` asset;
- the manifest has a non-empty version, an exact 40-character lowercase commit, an archive filename, an SHA-256 digest, and a tag matching the GitHub Release tag;
- the `SHA256SUMS` entry agrees with the manifest;
- all resolved asset URLs are HTTPS.

**Step 2: Run the focused test to verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_github_release_feed.py`

Expected: FAIL because `GitHubReleaseFeed` does not exist.

**Step 3: Implement the minimal release feed**

Add immutable `ReleaseManifest` fields for `tag`, `archive_name`, and `sha256`. Add `GitHubReleaseFeed.latest()` with injectable JSON downloader for tests. It calls `https://api.github.com/repos/<owner>/<repo>/releases/latest`, validates the response and asset names, then returns a manifest with the trusted archive asset URL attached. Do not support branch names, `target_commitish`, arbitrary URLs from the manifest, or unauthenticated redirect targets.

**Step 4: Run the focused test to verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_github_release_feed.py tests/test_release_manager.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add openhalo/release_manager.py tests/test_github_release_feed.py tests/test_release_manager.py
git commit -m "feat: resolve verified GitHub releases"
```

### Task 2: Stage a Verified Candidate Without Touching Personal Data

**Files:**
- Modify: `openhalo/release_manager.py`
- Modify: `tests/test_release_manager.py`

**Step 1: Write the failing staging tests**

Test that a valid archive is downloaded to a private temporary directory, checked against both digest sources, extracted only after rejecting traversal/symlink escapes, installed into `releases/<commit>/venv`, and leaves `current`, `previous`, and a supplied `OPENHALO_HOME` fixture unchanged until activation. Verify failure cleans temporary content and never creates a partial release directory.

**Step 2: Run the focused test to verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_release_manager.py`

Expected: FAIL because the staging API does not exist.

**Step 3: Implement minimal private staging**

Add `ReleaseStager.stage(manifest) -> Path`. Use a `.staging-*` sibling under the release root, stream-download the resolved HTTPS archive, verify SHA-256 before extraction, enforce safe tar members, create a venv, and install the extracted source. On success atomically rename staging to the commit directory; on error remove staging. Existing release directories are reused only if they contain the expected `venv/bin/python` executable.

**Step 4: Run the focused test to verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_release_manager.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add openhalo/release_manager.py tests/test_release_manager.py
git commit -m "feat: stage verified release archives"
```

### Task 3: Orchestrate Running Runtime Update and Recovery

**Files:**
- Create: `openhalo/updater.py`
- Modify: `openhalo/runtime_supervisor.py`
- Create: `tests/test_updater.py`
- Modify: `tests/test_runtime_supervisor.py`

**Step 1: Write the failing update tests**

Use fake layout, stager, feed, and supervisor factories to specify:

- `--check` reports `up_to_date` or `update_available` without staging or restarting;
- a stopped Runtime stages and activates the candidate without starting it;
- a running Runtime stages before stopping, stops fully, switches `current`, launches from `releases/<commit>/venv/bin/python`, and reports candidate health only after the ready file exists;
- failed candidate startup restores the old `current`, starts the old executable, and reports a structured `rolled_back` result;
- a failed stage or refused state transition does not stop the current Runtime;
- manual `rollback` requires a previous release and preserves whether the Runtime was running.

**Step 2: Run the focused test to verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_updater.py tests/test_runtime_supervisor.py`

Expected: FAIL because the updater module and executable override do not exist.

**Step 3: Implement the smallest reliable orchestration**

Add an optional runtime Python executable to `RuntimeSupervisor` and a bounded `wait_until_stopped()` method. Add `ReleaseUpdater.check()`, `update()`, and `rollback()`. `update()` performs `feed -> stage -> stop/wait -> activate -> candidate start`; when the candidate fails after activation, it stops any candidate process, swaps the prior release back, and restarts it with the old release Python. It must never call a migration, clear `OPENHALO_HOME`, or keep an ambiguous switched state.

**Step 4: Run the focused test to verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_updater.py tests/test_runtime_supervisor.py tests/test_release_manager.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add openhalo/updater.py openhalo/runtime_supervisor.py tests/test_updater.py tests/test_runtime_supervisor.py
git commit -m "feat: update running runtimes with rollback"
```

### Task 4: Expose Owner Commands and Build Release Assets

**Files:**
- Modify: `openhalo/cli.py`
- Modify: `tests/test_openhalo_cli.py`
- Create: `scripts/build_release.py`
- Create: `tests/test_build_release.py`

**Step 1: Write the failing CLI and packaging tests**

Require `openhalo update --check`, `openhalo update`, and `openhalo rollback` to emit safe JSON and inject the release root/repository only through explicit test seams or environment configuration. Require `scripts/build_release.py` to produce `openhalo-<tag>.tar.gz`, `release-manifest.json`, and `SHA256SUMS`, with archive digest and commit/tag agreement.

**Step 2: Run the focused test to verify RED**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_openhalo_cli.py tests/test_build_release.py`

Expected: FAIL because update subcommands and the release builder do not exist.

**Step 3: Implement the owner surface**

Add the three subcommands to the existing JSON CLI. Default the repository to `nwomn/openhalo`; permit only an explicit `OPENHALO_GITHUB_REPOSITORY` owner/repository override for controlled tests or forks. Build archives from a caller-supplied exact commit with `git archive`, write a canonical manifest plus `SHA256SUMS`, and avoid adding secrets or GitHub tokens to either program path.

**Step 4: Run the focused test to verify GREEN**

Run: `OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_openhalo_cli.py tests/test_build_release.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add openhalo/cli.py tests/test_openhalo_cli.py scripts/build_release.py tests/test_build_release.py
git commit -m "feat: add owner-facing release update commands"
```

### Task 5: Document Publishing, Updating, and Scope Limits

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/runtime-deploy.md`
- Modify: `Project.md`

**Step 1: Replace the manual update workflow**

Document `openhalo update --check`, `openhalo update`, and `openhalo rollback`. Explain that only latest non-prerelease GitHub Releases containing all three required assets are accepted, old program releases are retained, and `OPENHALO_HOME` is not reset.

**Step 2: Add maintainer publication instructions**

Document `scripts/build_release.py --tag <tag> --commit <40-character-commit> --output <directory>` and upload the generated three files to the matching GitHub Release. The initial public Release path relies on GitHub TLS plus checksum agreement; manifest signing and key rotation remain explicitly deferred.

**Step 3: Record milestone progress accurately**

Update `Project.md` to show that the GitHub Release update/check/rollback foundation has landed but signed manifests, persistent-state migration, Windows packages, reverse-proxy automation, and full three-end product acceptance remain open.

**Step 4: Run complete verification**

Run:

```bash
git diff --check
OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests/test_release_manager.py tests/test_github_release_feed.py tests/test_updater.py tests/test_runtime_supervisor.py tests/test_openhalo_cli.py tests/test_build_release.py
OPENHALO_TEST_ISOLATION=0 bin/test -m pytest -q tests
```

Expected: all selected and full Python tests pass.

**Step 5: Commit**

```bash
git add README.md README.zh-CN.md docs/runtime-deploy.md Project.md docs/plans/2026-07-30-m22-github-release-update-implementation-plan.md
git commit -m "docs: describe GitHub Release runtime updates"
```
