# D — Improved TrustC workbench

## Design objective

Keep the original one-screen dark developer workbench, but give the security outcome priority over logs and controls. The earlier conversational preview is directional, not production code or an approved screenshot baseline. This document supplies a buildable layout without requiring that preview file or the missing mockup ZIP.

The original UI PDF remains useful for the 19 states, stale-result handling, fix provenance and accessibility. v2 overrides its result wording, proof claims, tiny default sizing, API shapes and mandatory screenshot matching. Use A/B for behavior when they differ.

## Layout and tokens

Desktop target 1440×900. Top bar: brand, project/file identity, examples menu, visible Live/Mock/Recorded indicator. Workflow actions: Check → Build → Test access, with one prominent next action. The button invokes the real command; tabs only inspect stored results. Tab labels: Diagnostics, Generated code, Access tests, Build evidence.

Use a 42/58 editor/results split, adjustable only as optional polish. At widths below 900, stack panes; allow natural page scrolling rather than clipping essential controls. At 1440 the main panes may scroll internally. Keep all mandatory content readable at 125%/150% zoom. Presenter mode enlarges results, not just every control until it overflows.

Define product tokens in one file: canvas #0C111B, panel #121A27, raised #1A2535, border #2B384B, primary text #EDF2FA, secondary #ACBBCE, interactive/provenance teal #63DFD0, success #87E2AF, review #F3C47E, error #FF8795. Dark ink on filled teal buttons. Verify each real text/background pair; do not claim contrast based only on a palette screenshot.

IBM Plex Sans/Mono bundled locally. Base UI 14–15px; editor 14px with approximately 22px line height; secondary 12px minimum; result headline 24–28px. Avoid huge decorative headings. Radius 6px for controls, 8px for diagnostic containers. No animated backgrounds, dashboard metrics, invented security scores or unnecessary sidebar navigation.

## Interaction details

**Diagnostics:** lead with the next actionable issue and its consequence. Expand selected diagnostic; link precise source span. “Suggested restrictive default” labels auth diff. Apply requires a click; preview and undo work. Public/private business decisions are not automatically selected. Passed and not-applicable rules are distinguishable and collapsible.

**Generated code:** show file tree, selected code and a visible “Why this line exists” inspector. Selecting a generated check highlights its source declaration; selecting source can navigate to related checks. Hover supplements, but does not exclusively expose, provenance. Keep exact response schema and self-access checks inspectable.

**Access tests:** lead with a concrete observed result only after completion, for example “Other users were blocked. The owner received access.” Group by endpoint with three actor rows; display expected/received HTTP codes and non-status assertions. Pending rows are neutral. Blocked-as-expected is green; declared broad access is amber; contradiction is red. Logs are expandable below the outcome. Never animate fabricated live results.

F2 summary: “6 matched expectations · 0 policy reviews · 0 failed.” F3: “9 matched expectations · 1 policy review · 0 failed.” A reviewed result still matches expectations; matched = asExpected + review. A pending run has no final summary; a terminal execution error is separate from test failure.

**Build evidence:** sections for compiler checks, endpoint policies/declared exceptions, runtime observations if a matching attack exists, coverage and known limits. Show source/build identity in expandable details. Use “Not tested” when no relevant runtime observation exists. Export combined report with separate build and attack objects. No “secure,” universal “proof,” or unsupported zero-exposure claim.

**Footer:** plain current status, exact equivalent CLI for last executed action, exit code and duration. Switching tabs must not rewrite action history. Explain that web source must be saved as spec.trust before using its command.

## State model

Store source/version/hash, server sessionId, current action/run ID, immutable results, selected result tab, active diagnostic/source span, connectivity and data mode. Derive pills/locks/staleness/badges instead of storing independent booleans.

Every source edit increments version. If content differs, prior results remain readable with “Earlier source revision”; current success disappears and Test access locks. Reverting to identical text may reuse matching build content only when server session/build availability are still valid. Do not rely on counter equality alone.

Snapshot source at run start. Later events update that run's historical result, never overwrite current editor text or claim current success. Match runId/specHash before applying UI updates. Cancel is a separate action; it does not become Completed until the server confirms terminal cleanup. On offline/reconnect retrieve final result or replay events; do not silently start a new run.

Buttons visually locked with aria-disabled remain focusable and explain the prerequisite; every activation handler enforces the lock. Use standard keyboard-operable tabs. Any mode with fixture/recorded data has a persistent visible label, including exported summaries. Mock and recorded evidence never merges into a Live build.

## Required screens

Ready, checking, diagnostics failed, diff/prompt preview, edited/stale, check passed, building, build succeeded/code provenance, tests running, tests passed, tests failed, build evidence, syntax/reference/unsupported error, rule explanation, offline, examples, build refused, policy review, evidence with declarations, cancelled, timed out, execution error and empty test coverage. Screens are states of the same workbench, not new navigation pages.

## Accessibility and visual acceptance

Keyboard-only main flow, visible focus, labelled editors/buttons, aria-live for coarse status changes, icons/text with every state color, reduced motion, responsive layouts and readable zoom are required. Do not announce every streaming log line. Keep clipboard fallback visible.

Since original HTML/PNG assets are absent and layout has changed, do not enforce a fictional 2% difference against old baselines. Stage 7 captures and reviews new state screenshots in a fixed browser/font environment, then adopts those approved baselines for regression. Functional and accessibility gates are independent of pixel matching.
