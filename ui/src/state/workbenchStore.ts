import { create } from 'zustand';
import {
  CheckResult,
  BuildSuccess,
  AttackCompleted,
  RunFailure,
  RunEvent,
  ServerMeta,
  ExampleSpec,
  Span,
} from '../api/types';
import { api, computeSpecHash, DataMode } from '../api/client';
import { applyUnifiedDiff } from '../utils/patch';

export type ResultTab = 'diagnostics' | 'code' | 'tests' | 'evidence';

export interface ActiveRunState {
  runId: string | null;
  kind: 'check' | 'build' | 'attack' | null;
  status: 'idle' | 'running' | 'cancelling' | 'terminal';
  sourceSnapshot: string | null;
  sourceHashSnapshot: string | null;
  sourceVersionSnapshot: number | null;
  events: RunEvent[];
}

export interface WorkbenchState {
  // Source & versioning
  source: string;
  sourceVersion: number;
  sourceHash: string;
  serverSessionId: string | null;
  dataMode: DataMode;
  isOffline: boolean;
  announcement: string | null;

  // View state
  activeTab: ResultTab;
  selectedDiagnosticIndex: number | null;
  selectedFile: string | null;
  selectedSourceSpan: Span | null;
  diffPreview: { diff: string; baseSpecHash: string; label: string } | null;
  undoStack: string[];

  // Catalog
  examples: ExampleSpec[];
  selectedExampleId: string;
  serverMeta: ServerMeta | null;

  // Active run & historical cached results
  activeRun: ActiveRunState;
  checkResult: CheckResult | null;
  checkHash: string | null;
  buildResult: BuildSuccess | null;
  buildHash: string | null;
  buildId: string | null;
  attackResult: AttackCompleted | null;
  attackHash: string | null;
  attackBuildId: string | null;
  executionFailure: RunFailure | null;

  lastAction: {
    command: string;
    exitCode?: number;
    durationMs?: number;
  } | null;

  // Actions
  initServer: () => Promise<void>;
  setSource: (newSource: string) => Promise<void>;
  loadExample: (exampleId: string) => Promise<void>;
  setActiveTab: (tab: ResultTab) => void;
  selectDiagnostic: (index: number | null) => void;
  selectFile: (filePath: string) => void;
  selectSourceSpan: (span: Span | null) => void;
  previewFix: (diff: string, baseSpecHash: string, label: string) => void;
  closeDiffPreview: () => void;
  applyFix: (diff: string, baseSpecHash: string) => Promise<boolean>;
  undo: () => Promise<void>;
  runCheck: () => Promise<void>;
  runBuild: () => Promise<void>;
  runAttack: () => Promise<void>;
  cancelActiveRun: () => Promise<void>;
  setDataMode: (mode: DataMode) => void;
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  source: '',
  sourceVersion: 0,
  sourceHash: '',
  serverSessionId: null,
  dataMode: 'live',
  isOffline: false,
  announcement: null,

  activeTab: 'diagnostics',
  selectedDiagnosticIndex: null,
  selectedFile: null,
  selectedSourceSpan: null,
  diffPreview: null,
  undoStack: [],

  examples: [],
  selectedExampleId: '',
  serverMeta: null,

  activeRun: {
    runId: null,
    kind: null,
    status: 'idle',
    sourceSnapshot: null,
    sourceHashSnapshot: null,
    sourceVersionSnapshot: null,
    events: [],
  },

  checkResult: null,
  checkHash: null,
  buildResult: null,
  buildHash: null,
  buildId: null,
  attackResult: null,
  attackHash: null,
  attackBuildId: null,
  executionFailure: null,

  lastAction: null,

