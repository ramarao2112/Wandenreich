import React, { useState } from 'react';
import { useWorkbenchStore } from '../state/workbenchStore';
import { Terminal, Copy, Check, Info } from 'lucide-react';

export const Footer: React.FC = () => {
  const {
    lastAction,
    activeRun,
    announcement,
  } = useWorkbenchStore();

  const [copied, setCopied] = useState(false);

  const command = lastAction?.command || 'trustc check spec.trust';
  const exitCode = lastAction?.exitCode;
  const durationMs = lastAction?.durationMs;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const getStatusText = () => {
    if (activeRun.status === 'running') {
      return `Executing ${activeRun.kind}...`;
    }
    if (activeRun.status === 'cancelling') {
      return 'Cancelling execution...';
    }
    if (announcement) {
      return announcement;
    }
    if (lastAction) {
      return `Action completed in ${durationMs ?? 0}ms (exit ${exitCode ?? 0})`;
    }
    return 'Ready';
  };

  return (
    <footer
      role="contentinfo"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        padding: '8px 16px',
        backgroundColor: 'var(--color-panel)',
        borderTop: '1px solid var(--color-border)',
        fontSize: '12px',
        color: 'var(--color-text-secondary)',
        minHeight: '38px',
      }}
    >
      {/* Current Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor:
              activeRun.status === 'running'
                ? 'var(--color-teal)'
                : exitCode === 0
                ? 'var(--color-success)'
                : exitCode !== undefined
                ? 'var(--color-error)'
                : 'var(--color-border)',
          }}
        />
        <span style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>
          {getStatusText()}
        </span>
      </div>

      {/* Equivalent CLI Command & Clipboard */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
        <span
          title="Web source must be saved as spec.trust before running the CLI command"
          style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'help' }}
        >
          <Info size={12} />
          <span>Save as spec.trust for CLI:</span>
        </span>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            backgroundColor: 'var(--color-canvas)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--color-text-primary)',
          }}
        >
          <Terminal size={12} style={{ marginRight: '6px', color: 'var(--color-teal)' }} />
          <span>{command}</span>
          <button
            type="button"
            onClick={handleCopy}
            title="Copy equivalent CLI command"
            style={{
              marginLeft: '8px',
              background: 'none',
              border: 'none',
              color: copied ? 'var(--color-success)' : 'var(--color-text-secondary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
        </div>

        {exitCode !== undefined && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              padding: '1px 6px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: exitCode === 0 ? 'rgba(135, 226, 175, 0.15)' : 'rgba(255, 135, 149, 0.15)',
              color: exitCode === 0 ? 'var(--color-success)' : 'var(--color-error)',
              fontWeight: 600,
            }}
          >
            exit {exitCode}
          </span>
        )}

        {durationMs !== undefined && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
            {durationMs}ms
          </span>
        )}
      </div>
    </footer>
  );
};
