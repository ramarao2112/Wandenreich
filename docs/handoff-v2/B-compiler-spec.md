# B — Self-contained MVP compiler specification

## B1. Language boundary

TrustSpec describes a deliberately small CRUD API. It is not Python, SQL, an arbitrary expression language or an importer for existing backends. No eval, exec, user templates, raw query nodes, shell commands or executable plugins.

File order: one or more resources, optional secrets block, one or more endpoints. Top-level declarations start at column 1. Resource fields use two spaces for `fields:` and four for field declarations; endpoint attributes and secret declarations use two spaces. Reject tabs and inconsistent indentation. Blank lines and `#` comments are accepted outside tokens. LF-normalized source positions are preserved; a final newline is optional. Explicitly test a file with and without the final newline.

Supported forms (descriptive grammar; Stage 2 supplies the Lark implementation):

```text
resource NAME:
  fields:
    FIELD: TYPE [sensitive]
    OWNER: uuid -> User.id

secrets:
  DB_URL: env
  JWT_SECRET: env

endpoint METHOD /path:
  resource: NAME
  auth: required | public
  authorize: public | FIELD == current_user.id
  role_only: NAME
  body: [FIELD, FIELD]
  returns: NAME
  returns: NAME [FIELD, FIELD]
  expose: [FIELD, FIELD]
```

The alternatives are grammar choices, not literal pipe characters. Each endpoint attribute appears at most once, in any order; `resource:` is required. `auth:` may be absent syntactically so TC-001 can explain it. Optional attributes may be omitted; empty body `[]` is allowed, but empty response/expose projections are invalid. `role_only` parses only to produce a specific unsupported-policy TC-002 diagnostic. No other expression is accepted.

Types: uuid, string, text, int, bool, email. `enum`, `any`, unions, nested objects and arbitrary types are unsupported. Identifiers are ASCII `[A-Za-z][A-Za-z0-9_]*`; reject Python keywords, dunder names, generated reserved names and case-insensitive output-path collisions. Stage 2 defines one checked-in reserved-name set from actual generated imports/members (including metadata, registry, model_config). Values are parameters; identifiers are validated symbols, never accepted as executable fragments.

Every resource must have `id: uuid`; one resource must be named User. At most one ownership edge per non-User resource; it must be UUID -> User.id. User must not declare an ownership edge. Reject unknown/duplicate resources, fields, secrets, endpoint attributes, METHOD+path pairs and projected fields. Reject resource/path names that collide with generated module names or reserved routes. The v1 User endpoint is only `GET /users/{id}`; user creation/list/update/delete belongs to a later identity feature.

`password`, `password_hash`, `access_token`, `refresh_token`, `api_key`, `private_key`, and `jwt_secret` are reserved credential field names (case-insensitive). They must be marked sensitive, cannot be exposed, and cannot be client-writable in v1. These checks are finite protections, not a semantic detector for every possible secret name.

## B2. Paths and operations

Resource collection is `/` + lowercase resource name + `s` (Trip → /trips); intentionally no English pluralization. Path characters are restricted to ASCII letters, digits, `_`, `-`, `/` and the single supported `{id}` placeholder. No query strings, percent escapes, dot segments, repeated slashes or other braces. A suffix is one literal path segment. Reject unsupported shapes with an unsupported SpecError before rules run.

| Method and path | Operation | Success response |
|---|---|---|
| POST /collection | Create an ordinary resource | 201 + selected response fields |
| GET /collection | List ordinary resources | 200 + array of selected response fields |
| GET /collection/{id} | Read one | 200 + selected response fields |
| PUT /collection/{id} or /collection/{id}/suffix | Update every field named in body; require all these fields | 200 + response, or `{}` if returns omitted |
| PATCH /collection/{id} or /collection/{id}/suffix | Update provided subset of body fields; at least one required | 200 + response, or `{}` if returns omitted |
| DELETE /collection/{id} | Delete one | 204, no response body |

`returns:` is required for POST/GET; forbidden for DELETE; optional for PUT/PATCH. Its resource must equal the endpoint resource; cross-resource joins are unsupported. `body:` is allowed only on POST/PUT/PATCH. PUT/PATCH must declare a nonempty writable body. POST may have no body if the resource has no writable inputs. GET/DELETE reject body declarations. `expose:` requires returns and must name marked-sensitive fields selected by that response.