  initServer: async () => {
    const { dataMode, serverSessionId } = get();
    try {
      const [meta, examples] = await Promise.all([
        api.fetchMeta(dataMode),
        api.fetchExamples(dataMode),
      ]);

      const prevSession = serverSessionId;
      const isRestart = prevSession && prevSession !== meta.sessionId;

      set({
        serverMeta: meta,
        serverSessionId: meta.sessionId,
        examples,
        isOffline: false,
        // On server restart, invalidate previous builds and runs per §2.5 / A-contracts
        ...(isRestart
          ? {
              buildResult: null,
              buildId: null,
              buildHash: null,
              attackResult: null,
              attackHash: null,
              attackBuildId: null,
              announcement: 'Server restarted: prior builds invalidated.',
            }
          : {}),
      });

      // Load initial example if source is empty
      if (!get().source && examples.length > 0) {
        await get().loadExample(examples[0].id);
      }
    } catch (err) {
      console.warn('Server initialization failed, falling back to mock capability', err);
      set({ isOffline: true, announcement: 'Server offline. Switched to offline mode.' });
      // In offline mode, populate from mock
      const [meta, examples] = await Promise.all([
        api.fetchMeta('mock'),
        api.fetchExamples('mock'),
      ]);
      set({
        serverMeta: meta,
        serverSessionId: meta.sessionId,
        examples,
      });
      if (!get().source && examples.length > 0) {
        await get().loadExample(examples[0].id);
      }
    }
  },

  setSource: async (newSource: string) => {
    const newHash = await computeSpecHash(newSource);
    set((state) => ({
      source: newSource,
      sourceVersion: state.sourceVersion + 1,
      sourceHash: newHash,
      // If user edits, clear active diff preview
      diffPreview: null,
    }));
  },

  loadExample: async (exampleId: string) => {
    const { examples, source } = get();
    const ex = examples.find((e) => e.id.toLowerCase() === exampleId.toLowerCase());
    if (!ex) return;

    const newHash = await computeSpecHash(ex.spec);
    set((state) => ({
      undoStack: source ? [...state.undoStack, source] : state.undoStack,
      source: ex.spec,
      sourceVersion: state.sourceVersion + 1,
      sourceHash: newHash,
      selectedExampleId: ex.id,
      selectedDiagnosticIndex: null,
      diffPreview: null,
      selectedSourceSpan: null,
      announcement: `Loaded example ${ex.title}`,
    }));
  },

  setActiveTab: (tab: ResultTab) => {
    set({ activeTab: tab });
  },

  selectDiagnostic: (index: number | null) => {
    const { checkResult } = get();
    const diag = index !== null && checkResult?.diagnostics ? checkResult.diagnostics[index] : null;
    set({
      selectedDiagnosticIndex: index,
      selectedSourceSpan: diag ? diag.span : null,
    });
  },

  selectFile: (filePath: string) => {
    set({ selectedFile: filePath, selectedSourceSpan: null });
  },

  selectSourceSpan: (span: Span | null) => {
    set({ selectedSourceSpan: span });
  },

  previewFix: (diff: string, baseSpecHash: string, label: string) => {
    set({ diffPreview: { diff, baseSpecHash, label } });
  },

  closeDiffPreview: () => {
    set({ diffPreview: null });
  },

  applyFix: async (diff: string, baseSpecHash: string) => {
    const { source, sourceHash, undoStack } = get();
    if (sourceHash !== baseSpecHash) {
      set({ announcement: 'Cannot apply fix: source has changed since check.' });
      return false;
    }

    const patched = applyUnifiedDiff(source, diff);
    const newHash = await computeSpecHash(patched);

    set((state) => ({
      undoStack: [...undoStack, source],
      source: patched,
      sourceVersion: state.sourceVersion + 1,
      sourceHash: newHash,
      diffPreview: null,
      selectedDiagnosticIndex: null,
      announcement: 'Fix applied to specification.',
    }));

    // Auto-run check to verify the applied fix
    await get().runCheck();
    return true;
  },

  undo: async () => {
    const { undoStack } = get();
    if (undoStack.length === 0) return;

    const prevSource = undoStack[undoStack.length - 1];
    const newStack = undoStack.slice(0, -1);
    const newHash = await computeSpecHash(prevSource);

    set((state) => ({
      undoStack: newStack,
      source: prevSource,
      sourceVersion: state.sourceVersion + 1,
      sourceHash: newHash,
      diffPreview: null,
      announcement: 'Undid previous action.',
    }));
  },

