# TrustC 3-Minute Live Demo Script & Technical Q&A

**Target Duration:** Exactly 3 minutes (180 seconds)  
**Presenter Context:** Presenting to engineers, architects, and security reviewers.  
**Audience Baseline:** Understands REST APIs, JWT tokens, and basic OWASP authorization risks (IDOR/BOLA).

---

## 1. Rehearsal Cue Cards & Timeline

### `0:00 – 0:25` — The Broken Specification (Fixture F1)
- **Screen Action:**
  - Launch browser at `http://127.0.0.1:8787`.
  - Select **"F1: Trip Planner (Flawed)"** from the example specification dropdown.
- **Presenter Narrative:**
  > *"Welcome everyone. In modern web frameworks, authorization is usually left to developers' diligence in writing middleware or ORM queries. Here is a declarative TrustSpec for a Trip Planner application. Notice two critical security bugs right in the source: endpoint `GET /trips/{id}` does not declare authentication, and `GET /users/{id}` returns the entire `User` object, which contains a marked sensitive field `password_hash`."*

---

### `0:25 – 0:55` — Static Verification & One-Click Fix
- **Screen Action:**
  - Click **Check** (`Ctrl+Enter`).
  - Show the Diagnostics tab displaying **2 Actionable Security Issues**: `TC-001 (AUTH-REQUIRED)` and `TC-003 (SENSITIVE-EXPOSURE)`.
  - Click **Preview fix** on `TC-001`. Show the unified diff modal inserting `auth: required`.
  - Click **Apply fix**.
  - In CodeMirror editor line 31, update `returns: User` to `returns: User [id, email]`.
- **Presenter Narrative:**
  > *"When we click Check, the compiler's static verifier immediately flags both issues before emitting a single line of backend code. For the missing authentication rule, TrustC suggests a restrictive default: inserting `auth: required`. We apply the patch atomically with one click. Then, in the editor, we narrow the returned projection on `GET /users/{id}` to just `[id, email]`. TrustC's live staleness tracker immediately marks the prior check as an earlier revision."*

---

### `0:55 – 1:20` — Compilation with Cryptographic Provenance
- **Screen Action:**
  - Click **Check** again. Show **Specification checks passed: 5 of 5 security rules satisfied**.
  - Click **Build**.
  - Show the Code tab: file tree (`main.py`, `models.py`, `schemas.py`, `auth.py`, `router.py`, `manifest.json`).
  - Highlight the line comment: `# ForcedLine: owner-check: Trip.owner_id == current_user.id`.
- **Presenter Narrative:**
  > *"With both issues resolved, the specification passes all five security rules cleanly. Now we click Build. The compiler emits a complete, self-contained FastAPI application with SQLite database migrations and Pydantic schemas. Look at the generated router: every security check contains an explicit provenance comment linking it back to the exact declaration line in `spec.trust`. The build manifest is cryptographically hashed with SHA-256."*

---

### `1:20 – 2:05` — Live Multi-Actor Access Testing
- **Screen Action:**
  - Click **Test access**.
  - Results appear in the Tests tab:
    - Headline: **"Other users were blocked. The owner received access."**
    - Metrics: **6 matched expectations · 0 policy reviews · 0 failed**.
  - Expand `second_user` attempt on `GET /trips/{id}`: HTTP 403 Forbidden.
  - Expand `owner` attempt on `GET /trips/{id}`: HTTP 200 OK.
- **Presenter Narrative:**
  > *"Static checks are good, but real security requires live verification. When we click Test Access, TrustC spins up an isolated loopback test runtime and runs multi-actor adversarial queries. Watch what happens: an unauthenticated caller is rejected with 401. A second authenticated user trying to read Alice's trip is blocked with 403 Forbidden. Only the owner gets HTTP 200. We observe 6 matched expectations and zero unexpected breaches."*

---

