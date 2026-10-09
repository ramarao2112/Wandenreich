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
  status: 'idle' | 'submitting' | 'running' | 'reconnecting' | 'cancelling' | 'terminal';
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
  isHashing: boolean;
  serverSessionId: string | null;
  dataMode: DataMode;
  resultOriginMode: DataMode | null;
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
  activeRunController: (() => void) | null;
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
  isHashing: false,
  serverSessionId: null,
  dataMode: 'live',
  resultOriginMode: null,
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
  activeRunController: null,

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
              resultOriginMode: null,
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
    const nextVersion = get().sourceVersion + 1;
    // Update source and version synchronously so edit order is never inverted
    set({
      source: newSource,
      sourceVersion: nextVersion,
      diffPreview: null,
      isHashing: true,
    });

    return computeSpecHash(newSource).then((newHash) => {
      // Guard: only publish hash if revision is still current
      if (get().sourceVersion === nextVersion) {
        set({
          sourceHash: newHash,
          isHashing: false,
        });
      }
    });
  },

  loadExample: async (exampleId: string) => {
    const { examples, source } = get();
    const ex = examples.find((e) => e.id.toLowerCase() === exampleId.toLowerCase());
    if (!ex) return;

    const nextVersion = get().sourceVersion + 1;
    set((state) => ({
      undoStack: source ? [...state.undoStack, source] : state.undoStack,
      source: ex.spec,
      sourceVersion: nextVersion,
      selectedExampleId: ex.id,
      selectedDiagnosticIndex: null,
      diffPreview: null,
      selectedSourceSpan: null,
      isHashing: true,
      announcement: `Loaded example ${ex.title}`,
    }));

    return computeSpecHash(ex.spec).then((newHash) => {
      if (get().sourceVersion === nextVersion) {
        set({
          sourceHash: newHash,
          isHashing: false,
        });
      }
    });
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
    const { source, sourceHash, undoStack, isHashing } = get();
    if (isHashing || sourceHash !== baseSpecHash) {
      set({ announcement: 'Cannot apply fix: source has changed since check or hash is calculating.' });
      return false;
    }

    const patched = applyUnifiedDiff(source, diff);
    const nextVersion = get().sourceVersion + 1;

    set({
      undoStack: [...undoStack, source],
      source: patched,
      sourceVersion: nextVersion,
      diffPreview: null,
      selectedDiagnosticIndex: null,
      isHashing: true,
      announcement: 'Fix applied to specification.',
    });

    const newHash = await computeSpecHash(patched);
    if (get().sourceVersion === nextVersion) {
      set({
        sourceHash: newHash,
        isHashing: false,
      });
      // Auto-run check to verify the applied fix
      await get().runCheck();
    }
    return true;
  },

  undo: async () => {
    const { undoStack } = get();
    if (undoStack.length === 0) return;

    const prevSource = undoStack[undoStack.length - 1];
    const newStack = undoStack.slice(0, -1);
    const nextVersion = get().sourceVersion + 1;

    set({
      undoStack: newStack,
      source: prevSource,
      sourceVersion: nextVersion,
      diffPreview: null,
      isHashing: true,
      announcement: 'Undid previous action.',
    });

    return computeSpecHash(prevSource).then((newHash) => {
      if (get().sourceVersion === nextVersion) {
        set({
          sourceHash: newHash,
          isHashing: false,
        });
      }
    });
  },

  runCheck: async () => {
    const { activeRun, source, sourceVersion, isHashing, dataMode } = get();
    if (activeRun.status !== 'idle') return;

    // Ensure hash is resolved before submission
    let currentHash = get().sourceHash;
    if (isHashing || !currentHash) {
      currentHash = await computeSpecHash(source);
      set({ sourceHash: currentHash, isHashing: false });
    }

    const t0 = performance.now();

    set({
      activeRun: {
        runId: null,
        kind: 'check',
        status: 'submitting',
        sourceSnapshot: source,
        sourceHashSnapshot: currentHash,
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
        checkHash: currentHash,
        resultOriginMode: dataMode,
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
    const { activeRun, source, sourceVersion, isHashing, dataMode } = get();
    if (activeRun.status !== 'idle') return;

    let currentHash = get().sourceHash;
    if (isHashing || !currentHash) {
      currentHash = await computeSpecHash(source);
      set({ sourceHash: currentHash, isHashing: false });
    }

    const t0 = performance.now();

    // Set submitting synchronously to prevent duplicate triggers
    set({
      activeTab: 'code',
      activeRun: {
        runId: null,
        kind: 'build',
        status: 'submitting',
        sourceSnapshot: source,
        sourceHashSnapshot: currentHash,
        sourceVersionSnapshot: sourceVersion,
        events: [],
      },
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
          sourceHashSnapshot: currentHash,
          sourceVersionSnapshot: sourceVersion,
          events: [],
        },
      });

      const unsub = api.subscribeRunEvents(
        runId,
        (ev) => {
          // Ignore if obsolete
          if (get().activeRun.runId !== runId) return;
          set((state) => ({
            activeRun: {
              ...state.activeRun,
              events: [...state.activeRun.events, ev],
            },
          }));
        },
        async () => {
          if (get().activeRun.runId !== runId) return;
          const status = await api.getRunStatus(runId, dataMode);
          const ms = Math.round(performance.now() - t0);

          if (status.result && 'files' in status.result) {
            const buildRes = status.result as BuildSuccess;
            set({
              buildResult: buildRes,
              buildHash: currentHash,
              buildId: buildRes.buildId,
              resultOriginMode: dataMode,
              selectedFile: buildRes.files[0]?.path || 'main.py',
              activeRunController: null,
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
              activeRunController: null,
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
          if (get().activeRun.runId !== runId) return;
          set({
            activeRunController: null,
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

      set({ activeRunController: unsub });
    } catch (err: any) {
      set({
        announcement: `Build failed to start: ${err.message}`,
        activeRunController: null,
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
    const { activeRun, source, sourceVersion, isHashing, buildId, dataMode } = get();
    if (activeRun.status !== 'idle' || !buildId) return;

    let currentHash = get().sourceHash;
    if (isHashing || !currentHash) {
      currentHash = await computeSpecHash(source);
      set({ sourceHash: currentHash, isHashing: false });
    }

    const t0 = performance.now();
    set({
      activeTab: 'tests',
      activeRun: {
        runId: null,
        kind: 'attack',
        status: 'submitting',
        sourceSnapshot: source,
        sourceHashSnapshot: currentHash,
        sourceVersionSnapshot: sourceVersion,
        events: [],
      },
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
          sourceHashSnapshot: currentHash,
          sourceVersionSnapshot: sourceVersion,
          events: [],
        },
      });

      const unsub = api.subscribeRunEvents(
        runId,
        (ev) => {
          if (get().activeRun.runId !== runId) return;
          set((state) => ({
            activeRun: {
              ...state.activeRun,
              events: [...state.activeRun.events, ev],
            },
          }));
        },
        async () => {
          if (get().activeRun.runId !== runId) return;
          const status = await api.getRunStatus(runId, dataMode);
          const ms = Math.round(performance.now() - t0);

          if (status.result && 'steps' in status.result) {
            const attackRes = status.result as AttackCompleted;
            const matched = attackRes.asExpected + attackRes.review;
            set({
              attackResult: attackRes,
              attackHash: currentHash,
              attackBuildId: buildId,
              resultOriginMode: dataMode,
              activeRunController: null,
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
              activeRunController: null,
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
          if (get().activeRun.runId !== runId) return;
          set({
            activeRunController: null,
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

      set({ activeRunController: unsub });
    } catch (err: any) {
      set({
        announcement: `Attack failed to start: ${err.message}`,
        activeRunController: null,
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
    const { activeRun, dataMode, activeRunController } = get();
    if (!activeRun.runId) {
      if (activeRun.status === 'submitting') {
        activeRunController?.();
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
          activeRunController: null,
          announcement: 'Submission cancelled.',
        });
      }
      return;
    }

    set((state) => ({
      activeRun: {
        ...state.activeRun,
        status: 'cancelling',
      },
      announcement: 'Cancelling active run...',
    }));

    try {
      await api.cancelRun(activeRun.runId, dataMode);
      set({
        announcement: 'Run cancelled by user.',
      });
    } catch (err: any) {
      set({
        announcement: `Failed to cancel run: ${err.message}`,
      });
    }
  },

  setDataMode: (mode: DataMode) => {
    const current = get().dataMode;
    if (current === mode) return;

    const controller = get().activeRunController;
    if (controller) {
      try {
        controller();
      } catch {
        // ignore
      }
    }

    // Per R03: Bind every result to its originating mode; on mode changes,
    // clear incompatible results and disable downstream actions.
    set({
      dataMode: mode,
      resultOriginMode: null,
      activeRunController: null,
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
      diffPreview: null,
      announcement: `Switched to ${mode} mode. Incompatible cached results cleared.`,
    });
  },
}));
