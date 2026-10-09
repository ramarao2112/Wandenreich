# TrustC: Policy-to-Execution Compiler & Developer Workbench

[![Stage Status](https://img.shields.io/badge/Stage%201--8-PASS-brightgreen)](docs/progress/stage-8.md)
[![Schema Version](https://img.shields.io/badge/Schema%20Version-v2-blue)](src/trustc/schemas/v2/)
[![Axe Accessibility](https://img.shields.io/badge/Axe%20Accessibility-0%20Violations-brightgreen)](ui/e2e/a11y.spec.ts)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

TrustC is a domain-specific compiler that translates high-level resource and authorization declarations (**TrustSpec**) into self-contained, provably secure FastAPI web services backed by SQLite.

Rather than relying on after-the-fact runtime scanning or manual code review, TrustC evaluates access control and data exposure policies **at compile time**, automatically generates restrictive diff fixes, enforces authorization checks directly in emitted AST routes, and validates multi-actor invariants with a built-in isolated access attack harness.

---

## Table of Contents

- [Core Principles](#core-principles)
- [System Architecture](#system-architecture)
- [Prerequisites & Installation](#prerequisites--installation)
- [CLI Reference](#cli-reference)
- [Developer Workbench UI](#developer-workbench-ui)
- [TrustSpec DSL Reference](#trustspec-dsl-reference)
- [Five-Rule Security Catalog](#five-rule-security-catalog)
- [Policy Semantics & Data Exposure](#policy-semantics--data-exposure)
- [Test-Only Identity Seeder](#test-only-identity-seeder)
- [Three-Minute Live Demo](#three-minute-live-demo)
- [Platform Scope & Known Limitations](#platform-scope--known-limitations)
- [Reset & Maintenance](#reset--maintenance)

---

## Core Principles

1. **Security Outcome Over Vanity Metrics**: TrustC evaluates concrete multi-actor authorization invariants (e.g., *"Did another signed-in user receive a 403 Forbidden when requesting another user's trip?"*), not superficial coverage statistics.
2. **Compile-Time Refusal with Rollback**: If a specification violates security rules or contains syntax errors, compilation is refused (exiting with code 1 or 2). Existing destination directories are untouched, preserving atomic rollback.
3. **Cryptographic Provenance**: Every generated line of code contains source comments mapping back to declarations in `spec.trust`. Emitted manifests and build artifacts include length-prefixed SHA-256 digests.
4. **Offline and Self-Contained**: The compiler, local API server, generated FastAPI backend, and React workbench UI function completely offline without calling external CDNs, cloud services, or remote analytics.

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TrustSpec Source (spec.trust)                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
                     ┌─────────────────────────────┐
                     │    TrustC Parser (Lark)     │
                     └──────────────┬──────────────┘
                                    │ Immutable IR
                                    ▼
                     ┌─────────────────────────────┐
                     │   Static Verifier & Rules   │◄── Rules: TC-001..TC-005
                     └──────────────┬──────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               │ (Pass)                                  │ (Fail: Refusal exit 1)
               ▼                                         ▼
┌─────────────────────────────┐           ┌─────────────────────────────┐
│  Code Generator & Jinja2    │           │ Actionable Diagnostics &    │
│  - FastAPI Routes           │           │ Unified Diff Auto-Fixes     │
│  - Pydantic v2 Models       │           └─────────────────────────────┘
│  - SQLite Schema & Auth     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│    Generated Application    │
│    (Isolated Runtime)       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│   Live Local Access Harness │◄── Multi-Actor Scenarios (Owner,
│   (Loopback HTTP Assertions)│    Anonymous, Second User)
└─────────────────────────────┘
```

---

## Prerequisites & Installation

### Prerequisites

- **Python**: 3.10, 3.11, 3.12, 3.13, or 3.14 (tested on Windows Python 3.14.4 and Linux Python 3.12)
- **Node.js**: 18.x or 20.x (only required for building the UI from source)
- **Git**

### Installation from Source

Clone the repository and install with all extras:

```bash
git clone https://github.com/ramarao2112/TrustC.git
cd TrustC

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with harness and server extras
pip install -e ".[harness,server]"
```

### Installation from Built Wheel

```bash
# Build the wheel package
python -m build --wheel --outdir dist/

# Install in an isolated environment
pip install dist/trustc-0.1.0-py3-none-any.whl[harness,server]
```

---

## CLI Reference

The `trustc` command-line tool provides full access to every compiler stage:

| Command | Description | Exit Codes |
|---|---|---|
| `trustc parse <spec>` | Parses syntax into AST/IR and checks structural validity. | `0` (Success), `2` (Syntax error) |
| `trustc check <spec>` | Evaluates security rules TC-001 through TC-005. | `0` (Clean), `1` (Violations), `2` (Syntax error) |
| `trustc check <spec> --apply-fix` | Automatically applies unified diff fix to resolve diagnostic. | `0` (Success), `1` (Unfixable or dirty) |
| `trustc explain <rule_id>` | Displays reference documentation and remediation for a rule. | `0` (Success), `2` (Unknown rule) |
| `trustc build <spec> -o <out>` | Emits production FastAPI project with SQLite database and auth. | `0` (Success), `1` (Refused), `2` (Syntax error) |
| `trustc attack <spec>` | Generates app in temporary sandbox and executes access harness. | `0` (Pass/Review), `1` (Sabotage/Failed) |
| `trustc serve [--port 8787]` | Starts the local API server and serves the Developer Workbench. | `0` (Clean shutdown) |

### CLI Examples

```bash
# Parse a specification
trustc parse tests/fixtures/F2.trust

# Check for security violations with human or JSON output
trustc check tests/fixtures/F1.trust --format=human
trustc check tests/fixtures/F1.trust --format=json

# Export OASIS SARIF 2.1.0 report for CI/CD integration
trustc check tests/fixtures/F1.trust --sarif > results.sarif

# Explain a security rule
trustc explain TC-001

# Build a clean specification to an output folder (requires --replace if exists)
trustc build tests/fixtures/F2.trust -o ./dist-app --replace

# Run multi-actor access harness against a specification
trustc attack tests/fixtures/F2.trust
```

---

## Developer Workbench UI

TrustC includes a dark single-screen developer environment served directly by `trustc serve`:

```bash
trustc serve --port 8787
```

Open your browser to `http://127.0.0.1:8787`.

### Workbench Features

- **42/58 Desktop Split**: Code editor on the left; diagnostics, generated code, access tests, and evidence tabs on the right. Smoothly stacks vertically below 900px.
- **CodeMirror 6 Editor**: TrustSpec syntax-aware editor with line numbers, cursor status, and an undo stack (`Ctrl+Z`).
- **Interactive Diff Previews**: One-click preview of suggested restrictive defaults with atomic patch application and base-hash verification.
- **Strict Staleness Tracking**: Any edit in the editor immediately marks existing results as *"Earlier source revision"* and locks downstream build/attack operations until re-checked.
- **Provenance Inspector**: Highlights compiler-forced code lines (`route`, `auth`, `owner-check`, `self-check`) and maps each line to its source declaration in `spec.trust`.
- **Authoritative Multi-Actor Results**: Visualizes exact execution outcomes for `owner`, `second_user`, and `anonymous` actors with a logs drawer.
- **Axe-Certified Accessibility**: 0 violations under WCAG 2.1 AA in real-browser Chromium tests. Full keyboard control (`Tab`, `Ctrl+Enter` to check, `Escape` to cancel).
- **Bundled Offline Fonts**: Packaged with local IBM Plex Sans and IBM Plex Mono fonts; zero external network requests.

---

## TrustSpec DSL Reference

TrustSpec is a declarative language defining data models, secrets, and HTTP endpoints:

```trustspec
resource User:
  fields:
    id: uuid
    email: string
    password_hash: string [sensitive]

resource Trip:
  fields:
    id: uuid
    destination: string
    owner_id: uuid -> User.id

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint POST /trips:
  resource: Trip
  auth: required
  body: [destination]
  returns: Trip

endpoint GET /trips/{id}:
  resource: Trip
  auth: required
  returns: Trip

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User [id, email]
```

---

## Five-Rule Security Catalog

| Rule ID | Rule Name | Description | Severity | Fix Type |
|---|---|---|---|---|
| `TC-001` | `AUTH-REQUIRED` | Endpoints must declare `auth: required` or `auth: public`. | ERROR | Unified Diff (`auth: required`) |
| `TC-002` | `ACCESS-CHECK-REQUIRED` | Endpoints on owned resources must enforce owner or role check. | ERROR | Manual / Unified Diff |
| `TC-003` | `SENSITIVE-EXPOSURE` | Response projections must not expose fields marked `[sensitive]`. | ERROR | Projection Narrowing |
| `TC-004` | `MASS-ASSIGNMENT` | Request body cannot contain server-controlled fields (e.g. `owner_id`, `id`). | ERROR | Body Exclusion |
| `TC-005` | `HARDCODED-SECRET` | Secrets must use `env` declarations; inline secrets are prohibited. | ERROR | `env` Declaration |

---

## Policy Semantics & Data Exposure

1. **Owner-Protected Resources**: If a resource declares an `owner_id: uuid -> User.id` field, the compiler automatically:
   - Sets `owner_id = current_user.id` on creation (`POST`).
   - Restricts read/update/delete operations to `owner_id == current_user.id`.
   - Returns HTTP 403 Forbidden when accessed by any other authenticated user.
2. **User Self-Access**: On the `User` resource, `GET /users/{id}` enforces `id == current_user.id`. Nonexistent users return 404; requests for another user's ID return 403.
3. **Sensitive Field Filtering**: Fields marked `[sensitive]` (such as `password_hash`) are automatically stripped from default projections. Returning a full resource without explicit projection triggers `TC-003`.
4. **Ownership Waivers (F3)**: Endpoints may declare explicit waivers (`authorize: ...`) allowing wider access. Such declarations pass compiler verification but are surfaced prominently in the UI and test harness as **Policy Reviews**.

---

## Test-Only Identity Seeder

TrustC generates deterministic in-memory test identities to exercise the multi-actor access harness:

- `owner`: Alice (`id: 11111111-1111-1111-1111-111111111111`, `alice@example.com`)
- `second_user`: Bob (`id: 22222222-2222-2222-2222-222222222222`, `bob@example.com`)
- `anonymous`: Unauthenticated requests without bearer token.

> [!IMPORTANT]
> The test seeder is strictly for automated harness execution and local rehearsal. TrustC does not invent a production login endpoint. In production, JWT tokens are issued by your organization's identity provider using a verified 256-bit secret key.

---

## Three-Minute Live Demo

| Time | Rehearsal Action | What Is Observed |
|---|---|---|
| **0:00–0:25** | Open `F1` (Flawed Trip Planner) in Workbench | Highlights unauthenticated `/trips/{id}` (`TC-001`) and exposed `password_hash` (`TC-003`). |
| **0:25–0:55** | Run Check, preview diff fix, click Apply fix | `TC-001` is resolved via unified diff. In CodeMirror, manually narrow line 31 to `returns: User [id, email]`. |
| **0:55–1:20** | Run Check (5/5 pass) and click Build | Compilation succeeds with atomic rollback guarantee. Code viewer displays AST provenance comments. |
| **1:20–2:05** | Click Test Access | Multi-actor harness runs: anonymous gets 401, second user gets 403, owner gets 200. Results: 6 matched, 0 review, 0 failed. |
| **2:05–2:35** | Inspect Evidence Tab | Shows invariant proof, tested endpoint policies, and downloads `trustc-evidence-F2.json`. |
| **2:35–3:00** | Inspect Footer & Equivalent CLI | Demonstrates full CLI parity (`trustc attack tests/fixtures/F2.trust`). |

---

## Platform Scope & Known Limitations

- **Target Backend**: Emits Python 3.10+ FastAPI backends using SQLite and SQLAlchemy.
- **Single-Node Execution**: Generated backends are designed for single-node services or containerized microservices.
- **No Distributed Identity**: Expects standard HS256 JWT tokens; does not configure external OAuth2/OIDC redirection flows.
- **Synchronous / ASGI**: Generated routers use asynchronous FastAPI endpoints with SQLite thread safety.

---

## Reset & Maintenance

To safely reset local background server processes without killing unrelated user processes:

```bash
python scripts/reset-workbench.py
```

To reset browser UI cache and state, load the workbench with `?reset=1`:
```
http://127.0.0.1:8787/?reset=1
```
