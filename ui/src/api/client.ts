import {
  ServerMeta,
  ExampleSpec,
  RuleDocResponse,
  CheckResult,
  RunAccepted,
  RunStatusResponse,
  RunEvent,
} from './types';
import {
  MOCK_META,
  MOCK_EXAMPLES,
  MOCK_RULE_DOCS,
  MOCK_CHECK_F1,
  MOCK_CHECK_F2,
  MOCK_BUILD_F2,
  MOCK_ATTACK_F2,
} from './mockData';

export type DataMode = 'live' | 'mock' | 'recorded';

export async function computeSpecHash(raw: string): Promise<string> {
  const normalized = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const encoder = new TextEncoder();
  const data = encoder.encode(normalized);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl;
  }

  async fetchMeta(mode: DataMode): Promise<ServerMeta> {
    if (mode === 'mock' || mode === 'recorded') {
      return MOCK_META;
    }
    const res = await fetch(`${this.baseUrl}/api/meta`);
    if (!res.ok) {
      throw new Error(`Failed to fetch server meta: ${res.statusText}`);
    }
    return res.json();
  }

  async fetchExamples(mode: DataMode): Promise<ExampleSpec[]> {
    if (mode === 'mock' || mode === 'recorded') {
      return MOCK_EXAMPLES;
    }
    const res = await fetch(`${this.baseUrl}/api/examples`);
    if (!res.ok) {
      throw new Error(`Failed to fetch examples: ${res.statusText}`);
    }
    return res.json();
  }

  async fetchRuleDoc(ruleId: string, mode: DataMode): Promise<RuleDocResponse> {
    if (mode === 'mock' || mode === 'recorded') {
      const doc = MOCK_RULE_DOCS[ruleId];
      if (!doc) throw new Error(`Unknown rule ${ruleId}`);
      return doc;
    }
    const res = await fetch(`${this.baseUrl}/api/rules/${ruleId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch rule ${ruleId}: ${res.statusText}`);
    }
    return res.json();
  }

  async checkSpec(spec: string, specVersion: number, mode: DataMode): Promise<CheckResult> {
    if (mode === 'mock' || mode === 'recorded') {
      const shash = await computeSpecHash(spec);
      if (spec.includes('endpoint GET /trips/{id}\n')) {
        // F4 syntax error mock
        return {
          schemaVersion: 2,
          specVersion,
          specHash: shash,
          command: 'check',
          ms: 4,
          kind: 'check',
          ok: false,
          exitCode: 2,
          specErrors: [
            {
              kind: 'syntax',
              code: 'SYNTAX_ERROR',
              message: "Syntax error: expected ':' after endpoint path",
              span: { line: 23, col: 25, endLine: 23, endCol: 25 },
              snippet: 'endpoint GET /trips/{id}',
            },
          ],
          diagnostics: [],
          rules: [],
          rulesRun: 0,
          endpoints: 0,
        };
      }
      if (spec.includes('Missing auth (TC-001)') || spec.includes('returns: User\n') || !spec.includes('auth: required\n  returns: Trip\n')) {
        return { ...MOCK_CHECK_F1, specHash: shash, specVersion };
      }
      return { ...MOCK_CHECK_F2, specHash: shash, specVersion };
    }

    const res = await fetch(`${this.baseUrl}/api/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec, specVersion }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `Check failed: ${res.statusText}`);
    }
    return res.json();
  }

  private mockRuns: Map<
    string,
    { kind: 'build' | 'attack'; specHash: string; specVersion: number; buildId: string }
  > = new Map();

  async buildApp(spec: string, specVersion: number, mode: DataMode): Promise<RunAccepted> {
    if (mode === 'mock' || mode === 'recorded') {
      const shash = await computeSpecHash(spec);
      const runId = `mock-build-run-${Date.now()}`;
      const buildId = `mock-build-${Date.now()}`;
      this.mockRuns.set(runId, {
        kind: 'build',
        specHash: shash,
        specVersion,
        buildId,
      });
      return {
        runId,
        specVersion,
        specHash: shash,
      };
    }

    const res = await fetch(`${this.baseUrl}/api/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec, specVersion, target: 'fastapi' }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `Build submission failed: ${res.statusText}`);
    }
    return res.json();
  }

  async attackApp(
    spec: string,
    specVersion: number,
    buildId: string,
    mode: DataMode
  ): Promise<RunAccepted> {
    if (mode === 'mock' || mode === 'recorded') {
      const shash = await computeSpecHash(spec);
      const runId = `mock-attack-run-${Date.now()}`;
      this.mockRuns.set(runId, {
        kind: 'attack',
        specHash: shash,
        specVersion,
        buildId,
      });
      return {
        runId,
        specVersion,
        specHash: shash,
      };
    }

    const res = await fetch(`${this.baseUrl}/api/attack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec, specVersion, buildId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `Attack submission failed: ${res.statusText}`);
    }
    return res.json();
  }

  async getRunStatus(runId: string, mode: DataMode): Promise<RunStatusResponse> {
    if (mode === 'mock' || mode === 'recorded') {
      const info = this.mockRuns.get(runId);
      if (runId.includes('build') || info?.kind === 'build') {
        const buildId = info?.buildId || 'mock-build-f2-8787';
        const specHash = info?.specHash || 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884';
        const specVersion = info?.specVersion ?? 0;
        return {
          runId,
          state: 'terminal',
          result: {
            ...MOCK_BUILD_F2,
            buildId,
            specHash,
            specVersion,
            evidence: {
              ...MOCK_BUILD_F2.evidence,
              buildId,
              specHash,
              specVersion,
            },
          },
        };
      }
      const buildId = info?.buildId || 'mock-build-f2-8787';
      const specHash = info?.specHash || 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884';
      const specVersion = info?.specVersion ?? 0;
      return {
        runId,
        state: 'terminal',
        result: {
          ...MOCK_ATTACK_F2,
          buildId,
          specHash,
          specVersion,
        },
      };
    }

    const res = await fetch(`${this.baseUrl}/api/runs/${runId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch run status: ${res.statusText}`);
    }
    return res.json();
  }

  async cancelRun(runId: string, mode: DataMode): Promise<void> {
    if (mode === 'mock' || mode === 'recorded') {
      return;
    }
    const res = await fetch(`${this.baseUrl}/api/runs/${runId}`, {
      method: 'DELETE',
    });
    if (!res.ok && res.status !== 404 && res.status !== 204 && res.status !== 202) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `Cancellation failed: ${res.statusText}`);
    }
  }

  subscribeRunEvents(
    runId: string,
    onEvent: (ev: RunEvent) => void,
    onDone: () => void,
    onError: (err: any) => void,
    mode: DataMode
  ): () => void {
    if (mode === 'mock' || mode === 'recorded') {
      const info = this.mockRuns.get(runId);
      const isBuild = runId.includes('build') || info?.kind === 'build';
      const timer = setTimeout(() => {
        const buildId = info?.buildId || 'mock-build-f2-8787';
        const specHash = info?.specHash || 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884';
        const specVersion = info?.specVersion ?? 0;
        const resultPayload = isBuild
          ? {
              ...MOCK_BUILD_F2,
              buildId,
              specHash,
              specVersion,
              evidence: {
                ...MOCK_BUILD_F2.evidence,
                buildId,
                specHash,
                specVersion,
              },
            }
          : {
              ...MOCK_ATTACK_F2,
              buildId,
              specHash,
              specVersion,
            };

        onEvent({
          schemaVersion: 2,
          runId,
          specVersion,
          specHash,
          seq: 1,
          payload: {
            type: 'result',
            result: resultPayload,
          },
        });
        onDone();
      }, 400);
      return () => clearTimeout(timer);
    }

    const seenSeqs = new Set<number>();
    let isClosed = false;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    const eventSource = new EventSource(`${this.baseUrl}/api/runs/${runId}/events`);

    const cleanup = () => {
      isClosed = true;
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
      eventSource.close();
    };

    eventSource.addEventListener('trustc', (e: MessageEvent) => {
      if (isClosed) return;
      try {
        const ev: RunEvent = JSON.parse(e.data);
        if (seenSeqs.has(ev.seq)) {
          return; // Deduplicate by seq
        }
        seenSeqs.add(ev.seq);
        onEvent(ev);
        if (ev.payload.type === 'result') {
          cleanup();
          onDone();
        }
      } catch (err) {
        console.error('Error parsing SSE event', err);
      }
    });

    eventSource.onerror = (err) => {
      if (isClosed) return;
      // Do not close immediately if reconnecting
      if (eventSource.readyState === EventSource.CLOSED) {
        // Fallback polling for terminal status if SSE connection closed prematurely
        if (!pollInterval) {
          pollInterval = setInterval(async () => {
            if (isClosed) return;
            try {
              const status = await this.getRunStatus(runId, mode);
              if (status.state === 'terminal') {
                cleanup();
                onDone();
              }
            } catch {
              cleanup();
              onError(err);
            }
          }, 1000);
        }
      }
    };

    return cleanup;
  }

  getZipDownloadUrl(buildId: string): string {
    return `${this.baseUrl}/api/builds/${buildId}/out.zip`;
  }
}

export const api = new ApiClient();
