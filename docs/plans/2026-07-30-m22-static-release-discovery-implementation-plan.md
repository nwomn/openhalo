# M22 Static Release Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `openhalo update` discover the latest verified Runtime Release without calling the rate-limited GitHub REST API.

**Architecture:** `GitHubReleaseFeed` will obtain `release-manifest.json` from GitHub's canonical `releases/latest/download` asset route. The manifest supplies the immutable tag and archive filename; the feed constructs canonical tag-scoped HTTPS URLs for `SHA256SUMS` and the archive, then retains the existing manifest-to-checksum agreement check before staging. The Runtime update lifecycle, immutable selection, health gate, rollback, and `OPENHALO_HOME` behavior do not change.

**Tech Stack:** Python 3.11+, `urllib`, pytest, GitHub Releases.

### Task 1: Cover static asset discovery

**Files:**
- Modify: `tests/test_github_release_feed.py`

**Step 1: Write failing tests**

Create an injected downloader fixture that provides a manifest only at:

```python
https://github.com/nwomn/openhalo/releases/latest/download/release-manifest.json
```

Require `GitHubReleaseFeed.latest()` to resolve the checksum and archive through:

```python
https://github.com/nwomn/openhalo/releases/download/v0.22.0/SHA256SUMS
https://github.com/nwomn/openhalo/releases/download/v0.22.0/openhalo-v0.22.0.tar.gz
```

Require the existing checksum mismatch and ambiguous checksum rejection behavior to remain.

**Step 2: Run the focused test to verify RED**

Run: `pytest tests/test_github_release_feed.py -q`

Expected: failure because the current feed first requests GitHub's REST API route.

### Task 2: Resolve a release from static assets

**Files:**
- Modify: `openhalo/release_manager.py`
- Test: `tests/test_github_release_feed.py`

**Step 1: Implement the smallest safe resolver**

Add helpers that construct canonical HTTPS GitHub Release asset URLs from the validated `owner/name` repository, the manifest tag, and a filename. `latest()` must fetch only the latest manifest static path, validate it, fetch the tag-scoped `SHA256SUMS`, require one matching digest, and return the tag-scoped archive URL.

Do not accept an archive URL supplied by the manifest, call the GitHub REST API, weaken redirect HTTPS validation, or alter staging and rollback behavior.

**Step 2: Run the focused tests**

Run: `pytest tests/test_github_release_feed.py -q`

Expected: all pass.

### Task 3: Document the operational contract

**Files:**
- Modify: `docs/runtime-deploy.md`
- Modify: `Project.md`

**Step 1: Record static discovery**

Document that update discovery uses GitHub's latest Release asset route and therefore does not consume the GitHub REST API anonymous quota. Keep manifest signatures and persistent-state migrations explicitly deferred.

**Step 2: Record the observed proxy failure and bootstrap limitation**

State that v0.1.0's REST-based updater can be recovered by temporarily bypassing the proxy. State that later releases use static discovery so the normal command is independent of that REST quota.

### Task 4: Verify and publish

**Files:**
- Create: `dist/release-v0.1.2/` (ignored release assets)

**Step 1: Run tests**

Run: `pytest tests/test_github_release_feed.py tests/test_openhalo_cli.py tests/test_build_release.py -q`

Expected: all pass.

**Step 2: Check public static discovery**

Run: `curl -fsSL https://github.com/nwomn/openhalo/releases/latest/download/release-manifest.json`

Expected: a valid JSON manifest for the latest stable Release.

**Step 3: Publish the immutable release**

Commit the implementation, tag it, build the three immutable assets with `scripts/build_release.py`, publish a stable GitHub Release, download the assets back, and verify their SHA-256 agreement.

**Step 4: Verify owner path without mutation**

On an installed Runtime that includes this release, run `openhalo update --check` with the normal proxy environment. The owner performs the mutating `openhalo update` command.