Primary keys and ownership fields are server-controlled, never input fields. All models store id/owner as non-null UUIDs. Other ordinary fields are nullable by default; bool defaults to false. Their output schemas accept null when stored null. POST and PUT require every declared body field, PATCH makes those fields optional; explicit null is not an accepted body value in v1. On creation fields not named in body receive their documented DB defaults (false for bool, null otherwise); no secret or credential default value is generated. This choice makes F3's omitted is_public deterministic. User fixtures are seeded directly with typed values.

## B3. AST, IR and validation order

1. Decode/limit/normalize source and calculate hash.
2. Lark parser builds nodes with start/end spans and original source slices.
3. Resolve symbols, types, paths, duplicates and unsupported operation shapes.
4. Build immutable typed IR with explicit auth absence and inferred policies.
5. Run all five verifier rules.
6. Only if accepted, lower through audited templates.

IR types include Program, Resource, Field, Endpoint, AuthPolicy, OwnershipExpr, QueryOperation, BoundParam and SecretRef. QueryOperation uses an operation enum plus validated resource/field symbols and typed values; no raw query field. SecretRef is a declared environment variable name, not a value. Store source text outside executable query/secret nodes for diagnostics. Use immutable containers where feasible. This constrains supported representation; it is not a formal proof about all Python objects.

Unknown names, malformed paths and unsupported methods are SpecErrors (exit 2, no rules). Wrong-but-existing authorization field and role_only remain representable for TC-002. Never repair the source in the IR builder. Record explicit declarations separately from inferred defaults.

Missing-colon errors point at the insertion point on the previous declaration line when justified by the parser's expected token set. F4 is 23:25. Do not rewrite all unexpected-token errors to the previous line. Errors display kind-specific labels: Syntax error, Unknown reference, Unsupported feature.

## B4. Authorization decisions

Definitions: owned resource = direct edge to User.id; identity endpoint = GET /users/{id}; unowned ordinary resource = neither.

| Input | Effective policy or error |
|---|---|
| auth missing | TC-001; retain absence |
| required, owned, authorize omitted | Create sets owner; list filters owner; item routes check owner |
| required, identity, authorize omitted | Self-only access: path id must equal signed-in User.id |
| required, ordinary unowned, authorize omitted | Login only; evidence explicitly says no object ownership model |
| required, owned, equality names ownership field | Same default owner policy; legal redundant declaration |
| required, identity, equality id == current_user.id | Same self-only policy |
| required, owned, authorize public, except POST | Login required, ownership waived; report declaration |
| public, owned, read/list/update/delete, authorize omitted | No login/owner check; report public declaration |
| public, ordinary unowned, authorize omitted | Public operation; report declaration |
| public, owned POST | TC-002: owner identity is unavailable |
| identity endpoint public or ownership waiver | TC-002: User is self-only in v1 |
| authorize on ordinary unowned resource | TC-002: no supported ownership predicate to enforce |
| public plus any authorize field | TC-002: contradictory/redundant controls; require one public declaration |
| owned POST plus authorize field | TC-002: creation assigns caller; read/update waivers do not apply |
| any role_only | TC-002: role policy unsupported; no bypass through codegen |
| equality references existing wrong field | TC-002 |
| equality references unknown field | reference SpecError |

Missing auth does not suppress independent errors. Avoid duplicate TC-002 messages for the same offending attribute. Authenticate before fetching an existing protected item, then 404 when absent and 403 on another owner's existing item. This deliberately exposes existence through 403/404; document it. No public User directory is generated.

## B5. Verifier rules and fixes

| ID | Rule | Trigger | Location | Fix behavior |
|---|---|---|---|---|
| TC-001 | AUTH-REQUIRED | Missing auth | endpoint keyword | Proposed diff inserting auth: required after resource |
| TC-002 | OWNERSHIP-CHECK | Invalid policy in B4 | offending policy keyword | Prompt explaining supported choices; never suggest unsupported User/public/create waiver |
| TC-003 | SENSITIVE-LEAK | Selected sensitive field lacks permitted exposure; any selected credential field | returns keyword | Prompt to project safe fields; ordinary sensitive data may be explicitly exposed; credentials never |
| TC-004 | MASS-ASSIGNMENT | id, ownership or credential field named in body | exact field token | Diff removing server-controlled field; re-check may then reveal invalid empty update shape |
| TC-005 | SECRET-SCOPE | Missing DB_URL or JWT_SECRET | secrets keyword, else first endpoint | Diff adding declaration(s), never values |

