# Final review handoff — upload once for later review

At core completion (or a genuine blocking stop), prepare `TrustC-final-review.zip` and `FINAL-REVIEW.md`. The archive must permit another engineer to inspect and reproduce the result. A self-check report does not constitute independent verification.

## Include

- Application/compiler source, grammar, templates, rule docs, CLI, server and UI source.
- Tests, independent expected decisions, canonical F fixtures and X scenarios.
- Dependency manifests, exact locks, supported runtimes and installation instructions.
- JSON Schema, TypeScript API types and drift-generation tooling.
- This complete handoff-v3 pack; decisions and progress records; requirement/acceptance matrix.
- Sanitized stage/release command logs with real return codes; available browser traces and representative screenshots. Inspect traces for tokens before including.
- Final review report with source revision and dirty-tree status, modified/untracked included files, command results, security-rule mapping, known limitations and optional Stage 9 status.
- File inventory and SHA-256 hashes of included files, excluding the inventory's own hash. Save ZIP hash separately after packaging.
- An example generated F2 app/evidence if available and sanitized; label it build output, separate from source. Include runnable reproduction commands rather than a database or bearer tokens.

## Exclude

Real .env/credential files, API keys, JWTs, private keys, runtime databases, personal data, .git, node_modules, virtual environments, caches, run temp directories, previous ZIPs and the archive being created. A sanitized .env.example is allowed. Use an explicit inclusion list, do not indiscriminately archive the entire parent folder. Redact copied logs; preserve source files. A text scan is supplementary and not a guarantee of no secrets.

## Verify package

List its entries, reject absolute paths, traversal and symlinks, verify its inventory against packaged bytes, and ensure required source/fixtures/locks exist. Confirm reproduction paths are relative to repository root rather than one developer's home directory. Do not claim a clean installation was performed unless it ran. Document platform-specific process cleanup behavior.

## Review verdicts

Core self-check PASS / BLOCKED / FAIL; optional AI PASS / DEFERRED / BLOCKED; independent review PENDING. Do not label the application production-secure or independently approved. If mandatory tests cannot run, provide the partial archive and exact blocker rather than hiding it.

## Final user message

State completed stages, failing/unrun mandatory checks, optional status, exact ZIP path and how to start the local demo. Ask the user to upload the ZIP to this conversation for later review. Do not request review between already-passing stages.
