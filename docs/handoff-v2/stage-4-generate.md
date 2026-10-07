# Stage 4 — Generate and execute the backend

## Goal and dependencies

Build F2 into a runnable FastAPI app and verify authorization and persistence. Stages 1–3 pass. Read B6/B7, A BuildSuccess/BuildEvidence and C. Implement one real owner-protected read before generalizing.

## Work

1. Implement templates for models, request/response schemas, auth, DB session lifecycle, routes, app startup, dependencies and README. Include routers/__init__.py; do not optimize for the old seven-file count. Generate all supported B2 operations and reject everything else before writing.
2. Implement fixed-algorithm JWT validation and existing-user lookup per B6. Never accept token-controlled algorithms or bypass verification. Get configuration from env without printing it. Allocate AsyncSession per request and rollback failed transactions.
3. Enforce owner assignment, list filters, item ownership and User self access. Requests reject extra JSON fields. Use allowlisted field updates. PUT requires all declared body fields; PATCH changes only present fields and rejects an empty patch. Denied operations produce no DB mutation.
4. Build per-endpoint response models with exact projections and null behavior. Sensitive fields require explicit allowed exposure; credential fields never appear. Missing returns on PUT/PATCH means `{}` with 200; DELETE means empty 204.
5. Emit source provenance, then scan rendered output to obtain its actual line map. Validate spans and generated paths. Record endpoint policies, waivers, sensitive selections and constraints in BuildEvidence; no unconditional zero-leak/fully-protected summary.
6. Render and syntax-check in staging. Publish only on complete success; test rollback and cancellation before publication. CLI handles existing outputs according to B6. Parent publication logic must be usable by the future server worker supervisor.
7. Write an internal test-fixture seeder reused by Stage 5. Seed two local users and typed data directly through generated models. Tokens stay in memory; no `--secret VALUE`, printed bearer tokens or public seeding endpoint. Create `scripts/smoke-generated.py` to start a local app, issue requests and clean up while reporting only sanitized status/assertions.

## Gates

```bash
python scripts/check-stage.py 4
trustc build tests/fixtures/F2.trust --target=fastapi -o .trustc-smoke/generated
python scripts/smoke-generated.py tests/fixtures/F2.trust
```

The stage checker uses fresh destinations. If the manual path exists, choose another or use the explicit manifest-guarded --replace flow.

Tests must run generated code against a real database. Assert Trip and User anonymous 401 / other-user 403 / owner 200; JSON projection excludes password_hash; list filters other-owner rows; denied updates/deletes leave DB unchanged; authorized operations persist; owner_id/id injection yields 422; malicious-looking string input is stored as data. Cover F3 waiver, expiry/wrong JWT claims, null defaults, email validation, schema collision and missing returns.

Build F1/F4 and injected rendering/write failures over a preexisting build: files stay byte-identical. Compile every generated Python file. Build/install wheel smoke verifies templates ship. Compare output hashes excluding IDs/timing/report metadata as documented; investigate unexpected nondeterminism.

## Handoff

Provide the actual generated-app smoke outcome, files/counts, tested auth behavior, artifact publication guarantees and limitations. Pattern scans may supplement, not replace, runtime checks. Next: Stage 5 access harness.
