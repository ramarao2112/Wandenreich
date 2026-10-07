# Stage 7 — Workbench with real compiler integration

## Goal and dependencies

Implement D's improved one-screen UI against A's server. Stage 6 passes. The original PDF is a supplementary state reference; missing mockup assets are not a blocker. Do not build a static simulation and label it finished.

## Milestones

| Milestone | Implement | Gate |
|---|---|---|
| M0 | Vite/React/TS shell, tokens, local fonts, generated API types, CodeMirror, state store | Responsive shell and accessible editor; installed toolchain locks reused |
| M1 | Real /meta, examples and Check; diagnostics, positions, explain and spec errors | F1/F2/F4 use the live server; keyboard navigation reaches source errors |
| M2 | Diff/prompt preview, apply/undo, source hash, stale results | F1→F2 exact round trip; stale patch refused; arbitrary edits cannot retain success |
| M3 | Real Build SSE, terminal errors/refusal/cancel, file tree and source provenance | F2 generated code downloadable by its buildId; rejected build shows no new artifact |
| M4 | Real Test access SSE, three outcomes, coverage and logs | F2 six results; F3 nine results and one review; mutation fixture only in labelled test mode |
| M5 | Evidence join/export, reconnect, timeout/offline/session restart | Mismatched evidence rejected; interrupted run recovers without duplicate result |
| M6 | Required state coverage, accessibility, responsive polish and visual baselines | Real-server demo + failure paths pass; no secret in DOM/log/export |

## Implementation requirements

Use separate api/, state/, editor/ and result components. One shared run controller manages submission, deadlines, cancellation, replay and terminal handling. Use typed schema validation at boundaries. A stale or another-session run cannot update current completion state. Server outcome is authoritative; UI derives only display counts such as matched = asExpected + review.

Editor edits remain allowed while a run owns a source snapshot; make resulting staleness visible. Apply fix is one CodeMirror transaction. Never apply a patch with the wrong base hash. Prevent accidental example replacement with unsaved edits through an undoable action or clear replace notice.

Show required offline/timeout/cancel/error/review states now, not as optional polish. Test access button requires an available successful matching build. API may accept buildless attack for CLI-equivalent callers, but the UI follows its visible workflow. On server session change invalidate run/build handles and explain a rebuild is needed.

Mock mode exists for isolated visual-state tests. Initially use independently authored A-compatible fixtures; once backend exists cross-check them against real outputs. Label mode persistently. A recorded real run is an optional fallback view with permanent “Recorded run” label and no live timing claims; it never resumes as a real job.

No external CDN fonts, arbitrary HTML diagnostics, fabricated timings or hard-coded endpoint/rule totals. Explain generated-line provenance on click/focus, not hover alone. Use a real download link for selected buildId. Source export is available so copied CLI commands can be run on the same specification.

## Gates

```bash
python scripts/check-stage.py 7
```

Register UI typecheck, production build, unit tests, real-server Playwright flows and axe checks in this stage's checker. Browser tests start/stop only their own server with a fresh workspace and isolated storage.

Required flows: F1 fix/manual projection/check/build/test/evidence; F4 parse correction; F3 waiver review; build refusal over previous output; edit during run; stale diff; cancel build before publication; cancel attack; timeout; server loss/reconnect; server restart; wrong-build export; keyboard-only demo; 1440×900, 1024px and narrow layout/zoom checks. Verify every visible count comes from results.

Capture representative screenshots after each milestone; freeze new baselines only after review. Do not hold real-server wiring until all visual states exist. Optional last: resizable split, presenter shortcut, rename and live syntax lint.

## Handoff

Provide the actual production build/test outcomes, state checklist, screenshots, remaining polish and known platform limits. Confirm Live and Mock separation. Next: Stage 8 release and demo.
