# Project Management Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align OpenHalo project tracking with a lightweight Initiative -> Milestone -> Issue -> Pull Request workflow without changing historical milestone identifiers.

**Architecture:** `Project.md` remains the canonical project baseline and keeps historical evidence. GitHub Project becomes the execution surface with an `Initiative` field, milestone views, and real Issues only when work is ready to start. M17 is the parent Issue for the multi-edge expansion; M17.8, M17.9, and M17.10 are child milestone Issues, while their implementation tasks are nested beneath the relevant child.

**Tech Stack:** Markdown, GitHub Projects v2, GitHub CLI, GitHub GraphQL API, repository regression tests.

### Task 1: Reconcile the project baseline

**Files:**
- Modify: `Project.md`

**Steps:**

1. Add a concise current snapshot near the architecture baseline with current phase, current milestone, next route, and Goal status.
2. Reconcile M19 so its accepted state is consistent everywhere.
3. Reconcile M20.2 and M20.3 so accepted status is not described as deferred in later ownership notes.
4. Keep the old M-series identifiers and detailed acceptance evidence intact.
5. Run the repository guard and Markdown whitespace checks.

### Task 2: Migrate the GitHub Project taxonomy

**Files:**
- External: GitHub Project `OpenHalo Development`

**Steps:**

1. Add an `Initiative` single-select field with Runtime Foundation, Presence & Agent, Device Edge, Productization & Operations, Research / North Star, and Maintenance.
2. Rename the existing `Goal` field to `Historical Goal` and keep its values for traceability.
3. Remap current roadmap items to `Initiative`; remove the historical Goal field from primary views.
4. Keep Status, Architecture, Priority, Type, and Milestone as execution fields.
5. Preserve the existing table, board, and roadmap views.

### Task 3: Establish the M17 parent Issue hierarchy

**Files:**
- External: repository Issue and Project item

**Steps:**

1. Create the M17 parent Issue with the multi-edge expansion scope, boundaries, and links to the existing design baseline.
2. Create M17.8, M17.9, and M17.10 as child Issues of M17, each with its own scope and acceptance criteria.
3. Attach each child Issue to its matching repository Milestone and add the Issues to the Project.
4. Create M17.8 implementation sub-issues for design/policy, Android implementation, and verification/acceptance.
5. Link each child and task Issue to its correct parent, and remove duplicate planning drafts after the real Issue items are verified.

### Task 4: Verify Project automation boundaries

**Files:**
- Modify: `docs/dev/github-workflow.md`

**Steps:**

1. Document the actual Project views, fields, item lifecycle, and the distinction between Draft items and Issues.
2. Verify enabled and disabled built-in workflows through the GitHub API.
3. Do not claim an automation is configured unless the Project API or UI confirms it.
4. Record any GitHub API limitation and keep manual status transitions explicit.

### Task 5: Verify and publish

**Steps:**

1. Run `git diff --check`.
2. Run `bin/test -m unittest discover -s tests -v`.
3. Verify the Project contains the expected fields, views, parent Issue, sub-issues, and Milestone links.
4. Commit repository changes with a focused message.
5. Push `master` and confirm local and remote commit IDs match.