### `2:05 – 2:35` — Build Evidence & Verifiable Reporting
- **Screen Action:**
  - Click the **Build evidence** tab.
  - Show the Invariant Verification summary, tested endpoints table, and target build ID.
  - Click **Export JSON report** to trigger browser download of `trustc-evidence-F2.json`.
- **Presenter Narrative:**
  > *"Under the Build Evidence tab, we see the complete proof bundle tying the observed test results directly to the specific build hash. This report can be exported as structured JSON for compliance auditing, zero-trust gating, or pipeline deployment approvals."*

---

### `2:35 – 3:00` — Full CLI Parity & Conclusion
- **Screen Action:**
  - Scroll to the Footer: show the exact command `trustc attack tests/fixtures/F2.trust`.
  - Click the Copy button.
  - Optional: Switch to terminal and run the copied command to show identical exit code 0 and JSON output.
- **Presenter Narrative:**
  > *"Everything we just demonstrated in the UI has 100% parity with the `trustc` CLI. In your CI/CD pipeline, `trustc check` and `trustc attack` run non-interactively with exact exit codes. TrustC proves that authorization policies don't have to be runtime guesswork—they can be compiled, proven, and enforced from day zero. Thank you!"*

---

## 2. Technical Q&A Sheet

### Q1: Why compile authorization instead of using an existing library like OPA (Open Policy Agent) or CASBIN?
**Answer:** OPA and Casbin evaluate policies *dynamically at runtime* on every request. While powerful, if a developer forgets to insert the policy check middleware on an endpoint, the service fails open silently. TrustC works at *compile time*: if an endpoint accesses an owned resource without authorization rules, the compiler refuses to emit code (exit 1), making forgotten authorization impossible.

### Q2: What happens if an endpoint legitimately needs to bypass owner-only checks (e.g., public trips)?
**Answer:** TrustSpec supports explicit waivers. For example, fixture `F3` specifies `authorize: true` on `PUT /trips/{id}/visibility`. The compiler accepts this, but the access harness and UI prominently categorize the outcome as a **Policy Review** rather than a clean pass, alerting auditors that a declared exception exists.

### Q3: How does the generated app authenticate requests in production?
**Answer:** In production, requests include standard Bearer JWT tokens (`Authorization: Bearer <token>`). The generated service verifies the signature using a verified HMAC-SHA256 secret (`JWT_SECRET` env var, strictly >= 32 bytes) and extracts `sub` as `current_user.id`. The in-memory identity seeder (`Alice`, `Bob`) is strictly for test execution and rehearsal; TrustC does not invent a fake production login endpoint.

### Q4: Does the compiler protect against SQL injection and mass assignment?
**Answer:** Yes. SQL injection is mitigated structurally because all data access is generated using parameterized SQLAlchemy Core expressions. Mass assignment is prevented by rule `TC-004`: server-controlled fields like `id` and `owner_id` are forbidden in request bodies, and Pydantic schemas reject unexpected fields with HTTP 422.

### Q5: How do you guarantee the test results aren't from an older version of the code?
**Answer:** TrustC implements strict staleness tracking. Every build and attack run is tagged with the SHA-256 hash of the specification source (`sourceHash`). If a single character changes in the editor, all prior results are visually flagged as *"Earlier source revision"* and downstream build/test operations are locked until a new check is executed.

---

## 3. Presenter Recording Instructions

If you need to record the presentation for offline review:

1. **Option A: Automated Real-Browser Session Recording**:
   - The Playwright suite in [scripts/run-browser-tests.py](file:///c:/Users/rama%20rao/OneDrive/Desktop/TrustC/scripts/run-browser-tests.py) captures high-resolution screenshots for each step into `review-logs/stage-7/screenshots/`.
2. **Option B: Manual Screen Recording**:
   - Start the server: `trustc serve --port 8787`
   - Set browser zoom to 100% on a 1440×900 or 1920×1080 display.
   - Use OBS Studio, Windows Game Bar (`Win+Alt+R`), or QuickTime.
   - Follow the 3-minute cue cards verbatim.
