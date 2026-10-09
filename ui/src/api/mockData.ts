import {
  ServerMeta,
  ExampleSpec,
  RuleDocResponse,
  CheckResult,
  BuildSuccess,
  AttackCompleted,
} from './types';

export const MOCK_META: ServerMeta = {
  schemaVersion: 2,
  sessionId: 'mock-session-0000-0000-0000',
  version: '0.1.0',
  port: 8787,
  target: 'fastapi',
  rules: [
    { id: 'TC-001', name: 'AUTH-REQUIRED' },
    { id: 'TC-002', name: 'OWNERSHIP-CHECK' },
    { id: 'TC-003', name: 'SENSITIVE-LEAK' },
    { id: 'TC-004', name: 'MASS-ASSIGNMENT' },
    { id: 'TC-005', name: 'SECRET-SCOPE' },
  ],
};

export const MOCK_EXAMPLES: ExampleSpec[] = [
  {
    id: 'F1',
    title: 'Trip Planner (Flawed)',
    subtitle: 'Missing auth (TC-001) & sensitive leak (TC-003)',
    expectedCheck: 'fail',
    expectedReview: false,
    spec: `resource User:
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
  returns: Trip

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
`,
  },
  {
    id: 'F2',
    title: 'Trip Planner (Owner-protected)',
    subtitle: 'Owner-protected Trip access and self-only User access',
    expectedCheck: 'pass',
    expectedReview: false,
    spec: `resource User:
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
`,
  },
  {
    id: 'F3',
    title: 'Trip Planner (Ownership Waiver)',
    subtitle: 'Explicit waiver on PUT /trips/{id}/visibility',
    expectedCheck: 'pass',
    expectedReview: true,
    spec: `resource User:
  fields:
    id: uuid
    email: string
    password_hash: string [sensitive]

resource Trip:
  fields:
    id: uuid
    destination: string
    owner_id: uuid -> User.id
    is_public: bool

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

endpoint PUT /trips/{id}/visibility:
  resource: Trip
  auth: required
  authorize: public
  body: [is_public]
`,
  },
  {
    id: 'F4',
    title: 'Syntax Error Demo',
    subtitle: 'Syntax error at line 23 column 25',
    expectedCheck: 'fail',
    expectedReview: false,
    spec: `resource User:
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

endpoint GET /trips/{id}
  resource: Trip
  returns: Trip

endpoint GET /users/{id}:
  resource: User
  auth: required
  returns: User
`,
  },
];

export const MOCK_RULE_DOCS: Record<string, RuleDocResponse> = {
  'TC-001': {
    id: 'TC-001',
    name: 'AUTH-REQUIRED',
    checks: ['Explicit authentication declaration (auth: required | public) on every endpoint.'],
    flaw: "Missing explicit authentication decision ('auth: required' or 'auth: public').",
    fixType: 'diff',
    refused: 'endpoint GET /trips/{id}:\n  resource: Trip\n  returns: Trip',
    accepted: 'endpoint GET /trips/{id}:\n  resource: Trip\n  auth: required\n  returns: Trip',
  },
  'TC-002': {
    id: 'TC-002',
    name: 'OWNERSHIP-CHECK',
    checks: ['Owned resources must enforce owner or self checks, or provide explicit waiver.'],
    flaw: 'Endpoint accesses owned resource without owner-check statement or waiver.',
    fixType: 'diff',
    refused: 'endpoint PUT /trips/{id}:\n  resource: Trip\n  auth: required',
    accepted: 'endpoint PUT /trips/{id}:\n  resource: Trip\n  auth: required\n  authorize: public',
  },
};

