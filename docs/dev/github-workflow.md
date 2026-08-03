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

## Current roadmap seed

The Project contains the active execution route from `Project.md` as planning
items for `M17.8`, `M17.9`, `M17.10`, `M18`, `M19`, `M20.1`, `M21`, `M22`, and
`M23`. The corresponding repository Milestones are also created so real Issues
can be attached when each slice is opened for implementation.
