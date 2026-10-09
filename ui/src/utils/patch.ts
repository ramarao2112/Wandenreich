/**
 * Simple unified diff patcher for TrustSpec quick-fixes.
 * Applies hunk insertions and deletions against exact base text.
 */
export function applyUnifiedDiff(original: string, diffText: string): string {
  const origLines = original.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const diffLines = diffText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');

  let i = 0;
  // Skip diff header (--- and +++)
  while (i < diffLines.length && !diffLines[i].startsWith('@@')) {
    i++;
  }

  if (i >= diffLines.length) {
    // If no hunk header, return original
    return original;
  }

  let resultLines = [...origLines];
  let offset = 0;

  while (i < diffLines.length) {
    const header = diffLines[i];
    if (!header.startsWith('@@')) {
      i++;
      continue;
    }

    // Match @@ -oldStart,oldLen +newStart,newLen @@ or @@ -oldStart +newStart @@
    const match = header.match(/@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@/);
    if (!match) {
      i++;
      continue;
    }

    const oldStart = parseInt(match[1], 10);
    let targetIndex = oldStart - 1 + offset;

    i++;
    while (i < diffLines.length && !diffLines[i].startsWith('@@')) {
      const line = diffLines[i];
      if (line.startsWith('+')) {
        const addedLine = line.slice(1);
        resultLines.splice(targetIndex, 0, addedLine);
        targetIndex++;
        offset++;
      } else if (line.startsWith('-')) {
        resultLines.splice(targetIndex, 1);
        offset--;
      } else if (line.startsWith(' ')) {
        targetIndex++;
      }
      i++;
    }
  }

  return resultLines.join('\n');
}
