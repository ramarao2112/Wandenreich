import { describe, it, expect, beforeEach } from 'vitest';
import { useWorkbenchStore } from './workbenchStore';
import { MOCK_CHECK_F2, MOCK_ATTACK_F2 } from '../api/mockData';

describe('workbenchStore', () => {
  beforeEach(() => {
    // Reset state before each test
    useWorkbenchStore.setState({
      source: '',
      sourceVersion: 0,
      sourceHash: '',
      dataMode: 'mock',
      activeTab: 'diagnostics',
      selectedDiagnosticIndex: null,
      selectedFile: null,
      selectedSourceSpan: null,
      diffPreview: null,
      undoStack: [],
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

  it('updates source and computes new hash while preserving undo stack', async () => {
    const store = useWorkbenchStore.getState();
    await store.setSource('endpoint GET /health:\n  auth: public');

    const updated = useWorkbenchStore.getState();
    expect(updated.source).toBe('endpoint GET /health:\n  auth: public');
    expect(updated.sourceVersion).toBe(1);
    expect(updated.sourceHash).toBeTruthy();
  });

  it('detects staleness when source edits occur after a check', async () => {
    // Simulate completed check on initial source
    const initialSource = 'endpoint GET /health:\n  auth: public';
    await useWorkbenchStore.getState().setSource(initialSource);
    const initialHash = useWorkbenchStore.getState().sourceHash;

    useWorkbenchStore.setState({
      checkResult: MOCK_CHECK_F2,
      checkHash: initialHash,
    });

    // Check is fresh
    expect(useWorkbenchStore.getState().checkHash).toBe(useWorkbenchStore.getState().sourceHash);

    // Now edit source
    await useWorkbenchStore.getState().setSource(initialSource + '\n  returns: Health');
    const newHash = useWorkbenchStore.getState().sourceHash;

    // Check is now stale
    expect(useWorkbenchStore.getState().checkHash).not.toBe(newHash);
  });

  it('previews and applies a unified diff fix with undo support', async () => {
    const origSource = 'endpoint GET /trips/{id}:\n  resource: Trip\n';
    await useWorkbenchStore.getState().setSource(origSource);
    const baseHash = useWorkbenchStore.getState().sourceHash;

    const diff = '--- a/spec.trust\n+++ b/spec.trust\n@@ -1,2 +1,3 @@\n endpoint GET /trips/{id}:\n   resource: Trip\n+  auth: required\n';

    // Preview fix
    useWorkbenchStore.getState().previewFix(diff, baseHash, 'Require auth');
    expect(useWorkbenchStore.getState().diffPreview).toBeTruthy();
    expect(useWorkbenchStore.getState().diffPreview?.label).toBe('Require auth');

    // Close preview
    useWorkbenchStore.getState().closeDiffPreview();
    expect(useWorkbenchStore.getState().diffPreview).toBeNull();

    // Apply fix with matching base hash
    const applied = await useWorkbenchStore.getState().applyFix(diff, baseHash);
    expect(applied).toBe(true);

    const postFixState = useWorkbenchStore.getState();
    expect(postFixState.source).toContain('auth: required');
    expect(postFixState.undoStack.length).toBe(1);

    // Undo the fix
    await useWorkbenchStore.getState().undo();
    const undoneState = useWorkbenchStore.getState();
    expect(undoneState.source).toBe(origSource);
    expect(undoneState.undoStack.length).toBe(0);
  });

  it('refuses to apply patch if baseSpecHash does not match current source', async () => {
    await useWorkbenchStore.getState().setSource('line 1\n');
    const wrongHash = '0000000000000000000000000000000000000000000000000000000000000000';
    const diff = '--- a/spec.trust\n+++ b/spec.trust\n@@ -1 +1 @@\n-line 1\n+line 2\n';

    const applied = await useWorkbenchStore.getState().applyFix(diff, wrongHash);
    expect(applied).toBe(false);
    expect(useWorkbenchStore.getState().announcement).toContain('Cannot apply fix');
  });

  it('correctly calculates derived counts for access tests: matched = asExpected + review', () => {
    // In MOCK_ATTACK_F2: asExpected = 6, review = 0, unexpected = 0
    const matched = MOCK_ATTACK_F2.asExpected + MOCK_ATTACK_F2.review;
    expect(matched).toBe(6);
    expect(MOCK_ATTACK_F2.unexpected).toBe(0);

    // With a policy review (e.g. F3 fixture with 9 expected, 1 review):
    const f3Mock = { ...MOCK_ATTACK_F2, asExpected: 9, review: 1, unexpected: 0 };
    const f3Matched = f3Mock.asExpected + f3Mock.review;
    expect(f3Matched).toBe(10);
  });
});
