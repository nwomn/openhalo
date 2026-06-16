# AGENTS.md

## Project Context

This project uses [Project.md](/root/personal-runtime-agent/Project.md) as the primary source of truth for project background, goals, milestones, current status, and completed progress.

Before doing any substantive work in this project, you must read `Project.md` first.

## Mandatory Session Start Behavior

At the beginning of every new conversation or work session in this project:

1. Read `Project.md`
2. Understand the current project background, goals, sub-goals, completed items, and project progress
3. Use that context to guide the current task

You must not start implementation, planning, or analysis with stale project context.

This repository now enforces that behavior with project-level Codex hooks in `.codex/hooks.json`.
The `SessionStart` hook records the current `Project.md` baseline before work may continue.

## Mandatory Progress Check On Every Interaction

On every meaningful interaction, use the current conversation context to briefly assess whether `Project.md` should be updated.

This check does not require rewriting the file every time, but it does require consciously evaluating whether any of the following changed:

- project phase
- architecture decisions
- milestone definitions
- sub-goal status
- completed work
- acceptance status

If any of those changed in a meaningful way, update `Project.md`.

This repository now enforces a per-turn audit at assistant stop time.
The default path is an internal audit, so normal responses do not need to expose the audit result to the user.
When a turn changes `Project.md`, or when the hook detects an inconsistency, the turn must include a `Project.md Check` block in this exact shape:

```md
Project.md Check:
- meaningful: yes|no
- phase_changed: yes|no
- architecture_changed: yes|no
- milestone_changed: yes|no
- subgoal_status_changed: yes|no
- completed_work_changed: yes|no
- acceptance_status_changed: yes|no
- project_updated: yes|no
- summary: One concise sentence.
```

If a meaningful interaction changes project phase, architecture decisions, milestone definitions, sub-goal status, completed work, or acceptance status, the response must declare `project_updated: yes` and `Project.md` must actually change in the same turn.
If `Project.md` changed but the turn does not include a consistent `Project.md Check` block, the project-level `Stop` hook blocks the turn from completing.

## Project Documentation Rules

When updating `Project.md`:

- Preserve it as the single project baseline document
- Keep status fields accurate
- Ensure every tracked sub-goal has acceptance criteria
- Ensure completed items are clearly marked
- Keep the current progress summary aligned with the latest discussion

## Architecture Guidance

The current project direction is:

- frontend: `Device Edge`
- backend: `Personal Runtime`

The backend currently includes, at minimum, these conceptual layers:

- `Gateway`
- `State / Context / Task`
- `Presence Router`
- `Agent Executor`
- `Action Layer`

Treat this as the working architecture direction unless `Project.md` says otherwise.

## Collaboration Guidance

When contributing to this project:

- Prefer refining and preserving project clarity over rushing into unframed implementation
- Keep new decisions reflected in `Project.md`
- Treat `Project.md` as a living document, not a one-time kickoff note

## Hook Enforcement

Project-level Codex hook configuration lives in `.codex/hooks.json`.
Shared enforcement logic lives in `agent_guard/codex_hooks.py`.

The active hook chain is:

1. `SessionStart`: records the `Project.md` baseline for the session
2. `UserPromptSubmit`: refuses a new turn if the previous turn was not fully audited
3. `PreToolUse`: blocks tool execution if the session baseline is missing
4. `PostToolUse`: marks that meaningful work happened in the current turn
5. `Stop`: performs the internal turn audit and only requires a visible `Project.md Check` block when `Project.md` changed or an inconsistency must be resolved
