import React, { useMemo, useState, useRef, useEffect } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { EditorView, Decoration, MatchDecorator, ViewPlugin } from '@codemirror/view';
import { useWorkbenchStore } from '../state/workbenchStore';
import { FileCode, Undo2, Check, AlertTriangle, Eye, X, Info } from 'lucide-react';

const keywordMatcher = new MatchDecorator({
  regexp: /\b(endpoint|resource|fields|secrets|auth|authorize|returns|expose|body|required|public|env)\b/g,
  decoration: Decoration.mark({ class: 'cm-trustc-keyword' }),
});

const typeMatcher = new MatchDecorator({
  regexp: /\b(uuid|string|int|boolean)\b/g,
  decoration: Decoration.mark({ class: 'cm-trustc-type' }),
});

const builtinMatcher = new MatchDecorator({
  regexp: /\b(current_user|owner|id)\b/g,
  decoration: Decoration.mark({ class: 'cm-trustc-builtin' }),
});

const commentMatcher = new MatchDecorator({
  regexp: /#.*$/gm,
  decoration: Decoration.mark({ class: 'cm-trustc-comment' }),
});

const trustSpecHighlightPlugin = ViewPlugin.define(
  (view) => ({
    decorations: keywordMatcher.createDeco(view),
    update(u) {
      this.decorations = keywordMatcher.updateDeco(u, this.decorations);
    },
  }),
  { decorations: (v) => v.decorations }
);

const typeHighlightPlugin = ViewPlugin.define(
  (view) => ({
    decorations: typeMatcher.createDeco(view),
    update(u) {
      this.decorations = typeMatcher.updateDeco(u, this.decorations);
    },
  }),
  { decorations: (v) => v.decorations }
);

const builtinHighlightPlugin = ViewPlugin.define(
  (view) => ({
    decorations: builtinMatcher.createDeco(view),
    update(u) {
      this.decorations = builtinMatcher.updateDeco(u, this.decorations);
    },
  }),
  { decorations: (v) => v.decorations }
);

const commentHighlightPlugin = ViewPlugin.define(
  (view) => ({
    decorations: commentMatcher.createDeco(view),
    update(u) {
      this.decorations = commentMatcher.updateDeco(u, this.decorations);
    },
  }),
  { decorations: (v) => v.decorations }
);

