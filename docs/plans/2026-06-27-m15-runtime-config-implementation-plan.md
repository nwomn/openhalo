# M15 Runtime-Native Credential/Runtime-Config Implementation Plan

## Goal

M15 establishes a small runtime-owned credential baseline so OpenHalo can authenticate model-provider access through one inspectable runtime config instead of relying on ad hoc shell environment variables or a separate auth store.

## First Slice Scope

- Add a local runtime config contract at `config/runtime-config.toml`
- Keep provider route, model/profile selection, and provider API key together in that one local runtime config
- Do not use environment-variable fallback for provider credentials in this baseline
- Expose auth resolution metadata in provider probes without exposing secret values
- Preserve the existing model-provider request, retry, fallback, and diagnostic behavior

## Runtime Config Shape

```toml
[llm.providers.openai_main]
adapter_type = "openai_compatible"
base_url = "https://api-dmit.cubence.com/v1"
wire_api = "responses"
api_key = "..."
```

The initial config is deliberately local and file-based. Encryption, login UI, provider-specific token refresh, and OS keychain integration are later hardening work, not required for this first baseline.

## Acceptance Criteria

- Runtime provider execution authenticates through the provider `api_key` in `config/runtime-config.toml`
- `config/runtime-config.toml` is ignored by git, while `config/runtime-config.example.toml` documents the expected shape
- Provider probes report `auth_source`, `auth_reference`, and `auth_present` while never returning the secret
- Missing credentials are classified as auth failures with a provider-scoped missing-credential message
- Automated tests cover direct config credentials, missing credentials, request execution, and probe metadata

## Current Manual Acceptance Notes

- The current relay baseline is `https://api-dmit.cubence.com/v1` with `gpt-5.5`
- `gpt-5.4` can pass a narrow provider probe but is not accepted for the terminal live path because it can return a Codex-agent envelope with empty output after compact snapshot fields are present
- Host-plus-terminal acceptance should include one normal terminal reply, one `runtime.status` action routed through host edge, and one follow-up context question after that status result
- The gateway now runs WebSocket frame handling in serialized background-thread execution so slow provider calls do not block WebSocket ping/pong keepalive handling
- Occasional provider/relay errors may still surface explicitly to the user; those are acceptable as visible provider diagnostics when the terminal edge remains connected and `bin/verify-model-provider` still reports a healthy configured provider
- Repeated provider shape, timeout, or HTTP failures should be captured as provider stability evidence rather than treated as runtime-config credential failure unless probe metadata reports missing auth or unauthorized status
