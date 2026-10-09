import { describe, it, expect } from 'vitest';
import { applyUnifiedDiff } from './patch';

describe('applyUnifiedDiff', () => {
  it('applies addition hunk correctly', () => {
    const original = `line 1
line 2
line 3
`;
    const diff = `--- a/file
+++ b/file
@@ -2,1 +2,2 @@
 line 2
+new line
`;
    const patched = applyUnifiedDiff(original, diff);
    expect(patched).toContain('new line');
    expect(patched.split('\n')).toEqual(['line 1', 'line 2', 'new line', 'line 3', '']);
  });
});
