# Reviewer Prompt Templates

Use these templates when `reviewer` or `reviewer-lite` tends to stall because the scope is too broad.

## When To Use Which

- Use `reviewer-lite` for a fast first pass over a bounded file set, diff slice, or one risk theme.
- Use `reviewer` for deeper review after the first pass finds real risk, or when the change is small enough to review exhaustively.
- Treat a bounded "no high-signal findings" result as a valid outcome, not as a failed review.
- Do not ask either reviewer to inspect "all potential risks" across the whole branch as a first pass.

## Template 1: Single File Review

Use this when one file is the likely risk owner and you want fast findings.

```text
Review only this file for correctness, regression, security, and missing-test risks:

- file: <absolute-or-relative-path>
- change summary: <one sentence>
- scope limit: do not expand outside this file unless a directly called dependency is required to justify a finding

Return only:
1. top findings by severity
2. file/line evidence
3. highest-risk unchecked area
4. if no material issue is found, explicitly say "no high-signal findings in this bounded scope"
```

## Template 2: Small Module Review

Use this when the change spans 2-6 files in one module.

```text
Do a bounded first-pass review of this module change:

- files:
  - <path-1>
  - <path-2>
  - <path-3>
- module purpose: <one sentence>
- focus: correctness, regression, security, and missing tests
- scope limit: stay within these files unless one direct dependency is necessary to confirm a finding

If the module is too broad for one pass, return the top material findings plus the highest-risk unchecked area instead of waiting for exhaustive coverage.
If no material issue is found, explicitly state the bounded scope reviewed and the main unchecked risk area.
```

## Template 3: Risk-Specific Review

Use this when broad review is slow but one risk class matters most.

```text
Review this change only for <risk-theme>.

- files:
  - <path-1>
  - <path-2>
- risk theme: auth | input validation | data loss | contract breakage | missing tests | rollout risk
- ignore: style, readability-only comments, and unrelated architecture suggestions

Return only findings relevant to the selected risk theme, with file/line evidence when available.
If no material issue is found for that theme, explicitly say so and name the highest-risk unchecked theme.
```

## Template 4: Reviewer + Reviewer-Lite Pairing

Use this when you still want parallel review, but need fast signal first.

```text
Spawn `reviewer-lite` on the bounded changed files for a fast first pass.
Spawn `reviewer` only on the highest-risk subset or risk theme identified by the first pass.
Do not ask either reviewer to cover the whole branch unless the changed scope is already small and bounded.
```

## Template 5: Drop-In Strict Reviewer Prompt

Use this as the default bounded review prompt when previous reviewer tasks were too vague.

```text
Review only this bounded scope. Do not expand to the whole repository.

- files:
  - <path-1>
  - <path-2>
- change summary: <one sentence>
- focus: correctness, regression, security, missing tests
- scope limit: stay within these files unless one direct dependency is required to justify a finding

Return only:
1. findings first, ordered by severity
2. file/line evidence for each finding
3. if no material issue is found, explicitly say "no high-signal findings in this bounded scope"
4. one highest-risk unchecked area, or "none"
```