Needed secrets are exactly DB_URL and JWT_SECRET because templates use both. Extra declared env names are allowed but unused and do not claim active validation. Sort diagnostics by line, column, rule ID. Rule checked counts refer to eligible endpoints/secret references, not human security scores.

Diffs are computed against original normalized source and include baseSpecHash. One Apply action is one undoable edit; a mismatched hash/context refuses. If several diagnostics match --rule, CLI requires `--line` or an explicit `--all` batch. A batch computes one patch on the current source, not chained stale patches. Dry run changes nothing. Manual edits always re-check before build.

Use “Suggested restrictive default” for TC-001, not “one correct fix.” No silent public choice, no unclicked automatic edit. The CLI and UI share semantics and fixture cases for exact-context diff application. Plain messages and stable machine codes are required; punctuation changes alone should not break behavioral tests.

## B6. Code generation and runtime

Use reviewed Jinja2 templates, SQLAlchemy 2 async ORM, one AsyncSession per request, Pydantic v2 request/response models with from_attributes, and FastAPI lifespan. Validate identifiers before interpolation; query values remain bound parameters. No raw SQL/string-expression escape hatch. Reject extra request fields. Test injection-like text is stored as data and does not change query behavior.

JWT: fixed HS256 allowlist; require signed sub, exp, iat, iss and aud claims; verify issuer `trustc-local` and audience `trustc-api`; sub must parse as UUID and resolve to an existing User. Use at least 32 random bytes for the ephemeral test secret. Missing/malformed/expired/wrong-signature/wrong-issuer/wrong-audience/unknown-user tokens produce 401 with a sanitized response. This is the local demo identity contract, not an external identity-provider integration.

Owner assignment is from verified current_user.id on POST. Update uses only named body fields, never full model deserialization. List owner policy filters in the query. Explicit waivers remove only ownership restrictions, never required authentication. Unowned resources are labelled login-only, not owner-protected. Per-endpoint response schemas must preserve projections; one permissive resource-wide model must not leak into another route. For sensitive exposure, list exact fields in evidence. Unmarked sensitive business data cannot be automatically recognized.

Generated files: main.py, models.py, schemas.py, auth.py, db.py, routers/__init__.py, one router per resource with endpoints, requirements.txt, README.md and trustc-report.json. Include an output manifest/hash in the result. F2 has 8 Python files (including routers/__init__.py), 11 files total. Runtime requirements are exact resolved compatible versions from Stage 1. Generated README explains local environment configuration and that identity seeding is test-only.

Render to a fresh staging directory. Syntax-check all Python and validate paths before publishing. Refusal, invalid syntax, cancellation, timeout and generation failure leave existing output byte-identical. CLI refuses to replace a nonempty unrelated folder; `--replace` is permitted only for a folder with a verified TrustC manifest. Use sibling staging/backup, rollback on failure and recovery markers; never promise a universally atomic nonempty-directory swap. Server outputs are immutable per buildId and are published by the parent only after worker success.

Provenance comments come from IR spans. Scan rendered files for their structured markers and cross-check referenced source spans. User self-check points to the User.id declaration; owner check/set points to the ownership field. Query/route/auth point to relevant endpoint/source declarations. Generated comments aid traceability; comments themselves are not enforcement.

## B7. Evidence and honest claims

Build evidence contains compiler/template version, hash, exact endpoint policies, selected sensitive fields, rule results, declarations and known limits. Do not emit the absolute claim “0 sensitive fields sent back” when an explicit exposure exists. Do not claim every owned endpoint checks ownership when one is public. Show protected/waived/public counts from endpoint policies.

Structural restriction wording: “The supported IR has no raw-query operation,” “Generated secret references resolve through environment variables,” and “Every accepted input field has a supported type.” These apply to unmodified generated output and correct templates. Runtime observations are separately attributed to a matching build artifact. There is no numerical security score.

Known limits: one identity resource, no signup/login UI, RBAC, migrations, pagination, rate limiting or CSRF implementation, no arbitrary relationships, enum unsupported, no production deployment hardening claim. Local harness covers declared item access and selected response assertions; it does not establish complete business-policy correctness, exhaustive security or protection for hand-edited output.
