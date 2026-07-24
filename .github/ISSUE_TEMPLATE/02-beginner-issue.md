---
name: "Beginner Issue"
about: A well-scoped task for contributors ready to research the codebase (~8 hours)
labels: "beginner"
---

<!-- Everything outside "The task" is boilerplate — leave it, or trim what doesn't apply. -->

> 🧑‍🎓 **Beginner Issue** — a well-scoped task for contributors ready to learn this codebase and own a small implementation.
> **Time:** ~8 hours · **Prerequisites:** ~1 completed [Good First Issue](https://github.com/hiero-hackers/analytics/issues?q=is%3Aissue+state%3Aopen+no%3Aassignee+label%3A%22Good+First+Issue%22) recommended; comfortable forking, branching, and opening a PR without a tutorial.
> If that feels unfamiliar, a Good First Issue is the more rewarding path right now — you can always come back.

## The task

<!-- ✍️ Author: this is the only section you write. State the problem and the
     expected outcome, and point at the files and one or two similar patterns in
     the codebase worth studying first. Leave implementation decisions to the
     contributor. -->

**Problem:**

**What done looks like:**

**Where to look first:** `src/hiero_analytics/…` — and study a similar existing pattern before coding.

## How to work on this

1. **Claim it:** comment `/assign` and wait to be assigned — unassigned PRs are closed automatically.
2. **Get a plan:** once assigned, comment `@coderabbitai plan` for a draft implementation plan. Verify it against the code — spotting where it's wrong is the research.
3. **Research before coding:** read the files above and their tests; most of the value of this level is building an accurate picture before changing anything. The [workflow guide](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#workflow) has the mechanics.

**🤖 AI:** tools are welcome; verified work is required. You ran it, you can explain every line, your tests verify behaviour — see the [AI policy](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#ai-policy). Fully automated bot PRs are closed.

**Before opening your PR:**

- [ ] I spent real time reading the relevant code before writing any
- [ ] The implementation works and follows the surrounding patterns
- [ ] I added basic unit tests for what I changed, in the mirrored path `tests/<pkg>/test_<module>.py` ([testing guide](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#testing))
- [ ] `uv run pytest` and `uv run ruff check src tests` pass; scope is limited to this issue
- [ ] The basics from your first issue still apply — signed commits, linked issue, clean history ([quick refs](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#workflow))

**Stuck?** Comment here with what you've tried — see [getting help](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#getting-help).
