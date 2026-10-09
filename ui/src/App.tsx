import React, { useEffect, useState } from 'react';
import { useWorkbenchStore } from './state/workbenchStore';
import { TopBar } from './components/TopBar';
import { EditorPane } from './components/EditorPane';
import { ResultsPane } from './components/ResultsPane';
import { Footer } from './components/Footer';

export const App: React.FC = () => {
  const {
    initServer,
    announcement,
    activeRun,
    runCheck,
    cancelActiveRun,
    isOffline,
  } = useWorkbenchStore();

  const [isNarrow, setIsNarrow] = useState(false);

  // Initialize server connection on mount and expose store for testing
  useEffect(() => {
    initServer();
    if (typeof window !== 'undefined') {
      (window as unknown as { __WORKBENCH_STORE__?: typeof useWorkbenchStore }).__WORKBENCH_STORE__ = useWorkbenchStore;
    }
  }, [initServer]);

  // Responsive layout listener (stack below 900px)
  useEffect(() => {
    const handleResize = () => {
      setIsNarrow(window.innerWidth < 900);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Global keyboard shortcuts: Ctrl+Enter (run Check), Escape (Cancel active run)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (activeRun.status === 'idle') {
          runCheck();
        }
      } else if (e.key === 'Escape') {
        if (activeRun.status === 'running') {
          e.preventDefault();
          cancelActiveRun();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeRun.status, runCheck, cancelActiveRun]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100vw',
        overflow: 'hidden',
        backgroundColor: 'var(--color-canvas)',
        color: 'var(--color-text-primary)',
      }}
    >
      {/* Screen Reader Announcement Live Region */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        id="a11y-announcements"
      >
        {announcement}
      </div>

      {/* Offline Alert Banner (if offline in live mode) */}
      {isOffline && (
        <div
          role="alert"
          style={{
            backgroundColor: 'rgba(243, 196, 126, 0.2)',
            color: 'var(--color-review)',
            borderBottom: '1px solid var(--color-review)',
            padding: '6px 16px',
            fontSize: '12px',
            fontWeight: 600,
            textAlign: 'center',
          }}
        >
          Compiler server is unreachable. Workbench is running in offline mock capability mode.
        </div>
      )}

      {/* Top Application Bar */}
      <TopBar />

      {/* Main Workbench Body: 42/58 Editor/Results Split on desktop, stacked on narrow */}
      <main
        style={{
          display: 'flex',
          flex: 1,
          minHeight: 0,
          flexDirection: isNarrow ? 'column' : 'row',
          overflow: isNarrow ? 'auto' : 'hidden',
        }}
      >
        {/* Left: Editor Pane (42% split on desktop) */}
        <div
          style={{
            width: isNarrow ? '100%' : '42%',
            height: isNarrow ? '450px' : '100%',
            flexShrink: 0,
            minHeight: 0,
          }}
        >
          <EditorPane />
        </div>

        {/* Right: Results Pane (58% split on desktop) */}
        <div
          style={{
            width: isNarrow ? '100%' : '58%',
            height: isNarrow ? 'auto' : '100%',
            flex: isNarrow ? 'none' : 1,
            minHeight: 0,
          }}
        >
          <ResultsPane />
        </div>
      </main>

      {/* Bottom Status & CLI Footer */}
      <Footer />
    </div>
  );
};

export default App;
