# Contributing

This is the canonical guide for contributing to **hiero-hackers/analytics**. Issue
templates link here instead of repeating this content, so if anything on this page
disagrees with an old issue body, this page wins.

The project is a Python analytics pipeline + dashboard for Hiero repository health.
It is **not** an SDK: there are no protobufs, no testnet accounts, and setup takes
minutes.

- [Setup](#setup)
- [Workflow](#workflow)
- [Skill levels](#skill-levels)
- [AI policy](#ai-policy)
- [Code quality](#code-quality)
- [Testing](#testing)
- [After your PR](#after-your-pr)
- [Getting help](#getting-help)

## Setup

1. **Fork and clone** the repository, then add the upstream remote.
2. **Install [uv](https://docs.astral.sh/uv/)** (Python 3.11+).
3. Install dependencies and run the test suite — no credentials needed:

   ```bash
   uv sync
   uv run pytest
   ```

4. *(Only for issues that fetch live GitHub data)* create a `.env` file in the repo
   root containing `GITHUB_TOKEN=<a classic token with public repo read access>`.
   Most issues, and the whole test suite, work without one.
5. **Set up commit signing** (required): [GPG signing guide](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/signing.md).
6. **Install the pre-commit hooks** (recommended): `uv run pre-commit install`.
   They run automatically on each commit — see [Code quality](#code-quality).

Useful commands:

```bash
uv run pytest                        # full test suite
uv run ruff check src tests         # lint
uv run ruff format src tests        # format
uv run pre-commit run --all-files   # run all hooks now
uv run hiero-analytics --help       # list the analytics pipelines
```

The codebase map lives in [docs/architecture.md](docs/architecture.md).

## Workflow

1. **Claim the issue** by commenting `/assign` and wait to be assigned.
   PRs from unassigned contributors are closed automatically.
2. **Get a rough plan**: once assigned, comment `@coderabbitai plan` on the issue to
   generate a draft implementation plan. Treat it as a starting point — it can be
   wrong, and verifying it against the actual code is part of the work.
3. **Branch from an up-to-date `main`** in your fork.
4. **Commit** using Conventional Commits, signed and signed-off:
   `git commit -S -s -m "fix: describe the change"`.
5. **Open a PR** that briefly describes the change and links the issue with
   `Fixes #<number>` (PRs without a linked issue are closed automatically).

Generic Git help: [rebasing](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/rebasing.md) ·
[merge conflicts](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/merge_conflicts.md) ·
[full workflow walkthrough](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/contributor-workflow.md).

## Skill levels

Issues are labelled by the skill they exercise. Pick the level where you'll learn
something without drowning; it's normal (and encouraged) to move up one level at a
time.

| Level | Prerequisites | Typical time | Testing bar | What we look for |
|---|---|---|---|---|
| **Good First Issue** | none — beginner programming is enough | ~4 h incl. setup | run it and check the happy path | you followed the workflow |
| **Beginner** | ~1 completed Good First Issue | ~8 h | basic unit tests for what you changed | you researched the file before coding |
| **Intermediate** | comfortable navigating this repo | ~25 h | happy path + edge cases + error handling | architectural fit; comment your approach before coding |
| **Advanced** | proven track record here | ~30 h+ | comprehensive | a short design/impact note in the PR |

Find open issues at each level:
[Good First Issues](https://github.com/hiero-hackers/analytics/issues?q=is%3Aissue+state%3Aopen+no%3Aassignee+label%3A%22Good+First+Issue%22) ·
[Beginner](https://github.com/hiero-hackers/analytics/issues?q=is%3Aissue+state%3Aopen+no%3Aassignee+label%3Abeginner) ·
[Intermediate](https://github.com/hiero-hackers/analytics/issues?q=is%3Aissue+state%3Aopen+no%3Aassignee+label%3Aintermediate) ·
[Advanced](https://github.com/hiero-hackers/analytics/issues?q=is%3Aissue+state%3Aopen+no%3Aassignee+label%3Aadvanced)

## AI policy

AI tools are welcome here — for research, drafting, and debugging. We care about
what you verified, not what typed the characters. Whatever tools you use:

- **You ran it.** You executed the code and the tests locally and read the output.
- **You understand it.** You can explain every line of your diff when asked —
  reviewers do ask, and "the AI wrote that part" is not an answer.
- **You did the research.** You read the relevant source files yourself; the issue's
  file pointers and any CodeRabbit plan are starting points, not substitutes.
- **Your tests mean something.** Tests must verify behaviour, not restate the
  implementation. Writing them yourself is the best way to be sure.

Fully automated PRs — bot-authored submissions with no human who did the above —
are closed regardless of quality. If a review walkthrough shows the work wasn't
verified, we'll suggest a lower-level issue rather than merge it.

## Code quality

Formatting, linting, and type-checking are enforced in CI (the
[lint workflow](.github/workflows/lint.yml)). Run them locally before pushing:

```bash
uv run ruff check src tests     # lint  (add --fix to autofix)
uv run ruff format src tests    # format
uv run pyright                  # type-check (report-only in CI for now)
```

The [pre-commit hooks](.pre-commit-config.yaml) run a subset automatically on
every commit — [gitleaks](https://github.com/gitleaks/gitleaks) secret scanning,
end-of-file / trailing-whitespace fixers, and `ruff` + `ruff-format`. Set them up
once, then optionally run them across the whole tree:

```bash
uv run pre-commit install        # one-time: enable the git hook
uv run pre-commit run --all-files
```

Ruff's rules and line length live in [pyproject.toml](pyproject.toml) under
`[tool.ruff]`; the same config backs the CLI, the pre-commit hook, and CI, so all
three agree.

The `web/` dashboard has its own lint/format gate, enforced by the same CI
workflow's `web-lint` job:

```bash
npm --prefix web run lint            # oxlint (ESLint-compatible, TS/React rules)
npm --prefix web run format:check    # Prettier
npm --prefix web run format          # Prettier, autofix
```

## Testing

- Tests mirror the source layout: code in `src/hiero_analytics/<pkg>/<module>.py`
  is tested in `tests/<pkg>/test_<module>.py`.
- Run everything with `uv run pytest`; a single file with
  `uv run pytest tests/<pkg>/test_<module>.py`.
- CI enforces lint (ruff), formatting, and a coverage floor — a PR that lowers
  coverage on touched code will be asked to add tests.
- For **GitHub Actions / workflow changes** (`.github/`), test by pushing to your
  fork's `main` and linking the successful run in your PR.

## After your PR

1. **Automated checks** run first; all must pass. Open a failing check for
   details and ask if a failure doesn't make sense to you.
2. **Workflow review** — a team member confirms the PR follows the workflow
   (assigned, linked issue, signed commits, in scope).
3. **Implementation review** — you may be asked questions or for changes.
   Approved PRs are usually merged within a day.
4. **Merge conflicts** happen as `main` moves; resolve with the
   [merge conflicts guide](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/merge_conflicts.md).

## Getting help

- **Comment on the issue** describing what you tried — a maintainer will respond.
- [Discord](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/discord.md)
- [Community calls](https://zoom-lfx.platform.linuxfoundation.org/meetings/hiero?view=week)

---

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE) and that you follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
