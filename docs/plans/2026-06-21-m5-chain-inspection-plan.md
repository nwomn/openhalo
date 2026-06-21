# M5 Chain Inspection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a human-inspectable M5 chain report so a developer can directly inspect the `normalized observations -> compact snapshot / snapshot contract -> Agent proposal -> Presence decision -> recorded intervention` flow.

**Architecture:** Keep the runtime hot path unchanged. Reuse the existing in-memory local CLI session and intervention recording, then expose a read-only inspection/report surface that renders the latest chain state in one place for human acceptance work.

**Tech Stack:** Python 3, `unittest`, existing `device_edge.cli` and `personal_runtime` modules, `Project.md`

### Task 1: Lock the inspection report contract with tests

**Files:**
- Create: `tests/test_chain_inspection.py`
- Create: `personal_runtime/chain_inspection.py`

**Step 1: Write the failing test**

Add tests that require:
- a local inspected run returns a structured report with trace lines, normalized observations, compact snapshot, snapshot contract, proposal, presence decision, and recorded intervention
- the report preserves the exact snapshot contract stored in intervention history
- the human-readable rendering includes the major chain sections in order

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_chain_inspection -v`
Expected: FAIL because no chain inspection module exists yet.

**Step 3: Write minimal implementation**

Add the smallest support needed to:
- run a local CLI session
- collect the latest runtime state after one interaction
- expose a structured report and a human-readable formatter

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_chain_inspection -v`
Expected: PASS

### Task 2: Expose a CLI entrypoint for human acceptance

**Files:**
- Modify: `device_edge/cli/cli_edge.py`

**Step 1: Write the failing test**

Extend tests to require:
- a helper entrypoint can run one local inspected interaction and return the report

**Step 2: Run test to verify it fails**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_chain_inspection -v`
Expected: FAIL because the CLI helper does not expose the inspection mode.

**Step 3: Write minimal implementation**

Add the smallest support needed to:
- expose an inspection helper callable from Python
- optionally print the human-readable report from the CLI

**Step 4: Run test to verify it passes**

Run: `/root/personal-runtime-agent/.venv/bin/python -m unittest tests.test_chain_inspection -v`
Expected: PASS