export const MOCK_CHECK_F1: CheckResult = {
  schemaVersion: 2,
  specVersion: 0,
  specHash: '4e364036b90af9de7a8f883dc26dbd64068c08507928a4690b91c5d5ea22dc8a',
  command: 'check',
  ms: 12,
  kind: 'check',
  ok: false,
  exitCode: 1,
  rulesRun: 5,
  endpoints: 3,
  specErrors: [],
  diagnostics: [
    {
      ruleId: 'TC-001',
      ruleName: 'AUTH-REQUIRED',
      severity: 'error',
      span: { line: 23, col: 1, endLine: 23, endCol: 8 },
      location: 'endpoint GET /trips/{id}',
      endpoint: 'GET /trips/{id}',
      message: "Endpoint 'GET /trips/{id}' is missing an authentication declaration (auth: required | public).",
      why: 'Unauthenticated endpoints expose operations without verifying caller identity. By default, endpoints should require authentication unless explicitly declared public.',
      fix: {
        type: 'diff',
        baseSpecHash: '4e364036b90af9de7a8f883dc26dbd64068c08507928a4690b91c5d5ea22dc8a',
        diff: '--- a/spec.trust\n+++ b/spec.trust\n@@ -22,6 +22,7 @@\n \n endpoint GET /trips/{id}:\n   resource: Trip\n+  auth: required\n   returns: Trip\n \n endpoint GET /users/{id}:\n',
        label: 'Suggested restrictive default: require authentication',
      },
    },
    {
      ruleId: 'TC-003',
      ruleName: 'SENSITIVE-LEAK',
      severity: 'error',
      span: { line: 30, col: 3, endLine: 30, endCol: 10 },
      location: 'endpoint GET /users/{id}',
      endpoint: 'GET /users/{id}',
      message: "Endpoint 'GET /users/{id}' returns credential field(s) 'password_hash' in response.",
      why: 'Credential fields (password, password_hash, tokens, keys) must never be returned in API responses to prevent credential exposure.',
      fix: {
        type: 'prompt',
        text: "Narrow the response projection to exclude credentials: e.g. 'returns: User [id, email]'. Credential fields can never be returned, even with an expose declaration.",
      },
    },
  ],
  rules: [
    { ruleId: 'TC-001', ruleName: 'AUTH-REQUIRED', status: 'failed', checked: 3, violations: 1, summary: '1 endpoint(s) missing auth' },
    { ruleId: 'TC-002', ruleName: 'OWNERSHIP-CHECK', status: 'passed', checked: 2, violations: 0, summary: '2/2 endpoints enforce ownership' },
    { ruleId: 'TC-003', ruleName: 'SENSITIVE-LEAK', status: 'failed', checked: 3, violations: 1, summary: '1 endpoint(s) return credential field(s)' },
    { ruleId: 'TC-004', ruleName: 'MASS-ASSIGNMENT', status: 'passed', checked: 1, violations: 0, summary: '0 mass-assignment violations' },
    { ruleId: 'TC-005', ruleName: 'SECRET-SCOPE', status: 'passed', checked: 2, violations: 0, summary: 'All required secrets declared' },
  ],
};

export const MOCK_CHECK_F2: CheckResult = {
  schemaVersion: 2,
  specVersion: 0,
  specHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
  command: 'check',
  ms: 8,
  kind: 'check',
  ok: true,
  exitCode: 0,
  rulesRun: 5,
  endpoints: 3,
  specErrors: [],
  diagnostics: [],
  rules: [
    { ruleId: 'TC-001', ruleName: 'AUTH-REQUIRED', status: 'passed', checked: 3, violations: 0, summary: 'All endpoints require authentication' },
    { ruleId: 'TC-002', ruleName: 'OWNERSHIP-CHECK', status: 'passed', checked: 2, violations: 0, summary: 'All owned routes protected' },
    { ruleId: 'TC-003', ruleName: 'SENSITIVE-LEAK', status: 'passed', checked: 3, violations: 0, summary: 'Zero credentials exposed' },
    { ruleId: 'TC-004', ruleName: 'MASS-ASSIGNMENT', status: 'passed', checked: 1, violations: 0, summary: 'No client-writable owner keys' },
    { ruleId: 'TC-005', ruleName: 'SECRET-SCOPE', status: 'passed', checked: 2, violations: 0, summary: 'All required secrets declared' },
  ],
};

export const MOCK_BUILD_F2: BuildSuccess = {
  schemaVersion: 2,
  specVersion: 0,
  specHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
  command: 'build',
  ms: 180,
  kind: 'build',
  status: 'completed',
  exitCode: 0,
  buildId: 'mock-build-f2-8787',
  files: [
    {
      path: 'main.py',
      content: '# FastAPI application entrypoint\nfrom fastapi import FastAPI\nfrom router import router\n\napp = FastAPI(title="TrustC Generated Backend")\napp.include_router(router)\n',
      forced: [],
    },
    {
      path: 'router.py',
      content: '# Route definitions with generated security checks\nfrom fastapi import APIRouter, Depends, HTTPException\n\nrouter = APIRouter()\n',
      forced: [
        { line: 18, specSpan: { line: 17, col: 1, endLine: 21, endCol: 16 }, kind: 'route' },
        { line: 20, specSpan: { line: 18, col: 3, endLine: 18, endCol: 17 }, kind: 'auth' },
        { line: 42, specSpan: { line: 24, col: 3, endLine: 24, endCol: 17 }, kind: 'owner-check' },
        { line: 62, specSpan: { line: 29, col: 3, endLine: 29, endCol: 17 }, kind: 'self-check' },
      ],
    },
    {
      path: 'auth.py',
      content: '# JWT Authentication and token validation\nimport os\n\nJWT_SECRET = os.environ.get("JWT_SECRET", "mock-secret-at-least-32-bytes-long-here")\n',
      forced: [],
    },
    {
      path: 'models.py',
      content: '# SQLAlchemy models\nfrom sqlalchemy.orm import declarative_base\n\nBase = declarative_base()\n',
      forced: [],
    },
    {
      path: 'schemas.py',
      content: '# Pydantic schemas with response projections\nfrom pydantic import BaseModel\n',
      forced: [],
    },
  ],
  evidence: {
    schemaVersion: 2,
    buildId: 'mock-build-f2-8787',
    specHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
    specVersion: 0,
    compilerVersion: '0.1.0',
    templateVersion: 'fastapi-1.0',
    rules: [
      { ruleId: 'TC-001', ruleName: 'AUTH-REQUIRED', status: 'passed', checked: 3, violations: 0, summary: 'All endpoints require authentication' },
      { ruleId: 'TC-002', ruleName: 'OWNERSHIP-CHECK', status: 'passed', checked: 2, violations: 0, summary: 'All owned routes protected' },
      { ruleId: 'TC-003', ruleName: 'SENSITIVE-LEAK', status: 'passed', checked: 3, violations: 0, summary: 'Zero credentials exposed' },
      { ruleId: 'TC-004', ruleName: 'MASS-ASSIGNMENT', status: 'passed', checked: 1, violations: 0, summary: 'No client-writable owner keys' },
      { ruleId: 'TC-005', ruleName: 'SECRET-SCOPE', status: 'passed', checked: 2, violations: 0, summary: 'All required secrets declared' },
    ],
    endpointPolicies: [
      { endpoint: 'POST /trips', mode: 'owner', ownerWaived: false, sensitiveFields: [] },
      { endpoint: 'GET /trips/{id}', mode: 'owner', ownerWaived: false, sensitiveFields: [] },
      { endpoint: 'GET /users/{id}', mode: 'self', ownerWaived: false, sensitiveFields: [] },
    ],
    structuralRestrictions: ['JWT required on all non-public endpoints', 'Owner query filter enforced in data access layer'],
    declarations: [],
    limitations: ['In-memory SQLite test database', 'Mock JWT secret used for local testing'],
  },
};

