# GitHub Project Workflow

The actual OpenHalo execution board is the private GitHub Project:

https://github.com/users/nwomn/projects/1

The board is linked to `nwomn/openhalo`. It tracks executable work while
`Project.md` remains the baseline for architecture, goals, milestone definitions,
and overall project status.

## Project views

- `All Work`: table view for scanning and filtering every item
- `Execution Board`: board view for status-based execution
- `Milestone Roadmap`: roadmap view for time and milestone-oriented planning

## Project fields

- `Status`: Backlog, Ready, In Progress, Review, Acceptance, Done
- `Goal`: Goal 1 through Goal 6, or Cross-cutting
- `Architecture`: Device Edge, Gateway, State / Context / Task, Agent Runtime /
  Presence Router, Action Layer, Product / Release Tooling, Documentation
- `Milestone`: the repository milestone linked to an Issue
- `Priority`: P0, P1, P2
- `Type`: Feature, Bug, Design, Research, Maintenance

## Work lifecycle

```text
Project roadmap
        -> Issue with scope and acceptance criteria
        -> branch
        -> code + tests + docs
        -> Pull Request
        -> review + CI + human acceptance
        -> merge / release
```

The assistant creates the Issue and Pull Request when implementation starts.
The Project item then carries the Goal, architecture location, priority, type,
milestone, and current status.

For an uncertain architectural change, the order is:

```text
design document / decision -> implementation Issue -> implementation PR
```

Use the repository `docs/` directory for durable design, API, operations, and
developer knowledge. Use GitHub Discussions only for alternatives that have not
yet become project decisions.

## Automation boundary

The Project currently enables `Auto-add sub-issues to project`, which keeps
the M17 hierarchy visible when child tasks are created. Other built-in rules,
such as pull-request-linked, pull-request-merged, and issue-closed status
changes, remain manual until they are explicitly enabled in the Project
`Workflows` UI. The GitHub CLI/API does not expose their configuration as a
repository file, so the repository must not claim those transitions are
automatic unless the Project UI confirms them.

## Current roadmap seed

The Project contains an `M17` parent Issue with child Issues for `M17.8`,
`M17.9`, and `M17.10`. `M19` is a closed historical Milestone. Later route
entries `M18`, `M20.1`, `M21`, `M22`, and `M23` remain planning items
until their implementation is ready. Repository Milestones mirror these
delivery boundaries; implementation tasks are sub-issues under the active child
milestone rather than new milestone numbers.
