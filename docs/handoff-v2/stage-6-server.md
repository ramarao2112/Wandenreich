# Stage 6 — Local API, streaming and artifact lifecycle

## Goal and dependencies

Expose the same compiler/harness services through A's HTTP contract. Stage 5 passes. No new compiler logic in HTTP handlers. Local development/demo only; this is not a multi-user hosted execution service.

## Work

1. Implement `trustc serve --port 8787 --static ./ui/dist`, bound to 127.0.0.1. Register /api routes before the optional static mount; never turn unknown /api paths into index.html. Use an isolated configurable workspace for server artifacts.
2. Implement A's ten operations. Examples include F1/F2/F3/F4/F5/F6 so the waiver demonstration is actually selectable. Unknown rule/run/build identifiers get structured 404; expired retained items get 410. Check semantic results retain their 0/1/2 exit meaning.
3. Enforce request-body limit before unbounded reading, decoded spec byte limit, expected JSON shape/content type, safe Host and allowed Origin values. Allow only the actual loopback UI origins in development and same-origin in demo; do not use wildcard credentialed CORS. Reject untrusted browser origins on mutating requests. CLI requests without Origin still require correct JSON and allowed Host. Document that the service assumes a trusted local OS user; it is not authenticated isolation from other local processes.
4. Run accepted build/attack jobs in supervised workers. A lock is acquired atomically before returning 202. Do not assume cancelling an async task stops a blocking thread. All worker writes remain in staging; the parent publishes only a successful, noncancelled current run. Check jobs also have an enforceable 5-second deadline.
5. Implement build timeout 20 seconds, attack timeout 60 seconds and bounded cleanup grace. DELETE requests cancellation and returns 202 until cleanup finishes. Cleanup complete → terminal event; already terminal → 204. Unknown → 404. If forced termination is needed, track/reap children explicitly. Shutdown cancels and cleans up active work.
6. Stream RunEvent using A's sequence/cursor rules. Flush as events occur. Buffer replay within its cap, send heartbeat comments, and retain final result for polling/recovery. A listener disconnect does not imply user cancellation; reconnect resumes. Never replay one run's events into another.
7. Publish immutable build artifacts, manifest and evidence keyed by buildId. ZIP entries are relative generated paths only; reject traversal/symlinks and user-chosen server output paths. Downloads resolve the requested build ID. A refused current build leaves the prior artifact available only under its own ID, clearly marked previous in the UI.
8. API attack with buildId verifies source hash and compiler/template identity and tests an isolated copy. Without buildId build internally. The artifact checksum in AttackCompleted must match the copy actually executed. Server restart changes sessionId; stale browser IDs become unavailable.

## Gates

```bash
python scripts/check-stage.py 6
trustc serve --port 8787
```

Implement `scripts/smoke-server.py` reading F2 from disk and sending valid JSON, receiving SSE, checking terminal identity and downloading that build ID. No `...F2 text...` placeholder in commands.

Test Check parity with CLI; F1 refusal and F4 invalid_spec via build/attack; F2 and F3 streamed real results; concurrent run 409; cancellation while executing and immediately before publication; replay/drop/reconnect; terminal deduplication; bounded buffer; timeout actually stops writes/child processes; version/hash mismatch; wrong build download; server restart; malicious Host/Origin/path and oversized/chunked input; sanitized errors. A heartbeat alone must not keep a dead job looking successful.

## Handoff

Record API schema, tested routes, event examples without secrets, lifecycle decisions and smoke results. State any platform limitation in process cleanup. Next: Stage 7 UI, connecting to the real server from its first functional milestone.
