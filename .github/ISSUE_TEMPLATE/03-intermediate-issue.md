---
name: "Intermediate Issue"
about: A multi-module task requiring independent research and thorough testing (~25 hours)
labels: "intermediate"
---

<!-- Everything outside "The task" is boilerplate — leave it, or trim what doesn't apply. -->

> 🧑‍💻 **Intermediate Issue** — a complex task spanning multiple modules, with real design decisions to own.
> **Time:** ~25 hours · **Prerequisites:** comfortable navigating this repo (a completed [beginner issue](https://github.com/hiero-hackers/analytics/issues?q=is%3Aissue+state%3Aopen+no%3Aassignee+label%3Abeginner) is the usual route; demonstrated CI/CD proficiency substitutes for workflow-focused issues).
> We expect more than "it works": maintainable code that fits the existing architecture.

## The task

<!-- ✍️ Author: this is the only section you write. Articulate the problem and its
     impact for someone who can already navigate src/ and tests/. State the
     expected outcome; name the modules involved and any constraints or risks you
     already know about. The contributor owns the design. -->

**Problem:**

**What done looks like:**

**Modules involved / constraints:**

## How to work on this

1. **Claim it:** comment `/assign` and wait to be assigned — unassigned PRs are closed automatically.
2. **Get a plan:** once assigned, comment `@coderabbitai plan` for a draft plan, then do your own investigation — [docs/architecture.md](https://github.com/hiero-hackers/analytics/blob/main/docs/architecture.md) maps the layers and their rules.
3. **Propose your approach as a comment before coding.** A paragraph is enough; early feedback here routinely saves days of rework.

**🤖 AI:** tools are welcome; verified work is required — you can explain every line and defend every design choice. See the [AI policy](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#ai-policy). Fully automated bot PRs are closed.

**Worth knowing about this repo before you design:**

- The layer rules in [docs/architecture.md](https://github.com/hiero-hackers/analytics/blob/main/docs/architecture.md) are strict — review will hold your solution to them.
- Tests mirror src (`tests/<pkg>/test_<module>.py`), and the output-contract test pins the pipeline output surface — if your change adds or renames outputs, update the contract deliberately.

**Before opening your PR:**

- [ ] I proposed my approach on this issue and incorporated any feedback
- [ ] The solution fits the existing architecture and layer rules, and is clear enough for others to debug without me
- [ ] Tests cover the happy path, edge cases, and error handling ([testing guide](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#testing))
- [ ] I reviewed my own diff line by line; scope is limited to this issue
- [ ] Workflow checks pass — CI green, signed commits, linked issue

**Stuck?** Comment here with what you've tried — see [getting help](https://github.com/hiero-hackers/analytics/blob/main/CONTRIBUTING.md#getting-help).
