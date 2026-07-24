# Security Policy

`hiero-hackers/analytics` is a community analytics tool for the Hiero ecosystem.

## Scope

This project reads **public** GitHub data and renders a static dashboard. It stores
no user data, has no runtime backend, and holds no production secrets beyond a
read-only `GITHUB_TOKEN` used in CI. Please keep this scope in mind when assessing
severity.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately through GitHub:

1. Go to the [**Security** tab](https://github.com/hiero-hackers/analytics/security) of this repository.
2. Click **Report a vulnerability** to open a private advisory (GitHub Private
   Vulnerability Reporting).

If you cannot use GitHub advisories, raise the concern with a maintainer via the
Hiero [Discord](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/discord.md)
and ask to be directed to a private channel — do not include vulnerability details
in public messages.

## What to include

- A description of the issue and its impact
- Steps to reproduce (or a proof of concept)
- Affected version, commit, or workflow
- Any suggested remediation

## Our commitment

- We aim to **acknowledge** a report within **3 business days**.
- We will keep you informed as we assess and address the issue, and will agree a
  disclosure timeline with you before any public advisory.
- Fixes are developed privately (via GitHub Security Advisories) and disclosed
  once a fix is available.

## Supported versions

This project releases from `main`; security fixes are applied to `main`. There is
no long-term-support branch.
