# Project Baseline Slimming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce `Project.md` from a mixed current-state/history ledger into a compact, attention-friendly project baseline while preserving detailed evidence in linked documents.

**Architecture:** `Project.md` remains the single canonical project baseline for current phase, goals, architecture invariants, milestone route, and acceptance summaries. Detailed completed-progress evidence, low-frequency research questions, and operational investigation records move into explicit archive documents that are linked from the baseline and loaded only when relevant.

**Tech Stack:** Markdown, repository links, shell-based structural checks, Git diff.

### Task 1: Archive low-frequency project detail

**Files:**
- Create: `docs/history/project-completed-progress.md`
- Create: `docs/history/m19-operational-status.md`
- Create: `docs/research/project-open-questions.md`

**Steps:**

1. Preserve the existing completed-progress, M19 operational, and open-question sections verbatim in their new documents, adding a short note that `Project.md` remains the canonical summary.
2. Add links from the compact baseline to each archive.
3. Verify each archive has the expected top-level heading and non-empty content.

### Task 2: Rebuild the current project baseline

**Files:**
- Modify: `Project.md`

**Steps:**

1. Move `Current Snapshot` to the top immediately after the title.
2. Keep the project identity, naming, concise architecture invariants, edge representation, goal status/acceptance summaries, current route, and document-maintenance rules.
3. Replace long historical evidence with a completed-baseline table and archive links.
4. Keep the M17 parent/child hierarchy and current M17.8 route explicit.
5. Add a progressive-disclosure note telling future sessions which linked detail document to load for each kind of task.

### Task 3: Verify the refactor

**Files:**
- Verify: `Project.md`
- Verify: `docs/history/project-completed-progress.md`
- Verify: `docs/history/m19-operational-status.md`
- Verify: `docs/research/project-open-questions.md`

**Steps:**

1. Run `git diff --check`.
2. Check that all links and required current-route markers are present with `rg`.
3. Check that `Project.md` is materially smaller and that the archive line counts account for removed detail.
4. Run the repository test suite because the project hook and documentation guard tests validate the project baseline contract.

### Task 4: Commit and push

**Steps:**

1. Stage only the baseline, archive, and plan documents.
2. Commit with a documentation-focused message.
3. Push `master` and verify `HEAD` matches `origin/master` with a clean worktree.
