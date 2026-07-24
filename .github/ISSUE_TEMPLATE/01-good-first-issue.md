---
name: "Good First Issue"
about: A small, guided change for brand-new contributors (~4 hours)
labels: "Good First Issue"
---

<!-- Everything outside "The task" is boilerplate — leave it, or trim what doesn't apply. -->

> 🐥 **Good First Issue** — a small, well-contained change designed for first-time contributors.
> **Time:** ~4 hours including setup · **Prerequisites:** none — beginner programming is enough. No Hiero, Hedera, or data-science background needed.
> Setup takes minutes: see the [contributor guide](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#setup).

## The task

<!-- ✍️ Author: this is the only section you write. Say what's wrong or missing and
     why it matters, what "done" looks like, and point at 1–3 files to start from.
     Write for someone who has never seen this codebase. -->

**Problem:**

**What done looks like:**

**Where to start:** `src/hiero_analytics/…`

## How to work on this

1. **Claim it:** comment `/assign` and wait to be assigned — unassigned PRs are closed automatically.
2. **Get a plan:** once assigned, comment `@coderabbitai plan` for a draft implementation plan. It's a starting point, not a spec — checking it against the real code is part of the task.
3. **Set up and solve it** with the [setup](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#setup) and [workflow](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#workflow) guides. Ask questions early, on this issue or [Discord](https://github.com/hiero-ledger/sdk-collaboration-hub/tree/main/guides/issue-progression/for-developers/discord.md).

**🤖 AI:** tools are welcome; verified work is required. You must have run the code and tests yourself, be able to explain every line, and have read the files above with your own eyes — see the [AI policy](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#ai-policy). Fully automated bot PRs are closed.

**Before opening your PR:**

- [ ] I ran the change locally and checked it does what the issue asks
- [ ] `uv run pytest` and `uv run ruff check src tests` pass
- [ ] My changes stay within the scope of this issue
- [ ] My commits are signed: `git commit -S -s -m "fix: description"`
- [ ] The PR description links this issue with `Fixes #<number>`

**Stuck?** Comment here and tag `@good_first_issue_support_team`, or see [getting help](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#getting-help). What happens after you submit: [after your PR](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#after-your-pr).
