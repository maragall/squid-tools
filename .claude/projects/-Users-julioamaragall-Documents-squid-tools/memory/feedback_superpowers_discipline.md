---
name: Always use superpowers skills
description: User requires strict adherence to superpowers skills on every prompt. Was corrected twice for skipping them.
type: feedback
---

Always check and invoke superpowers skills before every action. The user has explicitly corrected TWICE that skills were being skipped.

**Why:** The user needs a production-grade, trustworthy system. Skipping skills (especially git worktrees, TDD, code review) undermines the reliability of the output. The user came back specifically because skills were being forgotten. User said "I don't trust that you will remember."

**How to apply:**

Full workflow chain for any implementation:
1. `superpowers:brainstorming` before any creative/design work
2. `superpowers:writing-plans` to create bite-sized TDD implementation plan
3. `superpowers:using-git-worktrees` REQUIRED before any code (isolated workspace)
4. `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` for implementation
   - Each task: dispatch implementer subagent using `implementer-prompt.md` template
   - After each task: dispatch spec reviewer using `spec-reviewer-prompt.md`
   - After spec passes: dispatch code quality reviewer using `code-quality-reviewer-prompt.md`
5. `superpowers:test-driven-development` RED-GREEN-REFACTOR, no production code without failing test
6. `superpowers:verification-before-completion` run the command, read output, THEN claim
7. `superpowers:requesting-code-review` using `code-reviewer.md` template with BASE_SHA/HEAD_SHA
8. `superpowers:finishing-a-development-branch` verify tests, present 4 options, clean up

Key files in the plugin (at ~/.claude/plugins/cache/claude-plugins-official/superpowers/5.0.7/):
- skills/subagent-driven-development/implementer-prompt.md
- skills/subagent-driven-development/spec-reviewer-prompt.md
- skills/subagent-driven-development/code-quality-reviewer-prompt.md
- skills/requesting-code-review/code-reviewer.md
- skills/writing-plans/plan-document-reviewer-prompt.md
- skills/test-driven-development/testing-anti-patterns.md

Re-read the relevant skill on every prompt. Do not rely on cached understanding.
