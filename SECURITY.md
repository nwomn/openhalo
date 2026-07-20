# Security Policy

## Supported Versions

OpenHalo is pre-1.0 software. Security fixes are considered for the latest
`master` revision only. Preview APKs and old commits are not supported release
channels.

## Reporting a Vulnerability

Use GitHub's private **Report a vulnerability** form in this repository's
Security tab:

<https://github.com/nwomn/openhalo/security/advisories/new>

Do not open a public issue, discussion, or pull request for a suspected
vulnerability. Do not include pairing codes, device credentials, provider API
keys, runtime-state files, screen text, screenshots, or other user data in a
report.

Repository owners must enable GitHub private vulnerability reporting in
**Settings -> Code security and analysis** before making the repository public.
If the private-reporting form is unavailable, open a public issue only asking
for a confidential reporting channel; include no vulnerability details.

## What To Include

Provide a minimal reproduction, affected revision, impact, and a safe proof of
concept. Redact secrets and personal data. Acknowledgement and remediation
timing depend on severity, reproducibility, and the current pre-release scope.

## Scope Notes

The project handles device-to-runtime credentials and optional mobile screen
context. Reports involving authentication, authorization, credential storage,
message routing, sensitive capture, logs, backups, or unintended network
exposure are in scope. Do not test against systems or devices you do not own or
have explicit permission to assess.
