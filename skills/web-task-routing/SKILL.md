---
name: web-task-routing
description: Choose the correct web or browser automation path. Use when the task involves public web extraction, browser session routing, current Chrome/Edge session reuse, localhost page debugging, screenshots, console/page errors, or choosing between agent-browser, Playwright MCP, and Playwright CLI. Do not use for ordinary code changes without browser interaction.
---

# Web Task Routing

Route web and browser work to the lightest reliable chain, then report results with concise evidence.

## Workflow

1. Classify the task:
   - Public information extraction or light interaction.
   - Existing browser session, login state, tab, or extension reuse.
   - Localhost/debug/repro/regression work requiring console, network, trace, or screenshots.
   - High-risk action such as payment, posting, deletion, approval, or order submission.
2. Select the link:
   - Use the ordinary web/search/fetch chain for public one-off extraction.
   - Use Browser or Playwright MCP only when real browser rendering, login/session reuse, or tab/extension context is needed.
   - Use Playwright CLI for localhost debugging, repeatable repro, trace/network/console capture, screenshots, or regression verification.
3. State the chosen link and reason before starting the web task.
4. Escalate only after observing a concrete limitation such as抓取受限, missing rendered fields, unstable interactions, or explicit session dependency.
5. Stop before high-risk final submit actions and ask for confirmation.
6. Deliver the result using the success or failure shape in `references/policy.md`.

## Reference

Read `references/policy.md` when the task needs detailed routing, escalation, screenshot, success-output, or failure-output rules.
