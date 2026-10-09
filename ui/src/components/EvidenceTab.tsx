import React, { useState } from 'react';
import { useWorkbenchStore } from '../state/workbenchStore';
import { Download, FileCheck2, ChevronDown, ChevronRight } from 'lucide-react';

export const EvidenceTab: React.FC = () => {
  const {
    buildResult,
    buildHash,
    attackResult,
    attackBuildId,
    attackHash,
    checkResult,
    sourceHash,
    buildId,
    dataMode,
    resultOriginMode,
    serverSessionId,
  } = useWorkbenchStore();

  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  const evidence = buildResult?.evidence;

  // Strict build identity matching per brief §4 / S7-01
  const isAttackMatching = Boolean(
    attackResult &&
      attackBuildId === buildId &&
      (attackHash === buildHash || attackHash === evidence?.specHash)
  );

  const handleExportJSON = () => {
    const matchingCheck =
      checkResult && checkResult.specHash === evidence?.specHash ? checkResult : null;
    const isEditorStale = sourceHash !== evidence?.specHash;

    const runtimeEvidence = isAttackMatching
      ? attackResult
      : {
          tested: false,
          status: 'not_tested',
          reason: `Access tests have not been executed against build ${buildId || 'active'}.`,
        };

    const bundle = {
      specHash: evidence?.specHash || sourceHash,
      buildId: buildId,
      originMode: resultOriginMode || dataMode,
      serverSessionId: serverSessionId,
      ...(isEditorStale ? { currentEditorContext: { specHash: sourceHash, isStale: true } } : {}),
      compilerEvidence: evidence || null,
      checkResult: matchingCheck,
      ...(!matchingCheck && checkResult
        ? { unmatchedLatestCheck: { specHash: checkResult.specHash, ok: checkResult.ok } }
        : {}),
      runtimeAttackEvidence: runtimeEvidence,
      exportedAt: new Date().toISOString(),
      disclaimer:
        'TrustC evidence verifies declared structural invariants and runtime access test assertions. It is not an absolute mathematical proof of absence of all vulnerabilities.',
    };

    const blob = new Blob([JSON.stringify(bundle, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trustc-evidence-${buildId || 'report'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!evidence) {
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
        <FileCheck2 size={36} color="var(--color-border)" />
        <h3 style={{ fontSize: '16px', color: 'var(--color-text-primary)', fontWeight: 600 }}>
          No Build Evidence Available
        </h3>
        <p style={{ maxWidth: '440px', fontSize: '13px', lineHeight: '1.6' }}>
          Run <strong>Check</strong> and <strong>Build</strong> to compile evidence of endpoint policies, structural restrictions, and invariant checks.
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Evidence Top Summary */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text-primary)' }}>
            Build Evidence & Verification Report
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
            Structural invariant enforcement and runtime access observation records.
          </p>
        </div>

        <button
          type="button"
          id="btn-export-evidence"
          onClick={handleExportJSON}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 14px',
            backgroundColor: 'var(--color-teal)',
            color: 'var(--color-dark-ink)',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Download size={14} />
          <span>Export combined report (JSON)</span>
        </button>
      </div>

      {/* Artifact Identity Card */}
      <div
        style={{
          backgroundColor: 'var(--color-panel)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-md)',
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          fontSize: '13px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ color: 'var(--color-text-secondary)' }}>Target Build:</span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontWeight: 600,
                color: 'var(--color-teal)',
                backgroundColor: 'var(--color-raised)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              {evidence.buildId}
            </span>
          </div>

          <button
            type="button"
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              color: 'var(--color-text-secondary)',
              cursor: 'pointer',
              fontSize: '12px',
            }}
          >
            <span>{showTechnicalDetails ? 'Hide technical hashes' : 'Show technical hashes'}</span>
            {showTechnicalDetails ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>

        {showTechnicalDetails && (
          <div
            style={{
              marginTop: '6px',
              paddingTop: '8px',
              borderTop: '1px solid var(--color-border)',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '12px',
              fontSize: '12px',
            }}
          >
            <div>
              <span style={{ color: 'var(--color-text-secondary)' }}>Spec SHA-256:</span>
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)', marginTop: '2px' }}>
                {evidence.specHash}
              </div>
            </div>
            <div>
              <span style={{ color: 'var(--color-text-secondary)' }}>Compiler Version:</span>
              <div style={{ color: 'var(--color-text-primary)', marginTop: '2px' }}>
                {evidence.compilerVersion} ({evidence.templateVersion})
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Section 1: Endpoint Policies */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
          Endpoint Security Policies ({evidence.endpointPolicies.length})
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {evidence.endpointPolicies.map((pol, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                backgroundColor: 'var(--color-panel)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border)',
                fontSize: '13px',
              }}
            >
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{pol.endpoint}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    fontSize: '11px',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'rgba(99, 223, 208, 0.15)',
                    color: 'var(--color-teal)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  mode: {pol.mode}
                </span>
                {pol.ownerWaived && (
                  <span
                    style={{
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'rgba(243, 196, 126, 0.15)',
                      color: 'var(--color-review)',
                    }}
                  >
                    owner-waived
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Section 2: Structural Restrictions */}
      {evidence.structuralRestrictions.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Structural Compiler Enforcements
          </h3>
          <ul style={{ paddingLeft: '20px', fontSize: '13px', color: 'var(--color-text-primary)', lineHeight: '1.6' }}>
            {evidence.structuralRestrictions.map((res, idx) => (
              <li key={idx}>{res}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Section 3: Runtime Observations */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
          Runtime Access Invariant Observations
        </h3>
        {isAttackMatching && attackResult ? (() => {
          const hasFailed = attackResult.unexpected > 0 || attackResult.exitCode !== 0;
          const hasReview = attackResult.review > 0;
          const isEmpty = attackResult.total === 0;

          let borderCol = 'var(--color-border)';
          let bgCol = 'var(--color-panel)';
          let titleCol = 'var(--color-success)';
          let title = '✓ All actor requests conformed';
          let subtitle = `Observed in ${attackResult.steps.length} automated harness execution steps`;
          let desc = `All ${attackResult.total} actor requests conformed to specified isolation boundaries under test for build ${buildId}.`;

          if (hasFailed) {
            borderCol = 'var(--color-error)';
            bgCol = 'rgba(255, 135, 149, 0.1)';
            titleCol = 'var(--color-error)';
            title = `✕ Access violations detected: ${attackResult.unexpected} unexpected disclosures or failures`;
            subtitle = `Observed in ${attackResult.steps.length} automated harness execution steps`;
            desc = `${attackResult.unexpected} actor request(s) violated security boundaries (exit code ${attackResult.exitCode}). Review the failed assertions in Access tests.`;
          } else if (hasReview) {
            borderCol = 'var(--color-review)';
            bgCol = 'rgba(243, 196, 126, 0.1)';
            titleCol = 'var(--color-review)';
            title = `⚠ Policy review required: ${attackResult.review} request(s) exercised explicit waivers`;
            subtitle = `Observed in ${attackResult.steps.length} automated harness execution steps`;
            desc = `${attackResult.review} actor request(s) exercised explicit policy waivers and require manual review for build ${buildId}.`;
          } else if (isEmpty) {
            titleCol = 'var(--color-text-secondary)';
            title = `No eligible endpoints exercised`;
            subtitle = `Observed in 0 automated harness execution steps`;
            desc = `0 automated test steps were generated or run for build ${buildId}.`;
          }

          const totalEndpoints =
            (attackResult.coverage?.testedEndpoints?.length || 0) +
            (attackResult.coverage?.excludedEndpoints?.length || 0);
          const exercisedEndpoints = attackResult.coverage?.testedEndpoints?.length || 0;

          return (
            <div
              style={{
                padding: '14px 16px',
                backgroundColor: bgCol,
                borderRadius: 'var(--radius-md)',
                border: `1px solid ${borderCol}`,
                fontSize: '13px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ color: titleCol, fontWeight: 700, fontSize: '14px' }}>
                {title}
              </div>
              <div style={{ color: 'var(--color-text-secondary)', fontSize: '12px', fontWeight: 600 }}>
                {subtitle}
              </div>
              <div style={{ color: 'var(--color-text-primary)', fontSize: '13px', lineHeight: '1.5' }}>
                {desc}
              </div>

              {/* Endpoint coverage display per brief §3.6 */}
              {totalEndpoints > 0 && (
                <div
                  style={{
                    marginTop: '4px',
                    paddingTop: '8px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.1)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ fontWeight: 600, color: 'var(--color-teal)' }}>
                    Endpoint Coverage: {exercisedEndpoints} of {totalEndpoints} endpoints exercised
                  </div>
                  {attackResult.coverage.excludedEndpoints.map((ex, idx) => (
                    <div key={idx} style={{ color: 'var(--color-text-secondary)' }}>
                      • <code>{ex.endpoint}</code>: {ex.reason}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })() : (
          <div
            style={{
              padding: '12px 14px',
              backgroundColor: 'var(--color-panel)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontSize: '13px',
              color: 'var(--color-text-secondary)',
            }}
          >
            <span style={{ color: 'var(--color-review)', fontWeight: 600 }}>Not tested: </span>
            No runtime access observations recorded for build <code>{buildId || 'active'}</code>.
            Click <strong>Test access</strong> in the workflow bar to execute the multi-actor harness against this artifact.
          </div>
        )}
      </div>

      {/* Section 4: Known Limitations */}
      {evidence.limitations.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
            Known Limitations & Environment Boundary
          </h3>
          <ul style={{ paddingLeft: '20px', fontSize: '12px', color: 'var(--color-text-secondary)', lineHeight: '1.6' }}>
            {evidence.limitations.map((lim, idx) => (
              <li key={idx}>{lim}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
