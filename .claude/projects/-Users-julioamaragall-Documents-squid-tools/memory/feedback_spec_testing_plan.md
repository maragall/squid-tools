---
name: Spec testing plan is functional, end-of-product
description: Testing plan in spec is functional validation of final integrated product, NOT per-cycle TDD. TDD already handled by superpowers during implementation.
type: feedback
---

The testing plan belongs at the END of the full spec document. It describes user-facing functional tests for the complete integrated product, not per-cycle unit tests.

**Why:** During cycle implementation, superpowers already enforces TDD (write failing test, verify fail, implement, verify pass). The per-cycle tests live in each plan. The spec-level testing plan is different: it's how we validate the WHOLE product works end-to-end when all cycles are done.

**How to apply:**
- Each cycle plan has its own TDD tests (handled by superpowers)
- The overall product spec has ONE testing plan at the end
- That testing plan is functional: "Open an acquisition, drag-select FOVs, click Run Flatfield, verify tiles update" etc.
- It's the final product acceptance test, written as user workflows
- Write it when we finish all cycles, not during each one
