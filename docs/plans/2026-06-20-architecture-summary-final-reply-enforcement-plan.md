# Architecture Summary Final Reply Enforcement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Hard-enforce an architecture summary block in final replies for turns that perform edits, so implementation turns cannot complete without stating the architecture location and downstream effect of the work.

**Architecture:** Keep the rule narrow and robust. Track whether the current turn used `apply_patch`, then validate the final assistant response in `Stop` for a required `架构实现小结` block with explicit labels for `架构位置`, `本步完成`, and `影响链路`.

**Tech Stack:** Python 3, `unittest`, existing `agent_guard` hook CLI tests

### Task 1: Lock architecture-summary validation behavior with unit tests

**Files:**
- Modify: `tests/test_agent_guard.py`
- Modify: `agent_guard/codex_hooks.py`

**Step 1: Write the failing tests**

Add tests that require:
- a valid architecture summary block passes validation
- a malformed architecture summary block missing a required label fails validation

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_agent_guard -v`
Expected: FAIL because the hook code does not yet validate the architecture summary block.

**Step 3: Write minimal implementation**

Add the smallest helper functions needed to:
- validate `架构实现小结`
- require `架构位置`, `本步完成`, and `影响链路`

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_agent_guard -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_agent_guard.py agent_guard/codex_hooks.py
git commit -m "feat: validate architecture summary final replies"
```

### Task 2: Enforce the rule through edit-turn tracking and Stop

**Files:**
- Modify: `tests/test_hook_cli.py`
- Modify: `agent_guard/codex_hooks.py`
- Modify: `AGENTS.md`

**Step 1: Write the failing tests**

Add CLI-level tests that require:
- `PostToolUse` marks a turn as edited when the tool is `functions.apply_patch`
- `Stop` blocks an edited turn whose final reply omits the required architecture summary
- `Stop` allows an edited turn whose final reply includes the required architecture summary

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_hook_cli -v`
Expected: FAIL because the session state does not yet track edit turns and `Stop` does not validate the architecture summary block.

**Step 3: Write minimal implementation**

Track edit activity in session state, then enforce the architecture summary block in `handle_stop` only for edited turns.

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_hook_cli -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_hook_cli.py agent_guard/codex_hooks.py AGENTS.md
git commit -m "feat: enforce architecture summary final replies"
```

### Task 3: Verify and update the project baseline

**Files:**
- Modify: `Project.md`

**Step 1: Run broader verification**

Run the hook-related test suites after the targeted tests pass.

**Step 2: Update the project baseline**

Record that project-level enforcement now requires architecture summary blocks in final replies for edited turns if the behavior lands cleanly.

**Step 3: Commit**

```bash
git add Project.md
git commit -m "docs: record architecture summary reply enforcement"
```
