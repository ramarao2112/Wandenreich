import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useWorkbenchStore } from '../state/workbenchStore';
import { TopBar } from './TopBar';
import { Footer } from './Footer';
import { DiagnosticsTab } from './DiagnosticsTab';
import { TestsTab } from './TestsTab';
import { EvidenceTab } from './EvidenceTab';
import {
  MOCK_CHECK_F1,
  MOCK_BUILD_F2,
  MOCK_ATTACK_F2,
} from '../api/mockData';

describe('UI Components', () => {
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
        {
          id: 'f2',
          title: 'Owned trips clean',
          subtitle: 'Valid spec',
          expectedCheck: 'pass',
          expectedReview: false,
          spec: 'endpoint GET /trips/{id}:\n  resource: Trip\n  auth: required\n',
        },
      ],
      selectedExampleId: 'f2',
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
    });
  });

  it('renders TopBar with brand, file identity, mode badge, and buttons', () => {
    render(<TopBar />);

    expect(screen.getByText('TrustC')).toBeTruthy();
    expect(screen.getByText('spec.trust')).toBeTruthy();
    expect(screen.getByText('Mock Mode')).toBeTruthy();

    const checkBtn = document.getElementById('btn-action-check');
    const buildBtn = document.getElementById('btn-action-build');
    const testBtn = document.getElementById('btn-action-test-access');

    expect(checkBtn).toBeTruthy();
    expect(buildBtn).toBeTruthy();
    expect(testBtn).toBeTruthy();

    // Build and Test access are disabled initially because no check has passed
    expect(buildBtn?.getAttribute('aria-disabled')).toBe('true');
    expect(testBtn?.getAttribute('aria-disabled')).toBe('true');
  });

  it('renders DiagnosticsTab with actionable issues on check failure', () => {
    useWorkbenchStore.setState({
      checkResult: MOCK_CHECK_F1,
      checkHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
    });

    render(<DiagnosticsTab />);

    expect(screen.getByText(/Actionable Security Issues Found/i)).toBeTruthy();
    expect(screen.getAllByText('TC-001').length).toBeGreaterThan(0);
    expect(screen.getAllByText('AUTH-REQUIRED').length).toBeGreaterThan(0);
    expect(screen.getAllByText('TC-003').length).toBeGreaterThan(0);
    expect(screen.getAllByText('SENSITIVE-LEAK').length).toBeGreaterThan(0);
  });

  it('renders TestsTab with concrete headline and derived counts', () => {
    useWorkbenchStore.setState({
      attackResult: MOCK_ATTACK_F2,
      attackHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      attackBuildId: 'mock-build-f2-8787',
      buildId: 'mock-build-f2-8787',
    });

    render(<TestsTab />);

    expect(
      screen.getByText('Other users were blocked. The owner received access.')
    ).toBeTruthy();
    expect(screen.getByText('6 matched expectations')).toBeTruthy();
    expect(screen.getByText(/0 policy reviews/i)).toBeTruthy();
    expect(screen.getByText(/0 failed/i)).toBeTruthy();
    expect(screen.getAllByText('POST /trips').length).toBeGreaterThan(0);
    expect(screen.getAllByText('GET /trips/{id}').length).toBeGreaterThan(0);
  });

  it('renders EvidenceTab with endpoint policies and export button', () => {
    useWorkbenchStore.setState({
      buildResult: MOCK_BUILD_F2,
      buildHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      buildId: 'mock-build-f2-8787',
    });

    render(<EvidenceTab />);

    expect(screen.getByText('Build Evidence & Verification Report')).toBeTruthy();
    expect(screen.getByText('POST /trips')).toBeTruthy();
    expect(screen.getByText(/Export combined report/i)).toBeTruthy();
  });

  it('renders Footer with equivalent CLI command and notice', () => {
    useWorkbenchStore.setState({
      lastAction: {
        command: 'trustc check spec.trust',
        exitCode: 0,
        durationMs: 14,
      },
    });

    render(<Footer />);

    expect(screen.getByText('trustc check spec.trust')).toBeTruthy();
    expect(screen.getByText('exit 0')).toBeTruthy();
    expect(screen.getByText('14ms')).toBeTruthy();
    expect(screen.getByText(/Save as spec.trust for CLI:/i)).toBeTruthy();
  });

  it('R04: EvidenceTab renders failure warning when unexpected > 0 and never false success', () => {
    const failedAttack = {
      ...MOCK_ATTACK_F2,
      unexpected: 1,
      exitCode: 1 as const,
    };

    useWorkbenchStore.setState({
      buildResult: MOCK_BUILD_F2,
      buildHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      buildId: 'mock-build-f2-8787',
      attackResult: failedAttack,
      attackHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      attackBuildId: 'mock-build-f2-8787',
    });

    render(<EvidenceTab />);

    // Must show failure text
    expect(screen.getByText(/Access violations detected: 1 unexpected disclosures or failures/i)).toBeTruthy();
    // Must NOT show false success wording
    expect(screen.queryByText(/All actor requests conformed to specified isolation boundaries/i)).toBeNull();
  });

  it('R04: EvidenceTab renders review warning when review > 0', () => {
    const reviewAttack = {
      ...MOCK_ATTACK_F2,
      review: 1,
      exitCode: 0 as const,
    };

    useWorkbenchStore.setState({
      buildResult: MOCK_BUILD_F2,
      buildHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      buildId: 'mock-build-f2-8787',
      attackResult: reviewAttack,
      attackHash: 'ef146324f68fb20e98d2a653e0ca31ad29690d6ce4a31cc9e11a05ad38502884',
      attackBuildId: 'mock-build-f2-8787',
    });

    render(<EvidenceTab />);

    expect(screen.getByText(/Policy review required: 1 request\(s\) exercised explicit waivers/i)).toBeTruthy();
  });
});
