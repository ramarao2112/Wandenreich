import React, { useState } from 'react';
import { useWorkbenchStore } from '../state/workbenchStore';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  Check,
  BookOpen,
} from 'lucide-react';

export const DiagnosticsTab: React.FC = () => {
  const {
    checkResult,
    checkHash,
    sourceHash,
    activeRun,
    previewFix,
    applyFix,
    selectDiagnostic,
    selectedDiagnosticIndex,
  } = useWorkbenchStore();

  const [expandedRules, setExpandedRules] = useState<Record<string, boolean>>({});

  const toggleRuleExpand = (ruleId: string) => {
    setExpandedRules((prev) => ({ ...prev, [ruleId]: !prev[ruleId] }));
  };

  const isStale = Boolean(checkResult && checkHash && checkHash !== sourceHash);
  const isRunning = activeRun.status === 'running' && activeRun.kind === 'check';

  // If no check run yet
  if (!checkResult && !isRunning) {
    return (
      <div
        style={{
          padding: '32px 24px',
          textAlign: 'center',
          color: 'var(--color-text-secondary)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
        }}
      >
        <BookOpen size={36} color="var(--color-border)" />
        <h3 style={{ fontSize: '16px', color: 'var(--color-text-primary)', fontWeight: 600 }}>
          Describe your API, then check its policies.
        </h3>
        <p style={{ maxWidth: '420px', fontSize: '13px', lineHeight: '1.6' }}>
          Click <strong>Check</strong> in the workflow bar (or press <strong>Ctrl+Enter</strong>) to parse the specification and verify the 5 security rules (TC-001 through TC-005).
        </p>
      </div>
    );
  }

  if (isRunning) {
    return (
      <div
        style={{
          padding: '40px 24px',
          textAlign: 'center',
          color: 'var(--color-text-secondary)',
        }}
      >
        <div style={{ fontSize: '15px', color: 'var(--color-teal)', fontWeight: 600 }}>
          Running security checks...
        </div>
      </div>
    );
  }

  if (!checkResult) return null;

  // Spec parse error handling
  if (checkResult.specErrors && checkResult.specErrors.length > 0) {
    return (
      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div
          style={{
            backgroundColor: 'rgba(255, 135, 149, 0.1)',
            border: '1px solid var(--color-error)',
            borderRadius: 'var(--radius-lg)',
            padding: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-error)' }}>
            <AlertCircle size={20} />
            <h3 style={{ fontSize: '15px', fontWeight: 600 }}>Specification Parse Error</h3>
          </div>
          {checkResult.specErrors.map((err, i) => (
            <div key={i} style={{ marginTop: '12px' }}>
              <p style={{ fontSize: '13px', color: 'var(--color-text-primary)' }}>{err.message}</p>
              <div
                style={{
                  marginTop: '6px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  color: 'var(--color-text-secondary)',
                }}
              >
                Line {err.span.line}, Column {err.span.col} ({err.kind})
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const diagnostics = checkResult.diagnostics || [];
  const rules = checkResult.rules || [];
  const passingCount = rules.filter((r) => r.status === 'passed').length;
  const violationCount = diagnostics.length;

  return (
    <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Staleness Notice */}
      {isStale && (
        <div
          role="status"
          style={{
            padding: '10px 14px',
            backgroundColor: 'rgba(243, 196, 126, 0.12)',
            border: '1px solid var(--color-review)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--color-review)',
            fontSize: '13px',
          }}
        >
          <strong>Notice:</strong> Earlier source revision. Check and build the current source to test it.
        </div>
      )}

      {/* Primary Result Headline */}
      <div>
        {violationCount === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <CheckCircle2 size={24} color="var(--color-success)" />
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-success)' }}>
                Specification checks passed.
              </h2>
              <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                5 of 5 security rules satisfied. Specification is ready to build.
              </p>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
            <AlertCircle size={24} color="var(--color-error)" style={{ marginTop: '2px' }} />
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                {violationCount} Actionable Security {violationCount === 1 ? 'Issue' : 'Issues'} Found
              </h2>
              <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                Resolve the diagnostic issues below before building code.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Actionable Diagnostics List */}
      {diagnostics.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Actionable Issues ({diagnostics.length})
          </h3>
          {diagnostics.map((diag, index) => {
            const isSelected = selectedDiagnosticIndex === index;
            return (
              <div
                key={index}
                style={{
                  backgroundColor: isSelected ? 'var(--color-raised)' : 'var(--color-panel)',
                  border: `1px solid ${isSelected ? 'var(--color-teal)' : 'var(--color-border)'}`,
                  borderRadius: 'var(--radius-lg)',
                  padding: '14px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                  transition: 'border-color 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: diag.severity === 'error' ? 'rgba(255, 135, 149, 0.15)' : 'rgba(243, 196, 126, 0.15)',
                        color: diag.severity === 'error' ? 'var(--color-error)' : 'var(--color-review)',
                        fontWeight: 700,
                        fontSize: '12px',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {diag.ruleId}
                    </span>
                    <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary)' }}>
                      {diag.ruleName}
                    </span>
                    <button
                      type="button"
                      onClick={() => selectDiagnostic(index)}
                      title="Jump to source position in editor"
                      style={{
                        fontSize: '12px',
                        color: 'var(--color-teal)',
                        fontFamily: 'var(--font-mono)',
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        textDecoration: 'underline',
                        padding: 0,
                      }}
                    >
                      {diag.location || `Line ${diag.span.line}:${diag.span.col}`}
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={() => selectDiagnostic(isSelected ? null : index)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--color-text-secondary)',
                      cursor: 'pointer',
                      fontSize: '12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <span>{isSelected ? 'Collapse' : 'Inspect'}</span>
                    {isSelected ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                </div>

                <p style={{ fontSize: '13px', color: 'var(--color-text-primary)', lineHeight: '1.5' }}>
                  {diag.message}
                </p>

                {/* Explanation */}
                {diag.why && (
                  <div
                    style={{
                      fontSize: '12px',
                      color: 'var(--color-text-secondary)',
                      backgroundColor: 'var(--color-canvas)',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-sm)',
                      borderLeft: '3px solid var(--color-teal)',
                    }}
                  >
                    <strong>Security context:</strong> {diag.why}
                  </div>
                )}

                {/* Fix Actions */}
                {diag.fix && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '8px',
                      marginTop: '4px',
                      paddingTop: '8px',
                      borderTop: '1px solid var(--color-border)',
                    }}
                  >
                    {diag.fix.type === 'diff' ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '12px', color: 'var(--color-teal)', fontWeight: 600 }}>
                          {diag.fix.label ? `Suggested restrictive default: ${diag.fix.label}` : 'Suggested restrictive default'}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            if (diag.fix && diag.fix.type === 'diff') {
                              previewFix(diag.fix.diff, diag.fix.baseSpecHash, diag.fix.label);
                            }
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '4px 10px',
                            backgroundColor: 'var(--color-raised)',
                            color: 'var(--color-text-primary)',
                            border: '1px solid var(--color-border)',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '12px',
                            cursor: 'pointer',
                          }}
                        >
                          <Eye size={13} />
                          <span>Preview fix</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (diag.fix && diag.fix.type === 'diff') {
                              applyFix(diag.fix.diff, diag.fix.baseSpecHash);
                            }
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '4px 10px',
                            backgroundColor: 'var(--color-teal)',
                            color: 'var(--color-dark-ink)',
                            border: 'none',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '12px',
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          <Check size={13} />
                          <span>Apply fix</span>
                        </button>
                      </div>
                    ) : (
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', fontStyle: 'italic' }}>
                        💡 Manual resolution needed: {diag.fix.text}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Rules Breakdown Checklist */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
          Compiler Rules ({passingCount}/{rules.length} Passing)
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {rules.map((rule) => {
            const isExpanded = Boolean(expandedRules[rule.ruleId]);
            const isPassed = rule.status === 'passed';
            return (
              <div
                key={rule.ruleId}
                style={{
                  backgroundColor: 'var(--color-panel)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '10px 14px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    cursor: 'pointer',
                  }}
                  onClick={() => toggleRuleExpand(rule.ruleId)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {isPassed ? (
                      <CheckCircle2 size={16} color="var(--color-success)" />
                    ) : (
                      <AlertCircle size={16} color="var(--color-error)" />
                    )}
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600 }}>
                      {rule.ruleId}
                    </span>
                    <span style={{ fontSize: '13px', color: 'var(--color-text-primary)' }}>
                      {rule.ruleName}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span
                      style={{
                        fontSize: '12px',
                        color: isPassed ? 'var(--color-success)' : 'var(--color-error)',
                      }}
                    >
                      {rule.summary}
                    </span>
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </div>
                </div>

                {isExpanded && (
                  <div
                    style={{
                      marginTop: '8px',
                      paddingTop: '8px',
                      borderTop: '1px solid var(--color-border)',
                      fontSize: '12px',
                      color: 'var(--color-text-secondary)',
                    }}
                  >
                    <div>Checked: {rule.checked} endpoints / declarations</div>
                    <div>Violations: {rule.violations}</div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
