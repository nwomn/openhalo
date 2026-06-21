# Progress Update Hook Enforcement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Hard-enforce the required Goal 1 through Goal 4 architecture-aware progress-report format at the hook layer so project progress updates cannot complete with a malformed structure.

**Architecture:** Keep the change local to the existing project hook path. Detect progress-update prompts from the stored user prompt, validate the final assistant response structure in `Stop`, and block turns that omit any required Goal section or required architecture-aware labels.

**Tech Stack:** Python 3, `unittest`, existing `agent_guard` hook CLI tests

### Task 1: Lock progress-update validation behavior with unit tests

**Files:**
- Modify: `tests/test_agent_guard.py`
- Modify: `agent_guard/codex_hooks.py`

**Step 1: Write the failing tests**

Add tests that require:
- a progress-update prompt is detected from a Chinese progress request
- a valid Goal 1 through Goal 4 response with required labels passes validation
- a malformed progress response missing a Goal section or required label fails validation

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_agent_guard -v`
Expected: FAIL because the hook code does not yet detect progress requests or validate Goal-section structure.

**Step 3: Write minimal implementation**

Add the smallest helper functions needed to:
- detect a project progress update request
- extract `Goal 1` through `Goal 4` sections
- require `状态`, `架构位置`, `本批完成`, `对整体链路的作用`, and `还缺什么` in each Goal section

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_agent_guard -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_agent_guard.py agent_guard/codex_hooks.py
git commit -m "feat: validate project progress update structure"
```

### Task 2: Enforce the rule through the Stop hook

**Files:**
- Modify: `tests/test_hook_cli.py`
- Modify: `agent_guard/codex_hooks.py`
- Modify: `AGENTS.md`

**Step 1: Write the failing tests**

Add CLI-level tests that require:
- `Stop` blocks a progress-update response that omits the required Goal structure
- `Stop` allows a progress-update response that satisfies the required Goal structure

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_hook_cli -v`
Expected: FAIL because `Stop` does not yet apply progress-format validation.

**Step 3: Write minimal implementation**

Thread the new validation into `handle_stop` and tighten `AGENTS.md` so the documented collaboration rule matches the enforced behavior.

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_hook_cli -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_hook_cli.py agent_guard/codex_hooks.py AGENTS.md
git commit -m "feat: enforce structured project progress updates"
```

### Task 3: Verify and update the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Run broader verification**

Run the hook-related test suites after the targeted tests pass.

**Step 2: Update the project baseline**

Record that the project-level enforcement baseline now includes structured progress-update reporting if the behavior lands cleanly.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: record progress update hook enforcement"
```
