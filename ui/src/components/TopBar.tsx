import React from 'react';
import { useWorkbenchStore } from '../state/workbenchStore';
import { ShieldCheck, Play, Hammer, Crosshair, XOctagon, RefreshCw, Radio, RotateCcw } from 'lucide-react';

export const TopBar: React.FC = () => {
  const {
    source,
    sourceHash,
    undoStack,
    dataMode,
    setDataMode,
    isOffline,
    initServer,
    examples,
    selectedExampleId,
    loadExample,
    activeRun,
    checkResult,
    checkHash,
    buildResult,
    buildHash,
    attackResult,
    attackBuildId,
    buildId,
    runCheck,
    runBuild,
    runAttack,
    cancelActiveRun,
  } = useWorkbenchStore();

  const isRunning = activeRun.status === 'running' || activeRun.status === 'cancelling';

  // Check state
  const isCheckFresh = Boolean(checkResult && checkHash === sourceHash);
  const isCheckPassing = Boolean(isCheckFresh && checkResult?.ok);

  // Build state
  const isBuildFresh = Boolean(buildResult && buildHash === sourceHash);
  const isBuildPassing = Boolean(isBuildFresh && buildResult?.status === 'completed');

  // Next prominent action
  const nextProminentAction: 'check' | 'build' | 'attack' = !isCheckPassing
    ? 'check'
    : !isBuildPassing
    ? 'build'
    : 'attack';

  const handleExampleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    if (!id) return;
    if (undoStack.length > 0 && source.trim().length > 0) {
      const confirmReplace = window.confirm(
        'You have unsaved changes in spec.trust. Loading a new example will replace current edits (you can use Undo). Continue?'
      );
      if (!confirmReplace) return;
    }
    await loadExample(id);
  };

  // State guidance text per brief §5
  let workflowGuidance = 'Describe your API, then check its policies.';
  if (activeRun.status === 'cancelling') {
    workflowGuidance = 'Stopping the run and cleaning up…';
  } else if (activeRun.status === 'running') {
    workflowGuidance = `Running ${activeRun.kind}...`;
  } else if (!isCheckFresh && checkResult) {
    workflowGuidance = 'Earlier source revision. Check and build the current source to test it.';
  } else if (isCheckPassing && !isBuildPassing) {
    workflowGuidance = 'Specification checks passed. Ready to generate FastAPI backend.';
  } else if (isBuildPassing && !attackResult) {
    workflowGuidance = 'Backend generated. Execute multi-actor access harness.';
  } else if (attackResult && attackBuildId === buildId) {
    const matched = (attackResult.asExpected ?? 0) + (attackResult.review ?? 0);
    const reviews = attackResult.review ?? 0;
    const failed = attackResult.unexpected ?? 0;
    workflowGuidance = `${matched} matched expectations · ${reviews} policy review${reviews === 1 ? '' : 's'} · ${failed} failed`;
  }

  return (
    <header
      role="banner"
      style={{
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--color-panel)',
        borderBottom: '1px solid var(--color-border)',
      }}
    >
      {/* Top Application Bar (Row 1: Brand, Spec Identity, Example Picker, Mode) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '8px 16px',
          borderBottom: '1px solid rgba(43, 56, 75, 0.6)',
          minHeight: '44px',
        }}
      >
        {/* Brand & File identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '26px',
                height: '26px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--color-raised)',
                color: 'var(--color-teal)',
                border: '1px solid var(--color-border)',
              }}
            >
              <ShieldCheck size={16} />
            </div>
            <span style={{ fontWeight: 700, fontSize: '15px', letterSpacing: '0.02em', color: 'var(--color-text-primary)' }}>
              TrustC
            </span>
            <span
              style={{
                fontSize: '11px',
                padding: '1px 6px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'var(--color-raised)',
                color: 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
              }}
            >
              v2 compiler
            </span>
          </div>

          <div style={{ width: '1px', height: '20px', backgroundColor: 'var(--color-border)' }} />

          {/* Current File identity */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
              spec.trust
            </span>
            {sourceHash && (
              <span
                title={`Spec SHA-256: ${sourceHash}`}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  color: 'var(--color-text-secondary)',
                  backgroundColor: 'var(--color-canvas)',
                  padding: '1px 6px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--color-border)',
                }}
              >
                #{sourceHash.slice(0, 8)}
              </span>
            )}
          </div>

          {/* Example Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label htmlFor="example-select" style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
              Example:
            </label>
            <select
              id="example-select"
              value={selectedExampleId}
              onChange={handleExampleChange}
              aria-label="Select TrustSpec example"
              disabled={isRunning}
              style={{
                padding: '3px 8px',
                backgroundColor: 'var(--color-raised)',
                color: 'var(--color-text-primary)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                fontSize: '12px',
                cursor: isRunning ? 'not-allowed' : 'pointer',
              }}
            >
              {examples.length === 0 ? (
                <option value="">(Loading examples...)</option>
              ) : (
                examples.map((ex) => (
                  <option key={ex.id} value={ex.id}>
                    {ex.id.toUpperCase()}: {ex.title}
                  </option>
                ))
              )}
            </select>
          </div>
        </div>

        {/* Persistent Mode Label: Live / Mock / Offline */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isOffline && (
            <button
              type="button"
              onClick={() => initServer()}
              title="Click to attempt reconnecting to local compiler server"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 8px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'rgba(255, 135, 149, 0.15)',
                border: '1px solid var(--color-error)',
                color: 'var(--color-error)',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <RotateCcw size={11} />
              <span>Reconnect</span>
            </button>
          )}

          <button
            type="button"
            id="btn-mode-toggle"
            onClick={() => setDataMode(dataMode === 'live' ? 'mock' : 'live')}
            disabled={isRunning}
            title={
              dataMode === 'live'
                ? 'Running against Live compiler server. Click to toggle Mock mode.'
                : 'Running in Mock mode. Click to toggle Live server mode.'
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 10px',
              borderRadius: 'var(--radius-md)',
              backgroundColor:
                isOffline
                  ? 'rgba(255, 135, 149, 0.15)'
                  : dataMode === 'live'
                  ? 'rgba(135, 226, 175, 0.1)'
                  : 'rgba(243, 196, 126, 0.15)',
              border: `1px solid ${
                isOffline
                  ? 'var(--color-error)'
                  : dataMode === 'live'
                  ? 'var(--color-success)'
                  : 'var(--color-review)'
              }`,
              color:
                isOffline
                  ? 'var(--color-error)'
                  : dataMode === 'live'
                  ? 'var(--color-success)'
                  : 'var(--color-review)',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <Radio size={12} />
            <span>
              {isOffline ? 'Server Offline' : dataMode === 'live' ? 'Live Server' : 'Mock Mode'}
            </span>
          </button>
        </div>
      </div>

      {/* Workflow Row (Row 2: Check, Build, Test Access, Cancel, State Guidance) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '8px 16px',
          minHeight: '44px',
          backgroundColor: 'rgba(18, 26, 39, 0.7)',
        }}
      >
        {/* Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {/* Check Button */}
          <button
            type="button"
            id="btn-action-check"
            onClick={() => runCheck()}
            disabled={isRunning}
            aria-disabled={isRunning}
            title="Compile and verify security invariants (TC-001 to TC-005) [Ctrl+Enter]"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: 'var(--radius-md)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: isRunning ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s ease',
              ...(nextProminentAction === 'check'
                ? {
                    backgroundColor: 'var(--color-teal)',
                    color: 'var(--color-dark-ink)',
                    border: '1px solid var(--color-teal)',
                    boxShadow: '0 0 10px rgba(99, 223, 208, 0.3)',
                  }
                : {
                    backgroundColor: 'var(--color-raised)',
                    color: 'var(--color-text-primary)',
                    border: '1px solid var(--color-border)',
                  }),
            }}
          >
            {activeRun.kind === 'check' && isRunning ? (
              <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} />
            ) : (
              <Play size={14} />
            )}
            <span>Check</span>
          </button>

          {/* Build Button */}
          <button
            type="button"
            id="btn-action-build"
            onClick={() => runBuild()}
            disabled={isRunning || !isCheckPassing}
            aria-disabled={isRunning || !isCheckPassing}
            title={
              !isCheckPassing
                ? 'Check must pass cleanly before building code'
                : 'Generate secure FastAPI backend code and manifest'
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: 'var(--radius-md)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: isRunning || !isCheckPassing ? 'not-allowed' : 'pointer',
              opacity: !isCheckPassing ? 0.45 : 1,
              transition: 'all 0.15s ease',
              ...(nextProminentAction === 'build' && isCheckPassing
                ? {
                    backgroundColor: 'var(--color-teal)',
                    color: 'var(--color-dark-ink)',
                    border: '1px solid var(--color-teal)',
                    boxShadow: '0 0 10px rgba(99, 223, 208, 0.3)',
                  }
                : {
                    backgroundColor: 'var(--color-raised)',
                    color: 'var(--color-text-primary)',
                    border: '1px solid var(--color-border)',
                  }),
            }}
          >
            {activeRun.kind === 'build' && isRunning ? (
              <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} />
            ) : (
              <Hammer size={14} />
            )}
            <span>Build</span>
          </button>

          {/* Test Access Button */}
          <button
            type="button"
            id="btn-action-test-access"
            onClick={() => runAttack()}
            disabled={isRunning || !isBuildPassing}
            aria-disabled={isRunning || !isBuildPassing}
            title={
              !isBuildPassing
                ? 'Requires a matching successful build before running access tests'
                : 'Execute multi-actor security harness (owner, second_user, anonymous)'
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: 'var(--radius-md)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: isRunning || !isBuildPassing ? 'not-allowed' : 'pointer',
              opacity: !isBuildPassing ? 0.45 : 1,
              transition: 'all 0.15s ease',
              ...(nextProminentAction === 'attack' && isBuildPassing
                ? {
                    backgroundColor: 'var(--color-teal)',
                    color: 'var(--color-dark-ink)',
                    border: '1px solid var(--color-teal)',
                    boxShadow: '0 0 10px rgba(99, 223, 208, 0.3)',
                  }
                : {
                    backgroundColor: 'var(--color-raised)',
                    color: 'var(--color-text-primary)',
                    border: '1px solid var(--color-border)',
                  }),
            }}
          >
            {activeRun.kind === 'attack' && isRunning ? (
              <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} />
            ) : (
              <Crosshair size={14} />
            )}
            <span>Test access</span>
          </button>

          {/* Cancel Button */}
          {isRunning && (
            <button
              type="button"
              id="btn-action-cancel"
              onClick={() => cancelActiveRun()}
              title="Cancel current running job [Esc]"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'rgba(255, 135, 149, 0.15)',
                color: 'var(--color-error)',
                border: '1px solid var(--color-error)',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <XOctagon size={14} />
              <span>{activeRun.status === 'cancelling' ? 'Cancelling...' : 'Cancel'}</span>
            </button>
          )}
        </div>

        {/* Workflow Guidance Text */}
        <div
          id="workflow-status-guidance"
          style={{
            fontSize: '13px',
            color: 'var(--color-text-secondary)',
            fontFamily: 'var(--font-sans)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <span>{workflowGuidance}</span>
        </div>
      </div>
    </header>
  );
};
