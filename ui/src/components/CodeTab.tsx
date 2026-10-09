import React, { useState } from 'react';
import { useWorkbenchStore } from '../state/workbenchStore';
import { Download, FileCode, ArrowRight, Layers } from 'lucide-react';
import { ForcedLine } from '../api/types';

export const CodeTab: React.FC = () => {
  const {
    buildResult,
    buildId,
    buildHash,
    sourceHash,
    selectedFile,
    selectFile,
    selectSourceSpan,
  } = useWorkbenchStore();

  const [activeForcedLine, setActiveForcedLine] = useState<ForcedLine | null>(null);

  const isStale = Boolean(buildResult && buildHash && buildHash !== sourceHash);

  if (!buildResult || !buildResult.files || buildResult.files.length === 0) {
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
        <FileCode size={36} color="var(--color-border)" />
        <h3 style={{ fontSize: '16px', color: 'var(--color-text-primary)', fontWeight: 600 }}>
          No Generated Code Available
        </h3>
        <p style={{ maxWidth: '420px', fontSize: '13px', lineHeight: '1.6' }}>
          Run <strong>Check</strong> to ensure zero security violations, then click <strong>Build</strong> to generate FastAPI backend code with full provenance.
        </p>
      </div>
    );
  }

  const files = buildResult.files;
  const currentFile = files.find((f) => f.path === selectedFile) || files[0];
  const fileLines = currentFile.content.split('\n');
  const forcedLines = currentFile.forced || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Code Header Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '10px 16px',
          backgroundColor: 'var(--color-panel)',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary)' }}>
            Artifact:
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              backgroundColor: 'var(--color-raised)',
              padding: '2px 8px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-teal)',
            }}
          >
            {buildId || 'build-active'}
          </span>
          {isStale && (
            <span
              style={{
                fontSize: '11px',
                color: 'var(--color-review)',
                backgroundColor: 'rgba(243, 196, 126, 0.15)',
                padding: '2px 6px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-review)',
              }}
            >
              Earlier source revision
            </span>
          )}
        </div>

        {buildId && (
          <a
            href={`/api/builds/${buildId}/out.zip`}
            download={`trustc-${buildId}.zip`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              backgroundColor: 'var(--color-raised)',
              color: 'var(--color-text-primary)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              fontSize: '12px',
              fontWeight: 600,
              textDecoration: 'none',
              cursor: 'pointer',
            }}
          >
            <Download size={13} color="var(--color-teal)" />
            <span>Download out.zip</span>
          </a>
        )}
      </div>

      {/* Main Split: Left file tree & Right Code viewer with Provenance Panel */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* File Tree Navigation */}
        <div
          style={{
            width: '180px',
            backgroundColor: 'var(--color-panel)',
            borderRight: '1px solid var(--color-border)',
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
            padding: '8px',
            overflowY: 'auto',
          }}
        >
          <div
            style={{
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--color-text-secondary)',
              padding: '4px 8px',
              letterSpacing: '0.05em',
            }}
          >
            Generated Files ({files.length})
          </div>
          {files.map((file) => {
            const isSelected = file.path === currentFile.path;
            const hasForced = (file.forced || []).length > 0;
            return (
              <button
                key={file.path}
                type="button"
                onClick={() => {
                  selectFile(file.path);
                  setActiveForcedLine(null);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                  padding: '6px 10px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: isSelected ? 'var(--color-raised)' : 'transparent',
                  color: isSelected ? 'var(--color-teal)' : 'var(--color-text-primary)',
                  border: isSelected ? '1px solid var(--color-border)' : '1px solid transparent',
                  fontSize: '13px',
                  fontFamily: 'var(--font-mono)',
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <FileCode size={14} />
                  <span>{file.path}</span>
                </div>
                {hasForced && (
                  <span
                    title={`${file.forced.length} security-forced line(s)`}
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: 'var(--color-teal)',
                    }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* Code Content & Line-by-Line Viewer */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
          <div
            style={{
              flex: 1,
              overflow: 'auto',
              backgroundColor: 'var(--color-canvas)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
              lineHeight: '22px',
            }}
          >
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <tbody>
                {fileLines.map((lineContent, idx) => {
                  const lineNum = idx + 1;
                  const forced = forcedLines.find((fl) => fl.line === lineNum);
                  const isHighlighted = activeForcedLine?.line === lineNum;

                  return (
                    <tr
                      key={lineNum}
                      onClick={() => forced && setActiveForcedLine(forced)}
                      style={{
                        backgroundColor: isHighlighted
                          ? 'rgba(99, 223, 208, 0.2)'
                          : forced
                          ? 'rgba(99, 223, 208, 0.08)'
                          : 'transparent',
                        cursor: forced ? 'pointer' : 'default',
                      }}
                    >
                      {/* Line Number */}
                      <td
                        style={{
                          width: '48px',
                          textAlign: 'right',
                          paddingRight: '12px',
                          color: forced ? 'var(--color-teal)' : '#536377',
                          userSelect: 'none',
                          borderRight: '1px solid var(--color-border)',
                          fontWeight: forced ? 700 : 400,
                        }}
                      >
                        {lineNum}
                      </td>

                      {/* Line Content */}
                      <td style={{ paddingLeft: '14px', whiteSpace: 'pre', color: 'var(--color-text-primary)' }}>
                        {lineContent}
                      </td>

                      {/* Forced Line Indicator Tag */}
                      <td style={{ width: '120px', textAlign: 'right', paddingRight: '12px' }}>
                        {forced && (
                          <span
                            title={`Forced by ${forced.kind}`}
                            style={{
                              fontSize: '10px',
                              padding: '1px 6px',
                              borderRadius: 'var(--radius-sm)',
                              backgroundColor: 'rgba(99, 223, 208, 0.15)',
                              color: 'var(--color-teal)',
                              border: '1px solid var(--color-teal)',
                            }}
                          >
                            {forced.kind}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* "Why this line exists" Provenance Inspector Panel */}
          <div
            style={{
              padding: '12px 16px',
              backgroundColor: 'var(--color-panel)',
              borderTop: '1px solid var(--color-border)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Layers size={16} color="var(--color-teal)" />
              <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary)' }}>
                Why this line exists — Security Provenance
              </span>
            </div>

            {activeForcedLine ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '12px',
                  padding: '8px 12px',
                  backgroundColor: 'var(--color-raised)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '13px', color: 'var(--color-text-primary)' }}>
                    Line <strong>{activeForcedLine.line}</strong> in {currentFile.path}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'rgba(99, 223, 208, 0.15)',
                      color: 'var(--color-teal)',
                      border: '1px solid var(--color-teal)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    Rule kind: {activeForcedLine.kind}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>
                    Forced by spec.trust line {activeForcedLine.specSpan.line}:{activeForcedLine.specSpan.col}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => selectSourceSpan(activeForcedLine.specSpan)}
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
                  <span>Highlight in spec</span>
                  <ArrowRight size={13} />
                </button>
              </div>
            ) : (
              <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                {forcedLines.length > 0
                  ? `Click any highlighted line in ${currentFile.path} (${forcedLines.length} compiler-enforced lines) to inspect its TrustSpec source declaration.`
                  : `No compiler-enforced invariant statements exist in ${currentFile.path}.`}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
