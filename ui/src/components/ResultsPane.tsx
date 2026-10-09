import React from 'react';
import { useWorkbenchStore } from '../state/workbenchStore';
import { DiagnosticsTab } from './DiagnosticsTab';
import { CodeTab } from './CodeTab';
import { TestsTab } from './TestsTab';
import { EvidenceTab } from './EvidenceTab';
import { AlertCircle, CheckCircle2, FileCode2, Crosshair, FileCheck } from 'lucide-react';

export const ResultsPane: React.FC = () => {
  const {
    activeTab,
    setActiveTab,
    checkResult,
    buildResult,
    attackResult,
  } = useWorkbenchStore();

  const violationCount = checkResult?.diagnostics?.length ?? 0;
  const fileCount = buildResult?.files?.length ?? 0;
  const testCount = attackResult?.total ?? 0;

  return (
    <section
      aria-label="Results and Invariant Inspection"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        backgroundColor: 'var(--color-panel)',
        overflow: 'hidden',
      }}
    >
      {/* Tab Navigation Header */}
      <div
        role="tablist"
        aria-label="Workbench Result Tabs"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          padding: '6px 12px 0 12px',
          backgroundColor: 'var(--color-raised)',
          borderBottom: '1px solid var(--color-border)',
          overflowX: 'auto',
          userSelect: 'none',
        }}
      >
        {/* Tab 1: Diagnostics */}
        <button
          role="tab"
          id="tab-diagnostics"
          aria-selected={activeTab === 'diagnostics'}
          aria-controls="panel-diagnostics"
          type="button"
          onClick={() => setActiveTab('diagnostics')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            borderTopLeftRadius: 'var(--radius-md)',
            borderTopRightRadius: 'var(--radius-md)',
            borderBottom: activeTab === 'diagnostics' ? '2px solid var(--color-teal)' : '2px solid transparent',
            backgroundColor: activeTab === 'diagnostics' ? 'var(--color-panel)' : 'transparent',
            color: activeTab === 'diagnostics' ? 'var(--color-teal)' : 'var(--color-text-secondary)',
            borderLeft: 'none',
            borderRight: 'none',
            borderTop: 'none',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          {violationCount > 0 ? (
            <AlertCircle size={15} color="var(--color-error)" />
          ) : checkResult?.ok ? (
            <CheckCircle2 size={15} color="var(--color-success)" />
          ) : null}
          <span>Diagnostics</span>
          {violationCount > 0 && (
            <span
              style={{
                fontSize: '11px',
                padding: '1px 6px',
                borderRadius: '10px',
                backgroundColor: 'rgba(255, 135, 149, 0.2)',
                color: 'var(--color-error)',
                fontWeight: 700,
              }}
            >
              {violationCount}
            </span>
          )}
        </button>

        {/* Tab 2: Generated Code */}
        <button
          role="tab"
          id="tab-code"
          aria-selected={activeTab === 'code'}
          aria-controls="panel-code"
          type="button"
          onClick={() => setActiveTab('code')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            borderTopLeftRadius: 'var(--radius-md)',
            borderTopRightRadius: 'var(--radius-md)',
            borderBottom: activeTab === 'code' ? '2px solid var(--color-teal)' : '2px solid transparent',
            backgroundColor: activeTab === 'code' ? 'var(--color-panel)' : 'transparent',
            color: activeTab === 'code' ? 'var(--color-teal)' : 'var(--color-text-secondary)',
            borderLeft: 'none',
            borderRight: 'none',
            borderTop: 'none',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <FileCode2 size={15} />
          <span>Generated code</span>
          {fileCount > 0 && (
            <span
              style={{
                fontSize: '11px',
                padding: '1px 6px',
                borderRadius: '10px',
                backgroundColor: 'var(--color-raised)',
                color: 'var(--color-text-primary)',
              }}
            >
              {fileCount}
            </span>
          )}
        </button>

        {/* Tab 3: Access Tests */}
        <button
          role="tab"
          id="tab-tests"
          aria-selected={activeTab === 'tests'}
          aria-controls="panel-tests"
          type="button"
          onClick={() => setActiveTab('tests')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            borderTopLeftRadius: 'var(--radius-md)',
            borderTopRightRadius: 'var(--radius-md)',
            borderBottom: activeTab === 'tests' ? '2px solid var(--color-teal)' : '2px solid transparent',
            backgroundColor: activeTab === 'tests' ? 'var(--color-panel)' : 'transparent',
            color: activeTab === 'tests' ? 'var(--color-teal)' : 'var(--color-text-secondary)',
            borderLeft: 'none',
            borderRight: 'none',
            borderTop: 'none',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <Crosshair size={15} />
          <span>Access tests</span>
          {testCount > 0 && (
            <span
              style={{
                fontSize: '11px',
                padding: '1px 6px',
                borderRadius: '10px',
                backgroundColor: 'var(--color-raised)',
                color: 'var(--color-text-primary)',
              }}
            >
              {testCount}
            </span>
          )}
        </button>

        {/* Tab 4: Build Evidence */}
        <button
          role="tab"
          id="tab-evidence"
          aria-selected={activeTab === 'evidence'}
          aria-controls="panel-evidence"
          type="button"
          onClick={() => setActiveTab('evidence')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 14px',
            borderTopLeftRadius: 'var(--radius-md)',
            borderTopRightRadius: 'var(--radius-md)',
            borderBottom: activeTab === 'evidence' ? '2px solid var(--color-teal)' : '2px solid transparent',
            backgroundColor: activeTab === 'evidence' ? 'var(--color-panel)' : 'transparent',
            color: activeTab === 'evidence' ? 'var(--color-teal)' : 'var(--color-text-secondary)',
            borderLeft: 'none',
            borderRight: 'none',
            borderTop: 'none',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <FileCheck size={15} />
          <span>Build evidence</span>
        </button>
      </div>

      {/* Tab Content Panels */}
      <div
        id={`panel-${activeTab}`}
        role="tabpanel"
        style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}
      >
        {activeTab === 'diagnostics' && <DiagnosticsTab />}
        {activeTab === 'code' && <CodeTab />}
        {activeTab === 'tests' && <TestsTab />}
        {activeTab === 'evidence' && <EvidenceTab />}
      </div>
    </section>
  );
};