  runCheck: async () => {
    const { source, sourceVersion, sourceHash, dataMode } = get();
    const t0 = performance.now();

    set({
      activeRun: {
        runId: null,
        kind: 'check',
        status: 'running',
        sourceSnapshot: source,
        sourceHashSnapshot: sourceHash,
        sourceVersionSnapshot: sourceVersion,
        events: [],
      },
      activeTab: 'diagnostics',
      announcement: 'Checking specification...',
    });

    try {
      const result = await api.checkSpec(source, sourceVersion, dataMode);
      const ms = Math.round(performance.now() - t0);

      set({
        checkResult: result,
        checkHash: sourceHash,
        executionFailure: null,
        activeRun: {
          runId: null,
          kind: null,
          status: 'idle',
          sourceSnapshot: null,
          sourceHashSnapshot: null,
          sourceVersionSnapshot: null,
          events: [],
        },
        lastAction: {
          command: 'trustc check spec.trust',
          exitCode: result.exitCode,
          durationMs: ms,
        },
        selectedDiagnosticIndex: result.diagnostics.length > 0 ? 0 : null,
        selectedSourceSpan: result.diagnostics[0]?.span || result.specErrors[0]?.span || null,
        announcement: result.ok
          ? 'Check passed! All rules satisfied.'
          : `Check failed: ${result.diagnostics.length} diagnostic(s), ${result.specErrors.length} error(s).`,
      });
    } catch (err: any) {
      const ms = Math.round(performance.now() - t0);
      set({
        activeRun: {
          runId: null,
          kind: null,
          status: 'idle',
          sourceSnapshot: null,
          sourceHashSnapshot: null,
          sourceVersionSnapshot: null,
          events: [],
        },
        lastAction: {
          command: 'trustc check spec.trust',
          exitCode: 3,
          durationMs: ms,
        },
        announcement: `Check error: ${err.message}`,
      });
    }
  },

  runBuild: async () => {
    const { source, sourceVersion, sourceHash, dataMode } = get();
    const t0 = performance.now();

    set({
      activeTab: 'code',
      announcement: 'Submitting build job...',
    });

    try {
      const accepted = await api.buildApp(source, sourceVersion, dataMode);
      const runId = accepted.runId;

      set({
        activeRun: {
          runId,
          kind: 'build',
          status: 'running',
          sourceSnapshot: source,
          sourceHashSnapshot: sourceHash,
          sourceVersionSnapshot: sourceVersion,
          events: [],
        },
      });

      api.subscribeRunEvents(
        runId,
        (ev) => {
          set((state) => ({
            activeRun: {
              ...state.activeRun,
              events: [...state.activeRun.events, ev],
            },
          }));
        },
        async () => {
          // Terminal completion
          const status = await api.getRunStatus(runId, dataMode);
          const ms = Math.round(performance.now() - t0);

          if (status.result && 'files' in status.result) {
            const buildRes = status.result as BuildSuccess;
            set({
              buildResult: buildRes,
              buildHash: sourceHash,
              buildId: buildRes.buildId,
              selectedFile: buildRes.files[0]?.path || 'main.py',
              activeRun: {
                runId: null,
                kind: null,
                status: 'idle',
                sourceSnapshot: null,
                sourceHashSnapshot: null,
                sourceVersionSnapshot: null,
                events: [],
              },
              lastAction: {
                command: 'trustc build spec.trust -o ./out',
                exitCode: buildRes.exitCode,
                durationMs: ms,
              },
              announcement: `Build succeeded! Generated ${buildRes.files.length} files.`,
            });
          } else if (status.result && 'status' in status.result) {
            const fail = status.result as RunFailure;
            set({
              executionFailure: fail,
              activeRun: {
                runId: null,
                kind: null,
                status: 'idle',
                sourceSnapshot: null,
                sourceHashSnapshot: null,
                sourceVersionSnapshot: null,
                events: [],
              },
              lastAction: {
                command: 'trustc build spec.trust -o ./out',
                exitCode: fail.exitCode,
                durationMs: ms,
              },
              announcement: `Build refused: ${fail.status}`,
            });
          }
        },
        (err) => {
          set({
            activeRun: {
              runId: null,
              kind: null,
              status: 'idle',
              sourceSnapshot: null,
              sourceHashSnapshot: null,
              sourceVersionSnapshot: null,
              events: [],
            },
            announcement: `Build stream interrupted: ${err}`,
          });
        },
        dataMode
      );
    } catch (err: any) {
      set({
        announcement: `Build failed to start: ${err.message}`,
        activeRun: {
          runId: null,
          kind: null,
          status: 'idle',
          sourceSnapshot: null,
          sourceHashSnapshot: null,
          sourceVersionSnapshot: null,
          events: [],
        },
      });
    }
  },

