import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { useWorkbenchStore } from '../state/workbenchStore';
import { TopBar } from './TopBar';
import { Footer } from './Footer';
import { DiagnosticsTab } from './DiagnosticsTab';
import { TestsTab } from './TestsTab';
import { EvidenceTab } from './EvidenceTab';
import { MOCK_CHECK_F1, MOCK_BUILD_F2, MOCK_ATTACK_F2 } from '../api/mockData';

describe('Accessibility (axe)', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({
      source: 'endpoint GET /health:\n  auth: public\n',
      sourceVersion: 1,
      sourceHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      dataMode: 'mock',
      isOffline: false,
      announcement: null,
      activeTab: 'diagnostics',
      selectedDiagnosticIndex: null,
      selectedFile: null,
      selectedSourceSpan: null,
      diffPreview: null,
      undoStack: [],
      examples: [
        {
          id: 'f1',
          title: 'Auth required and sensitive leak',
          subtitle: 'Missing auth',
          expectedCheck: 'fail',
          expectedReview: false,
          spec: 'endpoint GET /trips/{id}:\n  resource: Trip\n',
        },
      ],
      selectedExampleId: 'f1',
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
      checkResult: MOCK_CHECK_F1,
      checkHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      buildResult: MOCK_BUILD_F2,
      buildHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      buildId: 'mock-build-f2-8787',
      attackResult: MOCK_ATTACK_F2,
      attackHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      attackBuildId: 'mock-build-f2-8787',
      executionFailure: null,
      lastAction: {
        command: 'trustc check spec.trust',
        exitCode: 0,
        durationMs: 14,
      },
    });
  });

  it('TopBar has no axe accessibility violations', async () => {
    const { container } = render(<TopBar />);
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it('DiagnosticsTab has no axe accessibility violations', async () => {
    const { container } = render(<DiagnosticsTab />);
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it('TestsTab has no axe accessibility violations', async () => {
    const { container } = render(<TestsTab />);
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it('EvidenceTab has no axe accessibility violations', async () => {
    const { container } = render(<EvidenceTab />);
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it('Footer has no axe accessibility violations', async () => {
    const { container } = render(<Footer />);
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });
});
