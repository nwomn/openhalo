# GitHub Development Workflow

This is a small repository-level example of how OpenHalo work moves from a
project goal to an accepted change. GitHub tracks execution; `Project.md`
remains the project baseline for architecture, milestones, and overall status.

## The chain

```text
Project.md / GitHub Project
        -> Issue
        -> branch
        -> code + tests + docs
        -> Pull Request
        -> review + CI + human acceptance
        -> merge / release
```

## What each surface owns

| Surface | Owns |
| --- | --- |
| `Project.md` | Project background, architecture direction, goals, and milestone baseline |
| GitHub Project | Task status, priority, goal, architecture location, and milestone view |
| Issue | One piece of work, its scope, and acceptance criteria |
| `docs/` | Design, API, operations, and developer knowledge |
| Pull Request | The concrete code/documentation change and its evidence |
| Release | A versioned set of accepted changes and release notes |

## Example task

Suppose the Runtime needs a new health snapshot field.

1. Create an Engineering task from the Issue template.
2. Select the relevant Goal and `State / Context / Task` architecture location.
3. Add the current milestone and write observable acceptance criteria.
4. Link the relevant design or API document.
5. Create a branch and implement the reducer, tests, and documentation together.
6. Open a PR. The PR template records architecture impact, documentation impact,
   automated verification, and manual acceptance evidence.
7. Move the Project item through `In Progress`, `Review`, `Acceptance`, and
   `Done`.
8. Update `Project.md` only if the completed work changes project-level
   architecture, phase, milestone status, or the recorded acceptance baseline.

## When design comes first

For a local bug or a narrow implementation task, use:

```text
Issue -> implementation PR
```

For an uncertain architectural change, use:

```text
design Issue / RFC -> design document -> implementation Issue -> implementation PR
```

Use GitHub Discussions for early alternatives when the decision is not ready to
become a committed design. Once accepted, record the decision in `docs/` and
link it from the implementation Issue and PR.

## Lightweight Project fields

The first GitHub Project can use these fields without changing repository code:

- `Status`: Backlog, Ready, In Progress, Review, Acceptance, Done
- `Goal`: Goal 1, Goal 2, Goal 3, Goal 4, Cross-cutting
- `Architecture`: Device Edge, Gateway, State/Context, Agent Runtime, Action Layer
- `Milestone`: the active M-series milestone
- `Priority`: P0, P1, P2
- `Type`: Feature, Bug, Design, Research, Maintenance

The templates in `.github/` make the information available at task and PR
creation time; the Project view then makes it easy to scan and filter.