  runAttack: async () => {
    const { source, sourceVersion, sourceHash, buildId, dataMode } = get();
    if (!buildId) return;

    const t0 = performance.now();
    set({
      activeTab: 'tests',
      announcement: 'Executing live access attacks...',
    });

    try {
      const accepted = await api.attackApp(source, sourceVersion, buildId, dataMode);
      const runId = accepted.runId;

      set({
        activeRun: {
          runId,
          kind: 'attack',
          status: 'running',
          sourceSnapshot: source,
          sourceHashSnapshot: sourceHash,
          sourceVersionSnapshot: sourceVersion,
          events: [],
        },
      });

      api.subscribeRunEvents(
        runId,
        (ev) => {
          set((state) => ({
            activeRun: {
              ...state.activeRun,
              events: [...state.activeRun.events, ev],
            },
          }));
        },
        async () => {
          const status = await api.getRunStatus(runId, dataMode);
          const ms = Math.round(performance.now() - t0);

          if (status.result && 'steps' in status.result) {
            const attackRes = status.result as AttackCompleted;
            const matched = attackRes.asExpected + attackRes.review;
            set({
              attackResult: attackRes,
              attackHash: sourceHash,
              attackBuildId: buildId,
              activeRun: {
                runId: null,
                kind: null,
                status: 'idle',
                sourceSnapshot: null,
                sourceHashSnapshot: null,
                sourceVersionSnapshot: null,
                events: [],
              },
              lastAction: {
                command: 'trustc attack spec.trust',
                exitCode: attackRes.exitCode,
                durationMs: ms,
              },
              announcement: `Access tests complete: ${matched} matched, ${attackRes.review} reviews, ${attackRes.unexpected} failed.`,
            });
          } else if (status.result && 'status' in status.result) {
            const fail = status.result as RunFailure;
            set({
              executionFailure: fail,
              activeRun: {
                runId: null,
                kind: null,
                status: 'idle',
                sourceSnapshot: null,
                sourceHashSnapshot: null,
                sourceVersionSnapshot: null,
                events: [],
              },
              lastAction: {
                command: 'trustc attack spec.trust',
                exitCode: fail.exitCode,
                durationMs: ms,
              },
              announcement: `Attack error: ${fail.status}`,
            });
          }
        },
        (err) => {
          set({
            activeRun: {
              runId: null,
              kind: null,
              status: 'idle',
              sourceSnapshot: null,
              sourceHashSnapshot: null,
              sourceVersionSnapshot: null,
              events: [],
            },
            announcement: `Attack stream interrupted: ${err}`,
          });
        },
        dataMode
      );
    } catch (err: any) {
      set({
        announcement: `Attack failed to start: ${err.message}`,
        activeRun: {
          runId: null,
          kind: null,
          status: 'idle',
          sourceSnapshot: null,
          sourceHashSnapshot: null,
          sourceVersionSnapshot: null,
          events: [],
        },
      });
    }
  },

  cancelActiveRun: async () => {
    const { activeRun, dataMode } = get();
    if (!activeRun.runId) return;

    set((state) => ({
      activeRun: {
        ...state.activeRun,
        status: 'cancelling',
      },
      announcement: 'Cancelling active run...',
    }));

    await api.cancelRun(activeRun.runId, dataMode);
  },

  setDataMode: (mode: DataMode) => {
    set({ dataMode: mode, announcement: `Switched to ${mode} mode.` });
  },
}));
