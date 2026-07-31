# M22.1 Runtime Outbound Proxy Implementation Plan

> **For Codex:** Implement this plan task-by-task with test-first verification.

**Goal:** Let an installed owner configure, inspect, test, replace, and clear the
Personal Runtime's HTTP/HTTPS outbound proxy without changing Edge transport.

**Architecture:** Persist the redacted-safe proxy contract inside the private
`OPENHALO_HOME` configuration. The Runtime Supervisor constructs a sanitized
child environment for Provider and future MCP HTTP traffic, with loopback
`NO_PROXY` protection for the managed Host Edge. Changes use provider-path
preflight, controlled restart, and automatic configuration rollback.

**Tech Stack:** Python 3.11+, standard-library `urllib`, JSON owner config,
pytest, existing Runtime Supervisor.

## Public Commands

- `openhalo proxy set` reads an HTTP/HTTPS URL through a hidden prompt.
- `openhalo proxy show`, `test`, and `clear` return safe JSON and stable exit codes.
- Credentials are stored only in owner-readable `config.json` and are redacted in all output.

## Verification

- Unit tests cover URL validation, direct/proxy probing, environment isolation, CLI behavior, and restart rollback.
- The full Python suite is required before M22.1 acceptance.
- Real installed acceptance must verify both enabled-proxy and cleared/direct Provider egress.
