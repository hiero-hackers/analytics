---
name: "Advanced Issue"
about: Architectural, multi-module, or core-logic work for proven contributors (~30+ hours)
labels: "advanced"
---

<!-- Everything outside "The task" is boilerplate — leave it, or trim what doesn't apply. -->

> 🧑‍🔬 **Advanced Issue** — the most complex work in this project: architectural, multi-module, or core-logic changes where the solution itself may need discovering.
> **Time:** ~30+ hours · **Prerequisites:** a proven track record here (≥1 completed [intermediate issue](https://github.com/hiero-hackers/analytics/issues?q=is%3Aissue+state%3Aopen+no%3Aassignee+label%3Aintermediate); demonstrated CI/CD proficiency substitutes for workflow-focused issues).
> The bar is production-ready: safe, maintainable, architecturally sound.

## The task

<!-- ✍️ Author: this is the only section you write. Articulate the problem and its
     system-wide impact. Where the solution is uncertain, say what is unknown and
     what the key risks are — mapping that uncertainty is part of the task. -->

**Problem:**

**Impact / what done looks like:**

**Known unknowns and risks:**

## How to work on this

1. **Claim it:** comment `/assign` — yes, even at this level; unassigned PRs are closed automatically.
2. **Propose your design as a comment before building.** Cover the approach, the alternatives you rejected, and the system-wide impact. For large changes, say how you'll split the work into reviewable PRs. (`@coderabbitai plan` can sketch a starting point, but the design is yours.)

**What tends to bite experienced contributors in this repo:**

- The dependency DAG in [docs/architecture.md](https://github.com/hiero-hackers/analytics/blob/main/docs/architecture.md) is deliberately strict (zero violations today) — a solution that needs a new cross-layer import needs a design conversation first, not an exception.
- The output-contract test pins every CSV, chart, and dashboard artifact the pipelines produce. Changing the output surface means changing the contract *on purpose*, and downstream dashboard consumers exist.
- Ingestion has deliberate two-layer staleness semantics (TTL cache vs. the durable incremental dataset store with reuse/refresh windows) — read the module docstrings before touching fetch paths; naive "fixes" here reintroduce bugs we've already removed.

**🤖 AI:** tools are welcome; verified work is required — see the [AI policy](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#ai-policy). Fully automated bot PRs are closed.

**Before opening your PR:**

- [ ] The PR includes a short design/impact note: approach, alternatives considered, affected modules, compatibility impact
- [ ] Correctness, safety, and performance are evaluated, not assumed — and the evaluation is visible in the note or the tests
- [ ] Testing is comprehensive, including deliberate output-contract updates where the output surface changes
- [ ] I reviewed my own diff as if it were someone else's

**Review expectations:** advanced PRs get probing questions and may take longer than a day — that's the level working as intended. **Stuck or want a design sounding board?** Comment here — see [getting help](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#getting-help).