export const MOCK_ATTACK_F2: AttackCompleted = {
  schemaVersion: 2,
  specVersion: 0,
  specHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
  command: 'attack spec.trust',
  ms: 1240,
  kind: 'attack',
  status: 'completed',
  exitCode: 0,
  buildId: 'mock-build-f2-8787',
  artifactHash: 'mock-artifact-hash-f2',
  steps: [
    {
      stepId: 'a0000001-0000-0000-0000-000000000001',
      endpoint: 'POST /trips',
      actor: 'owner',
      method: 'POST',
      path: '/trips',
      expect: 201,
      got: 201,
      outcome: 'as_expected',
      declarationIds: [],
      checks: [
        { name: 'status_code', expected: '201', actual: '201', passed: true },
        { name: 'response_projection', expected: 'id,destination,owner_id', actual: 'id,destination,owner_id', passed: true },
      ],
    },
    {
      stepId: 'a0000001-0000-0000-0000-000000000002',
      endpoint: 'GET /trips/{id}',
      actor: 'owner',
      method: 'GET',
      path: '/trips/mock-trip-id',
      expect: 200,
      got: 200,
      outcome: 'as_expected',
      declarationIds: [],
      checks: [
        { name: 'status_code', expected: '200', actual: '200', passed: true },
        { name: 'response_projection', expected: 'id,destination,owner_id', actual: 'id,destination,owner_id', passed: true },
      ],
    },
    {
      stepId: 'a0000001-0000-0000-0000-000000000003',
      endpoint: 'GET /trips/{id}',
      actor: 'second_user',
      method: 'GET',
      path: '/trips/mock-trip-id',
      expect: 403,
      got: 403,
      outcome: 'as_expected',
      declarationIds: [],
      checks: [
        { name: 'status_code', expected: '403', actual: '403', passed: true },
      ],
    },
    {
      stepId: 'a0000001-0000-0000-0000-000000000004',
      endpoint: 'GET /trips/{id}',
      actor: 'anonymous',
      method: 'GET',
      path: '/trips/mock-trip-id',
      expect: 401,
      got: 401,
      outcome: 'as_expected',
      declarationIds: [],
      checks: [
        { name: 'status_code', expected: '401', actual: '401', passed: true },
      ],
    },
    {
      stepId: 'a0000001-0000-0000-0000-000000000005',
      endpoint: 'GET /users/{id}',
      actor: 'owner',
      method: 'GET',
      path: '/users/mock-user-id',
      expect: 200,
      got: 200,
      outcome: 'as_expected',
      declarationIds: [],
      checks: [
        { name: 'status_code', expected: '200', actual: '200', passed: true },
        { name: 'response_projection', expected: 'id,email', actual: 'id,email', passed: true },
      ],
    },
    {
      stepId: 'a0000001-0000-0000-0000-000000000006',
      endpoint: 'GET /users/{id}',
      actor: 'second_user',
      method: 'GET',
      path: '/users/mock-user-id',
      expect: 403,
      got: 403,
      outcome: 'as_expected',
      declarationIds: [],
      checks: [
        { name: 'status_code', expected: '403', actual: '403', passed: true },
      ],
    },
  ],
  asExpected: 6,
  review: 0,
  unexpected: 0,
  total: 6,
  coverage: {
    testedEndpoints: ['POST /trips', 'GET /trips/{id}', 'GET /users/{id}'],
    excludedEndpoints: [],
  },
  declarationObservations: [],
};