export const EditorPane: React.FC = () => {
  const {
    source,
    setSource,
    sourceHash,
    checkHash,
    checkResult,
    diffPreview,
    closeDiffPreview,
    applyFix,
    undoStack,
    undo,
    selectedDiagnosticIndex,
    selectedSourceSpan,
  } = useWorkbenchStore();

  const [cursorPos, setCursorPos] = useState({ line: 1, col: 1 });
  const editorViewRef = useRef<EditorView | null>(null);

  // R10: Dispatch selection and scroll when selectedSourceSpan changes
  useEffect(() => {
    if (!selectedSourceSpan || !editorViewRef.current) return;
    const view = editorViewRef.current;
    const doc = view.state.doc;
    const targetLineNum = Math.min(Math.max(1, selectedSourceSpan.line), doc.lines);
    const line = doc.line(targetLineNum);
    const from = Math.min(line.from + Math.max(0, selectedSourceSpan.col - 1), line.to);

    let to = from;
    if (selectedSourceSpan.endLine && selectedSourceSpan.endCol) {
      const endLineNum = Math.min(Math.max(1, selectedSourceSpan.endLine), doc.lines);
      const endLine = doc.line(endLineNum);
      to = Math.min(endLine.from + Math.max(0, selectedSourceSpan.endCol - 1), endLine.to);
    }
    if (to < from) to = from;

    view.dispatch({
      selection: { anchor: from, head: to },
      scrollIntoView: true,
    });
  }, [selectedSourceSpan]);

  // Staleness check
  const isStale = Boolean(checkResult && checkHash && checkHash !== sourceHash);

  // Custom dark theme matching workbench tokens with syntax coloring
  const editorTheme = useMemo(() => {
    return EditorView.theme({
      '&': {
        color: '#EDF2FA',
        backgroundColor: '#0C111B',
        fontSize: '14px',
        fontFamily: "var(--font-mono)",
        height: '100%',
      },
      '.cm-content': {
        caretColor: '#63DFD0',
        padding: '12px 0',
      },
      '&.cm-focused .cm-cursor': {
        borderLeftColor: '#63DFD0',
        borderLeftWidth: '2px',
      },
      '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
        backgroundColor: 'rgba(99, 223, 208, 0.25) !important',
      },
      '.cm-selectionMatch': {
        backgroundColor: 'transparent !important',
      },
      '.cm-gutters': {
        backgroundColor: '#121A27',
        color: '#ACBBCE',
        borderRight: '1px solid #2B384B',
        userSelect: 'none',
      },
      '.cm-activeLineGutter': {
        backgroundColor: '#1A2535',
        color: '#EDF2FA',
      },
      '.cm-activeLine': {
        backgroundColor: 'rgba(26, 37, 53, 0.5)',
      },
      '.cm-line': {
        lineHeight: '22px',
      },
      '.cm-trustc-keyword': {
        color: '#63DFD0',
        fontWeight: '600',
      },
      '.cm-trustc-type': {
        color: '#A5B4FC',
      },
      '.cm-trustc-builtin': {
        color: '#F3C47E',
      },
      '.cm-trustc-comment': {
        color: '#64748B',
        fontStyle: 'italic',
      },
    }, { dark: true });
  }, []);

  const editorExtensions = useMemo(() => {
    return [
      EditorView.contentAttributes.of({
        'aria-label': 'TrustSpec specification code',
      }),
      trustSpecHighlightPlugin,
      typeHighlightPlugin,
      builtinHighlightPlugin,
      commentHighlightPlugin,
    ];
  }, []);

  const activeDiagnostic =
    checkResult && selectedDiagnosticIndex !== null
      ? checkResult.diagnostics[selectedDiagnosticIndex]
      : null;

  return (
    <section
      aria-label="TrustSpec Editor"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        backgroundColor: 'var(--color-canvas)',
        borderRight: '1px solid var(--color-border)',
        overflow: 'hidden',
      }}
    >
      {/* Editor Header Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          backgroundColor: 'var(--color-panel)',
          borderBottom: '1px solid var(--color-border)',
          userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileCode size={16} color="var(--color-teal)" />
          <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary)' }}>
            spec.trust
          </span>
          <span style={{ fontSize: '11px', color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>
            Ln {cursorPos.line}, Col {cursorPos.col}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {undoStack.length > 0 && (
            <button
              type="button"
              onClick={() => undo()}
              title="Undo last edit / fix [Ctrl+Z]"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 8px',
                fontSize: '12px',
                backgroundColor: 'var(--color-raised)',
                color: 'var(--color-text-primary)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer',
              }}
            >
              <Undo2 size={13} />
              <span>Undo ({undoStack.length})</span>
            </button>
          )}

          {isStale && (
            <div
              role="status"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '2px 8px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: 'rgba(243, 196, 126, 0.15)',
                color: 'var(--color-review)',
                border: '1px solid var(--color-review)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <AlertTriangle size={12} />
              <span>Earlier source revision</span>
            </div>
          )}
        </div>
      </div>

      {/* Diff Preview Banner */}
      {diffPreview && (
        <div
          role="region"
          aria-label="Fix preview"
          style={{
            backgroundColor: 'var(--color-raised)',
            borderBottom: '1px solid var(--color-border)',
            padding: '10px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Eye size={14} color="var(--color-teal)" />
              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-teal)' }}>
                {diffPreview.label}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <button
                type="button"
                onClick={() => applyFix(diffPreview.diff, diffPreview.baseSpecHash)}
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
              <button
                type="button"
                onClick={() => closeDiffPreview()}
                aria-label="Close diff preview"
                style={{
                  padding: '4px 8px',
                  backgroundColor: 'transparent',
                  color: 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                }}
              >
                <X size={13} />
              </button>
            </div>
          </div>
          <div
            tabIndex={0}
            aria-label="Unified diff preview"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              backgroundColor: 'var(--color-canvas)',
              padding: '8px 10px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              overflowX: 'auto',
              maxHeight: '220px',
              color: 'var(--color-text-primary)',
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
            }}
          >
            {diffPreview.diff.split('\n').map((line, idx) => {
              const isAdd = line.startsWith('+') && !line.startsWith('+++');
              const isDel = line.startsWith('-') && !line.startsWith('---');
              const isHunk = line.startsWith('@@');

              let bg = 'transparent';
              let color = 'inherit';
              let fontWeight = 400;

              if (isAdd) {
                bg = 'rgba(99, 223, 208, 0.15)';
                color = '#63DFD0';
                fontWeight = 600;
              } else if (isDel) {
                bg = 'rgba(255, 135, 149, 0.15)';
                color = '#FF8795';
              } else if (isHunk) {
                color = '#F3C47E';
                fontWeight = 600;
              }

              return (
                <div
                  key={idx}
                  style={{
                    backgroundColor: bg,
                    color: color,
                    fontWeight: fontWeight,
                    padding: '2px 6px',
                    borderRadius: '2px',
                    whiteSpace: 'pre',
                  }}
                >
                  {line}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Active Diagnostic Span Banner */}
      {activeDiagnostic && !diffPreview && (
        <div
          style={{
            backgroundColor: 'rgba(255, 135, 149, 0.1)',
            borderBottom: '1px solid var(--color-error)',
            padding: '8px 12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--color-error)' }}>
            <Info size={14} />
            <span>
              <strong>{activeDiagnostic.ruleId}</strong>: {activeDiagnostic.message}
            </span>
          </div>
          <span style={{ color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>
            Line {activeDiagnostic.span.line}:{activeDiagnostic.span.col}
          </span>
        </div>
      )}

      {/* CodeMirror Editor Area */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <CodeMirror
          value={source}
          height="100%"
          theme={editorTheme}
          extensions={editorExtensions}
          onCreateEditor={(view) => {
            editorViewRef.current = view;
          }}
          basicSetup={{
            lineNumbers: true,
            highlightActiveLineGutter: true,
            highlightSpecialChars: true,
            history: true,
            foldGutter: true,
            drawSelection: true,
            dropCursor: true,
            allowMultipleSelections: true,
            indentOnInput: true,
            syntaxHighlighting: true,
            bracketMatching: true,
            closeBrackets: true,
            autocompletion: false,
            rectangularSelection: true,
            crosshairCursor: true,
            highlightActiveLine: true,
            highlightSelectionMatches: false,
            closeBracketsKeymap: true,
            defaultKeymap: true,
            searchKeymap: true,
            historyKeymap: true,
            foldKeymap: true,
            completionKeymap: false,
            lintKeymap: false,
          }}
          onChange={(val) => {
            setSource(val);
          }}
          onUpdate={(viewUpdate) => {
            const head = viewUpdate.state.selection.main.head;
            const line = viewUpdate.state.doc.lineAt(head);
            setCursorPos({
              line: line.number,
              col: head - line.from + 1,
            });
          }}
        />
      </div>
    </section>
  );
};
