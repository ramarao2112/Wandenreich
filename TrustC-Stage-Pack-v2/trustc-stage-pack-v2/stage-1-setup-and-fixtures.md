# Stage 1 — Setup, contracts and independent fixtures

## Goal and dependencies

Create an installable repository with executable contracts and trusted reference fixtures. No parser, compiler, server or UI behavior yet. Read 00, A, B and C first. Prerequisite: choose v2 as the implementation baseline in the Stage 1 prompt.

## Work

1. Inspect existing files/git state and record what already exists. Preserve unrelated changes. Initialize git only if this is not already a repository. Do not replace an existing application scaffold blindly.
2. Record available Python/Node versions. Select compatible stable dependencies using official documentation/package metadata, pin and lock them. Separate CLI/core, generated-app, server and development dependencies. Include pytest, async test support, lint tooling, schema generation and future frontend test dependencies in the correct groups. Do not label all packages runtime dependencies.
3. Create `pyproject.toml`, `src/trustc/__init__.py`, a minimal `cli.py` with --help/--version, package-data rules for future grammar/templates/rule docs, `.gitignore`, test configuration and `scripts/check-stage.py`. The latter accepts stages 1–8 and executes their registered checks; later stages extend it. Unsupported/unimplemented stages must fail clearly, never pass with no tests.
4. Implement A as Pydantic contracts and exported JSON Schema. Generate or mirror `ui/src/api/types.ts` with a drift test. Add discriminated-result validation so status and exitCode combinations cannot conflict. Give schema version 2 its own location.
5. Copy F1–F7b from this pack; author X fixtures from C with independent expected decisions. Create F1/F2 full expected checks, plus focused expectations for other fixtures. Future-stage tests live in separate files not selected until their stage; no blanket xfail hiding import failures.
6. Verify line counts/positions, proposed TC-001 diff application, and F1-to-F2 exact round trip using a temporary copy, never editing canonical fixtures. Write a short fixture provenance note.
7. Establish `docs/progress/`, `docs/decisions/`, `docs/dependencies.md` and a source inventory that names the missing Master document/mockup ZIP. Missing assets do not block this revised pack. Record the platform and compatible package locks.

## Deliverables

Installable CLI, locked dependency files, contract models/schema/types, fixtures/expected decisions, fixture tests, stage checker and Stage 1 handoff. Python package installs from source and wheel with the expected data manifest.

## Gates

```bash
python -m pip install -e '.[dev,generated-app,server]'
trustc --help
python scripts/check-stage.py 1
```

The stage checker runs contract round trips, invalid-union rejection, fixture validation and lint for implemented files. At this point it must not pretend future compiler tests passed. Confirm F1=30, F2=31, F3=38 lines; TC-001 23:1; TC-003 30:3; F4 23:25; F5 20:23.

## Handoff

Write `docs/progress/stage-1.md`: installed versions, actual commands/results, source inventory, proposed decisions selected, changed files, remaining work and Stage 2 prompt. Explain how goldens remain independent and why v1 contracts cannot be mixed in. Tag only after gates pass.

Next prompt: “Implement Stage 2 only from docs/handoff-v2/stage-2-parse.md; verify Stage 1 first and preserve its contracts.”
