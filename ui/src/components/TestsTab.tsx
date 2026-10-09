import React, { useState } from 'react';
import { useWorkbenchStore } from '../state/workbenchStore';
import {
  Crosshair,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Terminal,
  Shield,
  User,
  Users,
  EyeOff,
} from 'lucide-react';
import { Actor, AttackStep } from '../api/types';

export const TestsTab: React.FC = () => {
  const {
    attackResult,
    attackHash,
    attackBuildId,
    buildId,
    sourceHash,
    activeRun,
  } = useWorkbenchStore();

  const [showLogs, setShowLogs] = useState(false);
  const [expandedEndpoints, setExpandedEndpoints] = useState<Record<string, boolean>>({});

  const toggleEndpointExpand = (endpoint: string) => {
    setExpandedEndpoints((prev) => ({ ...prev, [endpoint]: !prev[endpoint] }));
  };

  const isStale = Boolean(
    attackResult && (attackHash !== sourceHash || attackBuildId !== buildId)
  );
  const isRunning = activeRun.status === 'running' && activeRun.kind === 'attack';

  if (!attackResult && !isRunning) {
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
        <Crosshair size={36} color="var(--color-border)" />
        <h3 style={{ fontSize: '16px', color: 'var(--color-text-primary)', fontWeight: 600 }}>
          No Access Tests Executed
        </h3>
        <p style={{ maxWidth: '440px', fontSize: '13px', lineHeight: '1.6' }}>
          Once a clean build is generated, click <strong>Test access</strong> to run the automated security harness across actor roles (owner, second_user, anonymous) and verify resource isolation.
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
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
        }}
      >
        <div style={{ fontSize: '15px', color: 'var(--color-teal)', fontWeight: 600 }}>
          Executing multi-actor access harness...
        </div>
        <p style={{ fontSize: '13px' }}>
          Simulating requests from owner, second_user, and anonymous callers...
        </p>
      </div>
    );
  }

  if (!attackResult) return null;

  // Derived display counts per D-ui-design-addendum:
  // matched = asExpected + review; review = review; failed = unexpected
  const asExpected = attackResult.asExpected ?? 0;
  const review = attackResult.review ?? 0;
  const unexpected = attackResult.unexpected ?? 0;
  const matched = asExpected + review;

  const isCoverageEmpty = (attackResult.total ?? 0) === 0 || (attackResult.steps?.length ?? 0) === 0;

  // Concrete headline based on result per brief §5
  const headline = isCoverageEmpty
    ? 'No eligible endpoints tested.'
    : unexpected > 0
    ? 'Contradiction detected: Access policy violated under test.'
    : review > 0
    ? 'Policy review: Access granted under declared exception.'
    : 'Other users were blocked. The owner received access.';

  // Group steps by endpoint
  const stepsByEndpoint = (attackResult.steps || []).reduce<Record<string, AttackStep[]>>(
    (acc, step) => {
      if (!acc[step.endpoint]) acc[step.endpoint] = [];
      acc[step.endpoint].push(step);
      return acc;
    },
    {}
  );

  const getActorIcon = (actor: Actor) => {
    switch (actor) {
      case 'owner':
        return <User size={14} color="var(--color-success)" />;
      case 'second_user':
        return <Users size={14} color="var(--color-review)" />;
      case 'anonymous':
        return <EyeOff size={14} color="var(--color-text-secondary)" />;
    }
  };

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

      {/* Outcome Headline & Concrete Summary */}
      <div>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
          {isCoverageEmpty ? (
            <AlertTriangle size={24} color="var(--color-text-secondary)" style={{ marginTop: '2px' }} />
          ) : unexpected > 0 ? (
            <XCircle size={24} color="var(--color-error)" style={{ marginTop: '2px' }} />
          ) : review > 0 ? (
            <AlertTriangle size={24} color="var(--color-review)" style={{ marginTop: '2px' }} />
          ) : (
            <CheckCircle2 size={24} color="var(--color-success)" style={{ marginTop: '2px' }} />
          )}
          <div>
            <h2
              style={{
                fontSize: '20px',
                fontWeight: 700,
                color: isCoverageEmpty
                  ? 'var(--color-text-primary)'
                  : unexpected > 0
                  ? 'var(--color-error)'
                  : review > 0
                  ? 'var(--color-review)'
                  : 'var(--color-success)',
              }}
            >
              {headline}
            </h2>
            {isCoverageEmpty ? (
              <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                No endpoints in the specification met the criteria for multi-actor access simulation.
              </p>
            ) : (
              <p
                style={{
                  fontSize: '13px',
                  color: 'var(--color-text-primary)',
                  marginTop: '4px',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                <strong>{matched} matched expectations</strong> ·{' '}
                <span style={{ color: review > 0 ? 'var(--color-review)' : 'var(--color-text-secondary)' }}>
                  {review} policy {review === 1 ? 'review' : 'reviews'}
                </span>{' '}
                ·{' '}
                <span style={{ color: unexpected > 0 ? 'var(--color-error)' : 'var(--color-text-secondary)' }}>
                  {unexpected} failed
                </span>
              </p>
            )}
            {review > 0 && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '8px 12px',
                  backgroundColor: 'rgba(243, 196, 126, 0.12)',
                  border: '1px solid var(--color-review)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  color: 'var(--color-review)',
                  fontWeight: 500,
                }}
              >
                <strong>Policy review:</strong> Another signed-in user was allowed by your ownership waiver. Review whether that is intended.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Grouped Endpoint Test Rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
          Endpoints Tested ({Object.keys(stepsByEndpoint).length})
        </h3>

        {Object.entries(stepsByEndpoint).map(([endpoint, steps]) => {
          const isExpanded = expandedEndpoints[endpoint] !== false; // expanded by default
          const hasFailures = steps.some((s) => s.outcome === 'unexpected');
          const hasReviews = steps.some((s) => s.outcome === 'review');

          return (
            <div
              key={endpoint}
              style={{
                backgroundColor: 'var(--color-panel)',
                border: `1px solid ${
                  hasFailures
                    ? 'var(--color-error)'
                    : hasReviews
                    ? 'var(--color-review)'
                    : 'var(--color-border)'
                }`,
                borderRadius: 'var(--radius-lg)',
                padding: '14px 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
              }}
            >
              {/* Endpoint Header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                }}
                onClick={() => toggleEndpointExpand(endpoint)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Shield size={16} color="var(--color-teal)" />
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '14px',
                      fontWeight: 700,
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    {endpoint}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                    ({steps.length} actor checks)
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {hasFailures ? (
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'rgba(255, 135, 149, 0.15)',
                        color: 'var(--color-error)',
                        fontWeight: 600,
                      }}
                    >
                      Failed
                    </span>
                  ) : hasReviews ? (
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'rgba(243, 196, 126, 0.15)',
                        color: 'var(--color-review)',
                        fontWeight: 600,
                      }}
                    >
                      Review
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'rgba(135, 226, 175, 0.15)',
                        color: 'var(--color-success)',
                        fontWeight: 600,
                      }}
                    >
                      Protected
                    </span>
                  )}
                  {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </div>
              </div>

              {/* Actor Rows */}
              {isExpanded && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {steps.map((step) => {
                    const isPassed = step.outcome === 'as_expected';
                    const isReview = step.outcome === 'review';
                    const statusColor = isPassed
                      ? 'var(--color-success)'
                      : isReview
                      ? 'var(--color-review)'
                      : 'var(--color-error)';

                    return (
                      <div
                        key={step.stepId}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          flexWrap: 'wrap',
                          gap: '12px',
                          padding: '8px 12px',
                          backgroundColor: 'var(--color-raised)',
                          borderRadius: 'var(--radius-md)',
                          fontSize: '13px',
                        }}
                      >
                        {/* Actor identity & method */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {getActorIcon(step.actor)}
                          <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>
                            {step.actor}
                          </span>
                          <span
                            style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: '11px',
                              color: 'var(--color-text-secondary)',
                            }}
                          >
                            {step.method} {step.path}
                          </span>
                        </div>

                        {/* Status assertion */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                            <span>Expected </span>
                            <strong>{step.expect}</strong>
                            <span> · Got </span>
                            <strong style={{ color: statusColor }}>{step.got ?? 'null'}</strong>
                          </div>

                          <span
                            style={{
                              fontSize: '11px',
                              padding: '2px 8px',
                              borderRadius: 'var(--radius-sm)',
                              backgroundColor: isPassed
                                ? 'rgba(135, 226, 175, 0.15)'
                                : isReview
                                ? 'rgba(243, 196, 126, 0.15)'
                                : 'rgba(255, 135, 149, 0.15)',
                              color: statusColor,
                              fontWeight: 600,
                            }}
                          >
                            {step.outcome === 'as_expected'
                              ? 'As expected'
                              : step.outcome === 'review'
                              ? 'Policy review'
                              : 'Contradiction'}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Expandable Logs Drawer */}
      <div style={{ marginTop: '8px' }}>
        <button
          type="button"
          onClick={() => setShowLogs(!showLogs)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'none',
            border: 'none',
            color: 'var(--color-text-secondary)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            padding: '4px 0',
          }}
        >
          <Terminal size={15} />
          <span>{showLogs ? 'Hide Execution Logs' : 'Show Execution Logs'}</span>
          {showLogs ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        {showLogs && (
          <div
            style={{
              marginTop: '8px',
              padding: '12px 14px',
              backgroundColor: 'var(--color-canvas)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              maxHeight: '180px',
              overflowY: 'auto',
              color: 'var(--color-text-primary)',
            }}
          >
            {activeRun.events.length > 0 ? (
              activeRun.events.map((evt, idx) => (
                <div key={idx} style={{ padding: '2px 0' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>[{evt.seq}] </span>
                  {evt.payload.type === 'log' ? (
                    <span>{evt.payload.log.text}</span>
                  ) : evt.payload.type === 'phase' ? (
                    <span style={{ color: 'var(--color-teal)' }}>
                      Phase {evt.payload.phase}: {evt.payload.state}
                    </span>
                  ) : (
                    <span>Event {evt.payload.type}</span>
                  )}
                </div>
              ))
            ) : (
              <div style={{ color: 'var(--color-text-secondary)' }}>
                Attack run completed in {attackResult.ms}ms with exit code {attackResult.exitCode}.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
