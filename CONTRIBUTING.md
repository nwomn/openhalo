# Contributing to OpenHalo

## Before You Start

OpenHalo is an alpha personal-agent runtime. Read [Project.md](Project.md) for
the current architecture, milestones, and boundaries before proposing a change.
Small, focused changes that preserve the `Device Edge -> Gateway -> Personal
Runtime` boundary are easier to review and test.

For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a
public issue.

## Local Setup

Use Python 3.11 or newer. The development extra includes the repository's
Python test tools:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Run Python regression through the contained project wrapper:

```bash
bin/test -m pytest -q tests
```

Run Android local unit tests from the Android project:

```bash
cd device_edge/android_edge
bash ./gradlew testDebugUnitTest
```

The Android instrumentation suite and real-device acceptance require local
Android SDK/device setup and are not part of the credential-free CI baseline.

## Change Expectations

- Add or update regression coverage for behavior changes.
- Keep credentials, pairing codes, provider configuration, runtime state,
  screenshots, and personal device data out of commits, issues, and test
  fixtures. Do not commit credentials, including redacted-looking real values.
- Update `Project.md` when a change affects architecture, a milestone, status,
  acceptance criteria, or the current implementation path.
- Keep documentation and examples free of real public endpoints, server
  accounts, tokens, and device identifiers.
- Keep the normal test suite offline from external providers. A test must not
  require a public Runtime, a pairing code, or a real user device.

## Pull Requests

Describe the problem, the boundary affected, the verification performed, and
any remaining manual acceptance work. Keep unrelated formatting or refactors
out of the same pull request.

By submitting a contribution, you agree to license it under the
[MIT License](LICENSE).
