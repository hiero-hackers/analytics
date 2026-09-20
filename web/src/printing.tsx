/** Print the existing view without discarding its local selections. */
import {
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { flushSync } from 'react-dom';
import { PrintContext } from './printContext';

const PREPARE_TIMEOUT_MS = 15_000;

export function PrintProvider({ children }: { children: ReactNode }) {
  const [printing, setPrinting] = useState(() => window.matchMedia?.('print').matches ?? false);
  const active = useRef(printing);
  const closed = useRef<HTMLDetailsElement[]>([]);
  const focus = useRef<HTMLElement | null>(null);
  const focusFrame = useRef<number | undefined>(undefined);
  const restorePending = useRef(false);
  const scroll = useRef<{ element: HTMLElement; top: number; left: number }[]>([]);
  const begin = useCallback(() => {
    if (active.current) return;
    active.current = true;
    restorePending.current = false;
    if (focusFrame.current !== undefined) cancelAnimationFrame(focusFrame.current);
    focus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    scroll.current = [
      ...document.querySelectorAll<HTMLElement>(
        '.wrap .tablewrap, .wrap .hipmx-wrap, .wrap .hipboard, .wrap .hipboard-chips',
      ),
    ].map((element) => ({ element, top: element.scrollTop, left: element.scrollLeft }));
    closed.current = [
      ...document.querySelectorAll<HTMLDetailsElement>('.wrap details:not([open])'),
    ];
    document.documentElement.dataset.printing = 'true';
    // beforeprint is synchronous: React must mount the non-virtualised rows
    // before the browser snapshots layout, not in a later effect/frame.
    flushSync(() => setPrinting(true));
    closed.current.forEach((details) => {
      details.open = true;
    });
  }, []);
  const finish = useCallback(() => {
    if (!active.current) return;
    active.current = false;
    restorePending.current = true;
    setPrinting(false);
    delete document.documentElement.dataset.printing;
    closed.current.forEach((details) => {
      if (details.isConnected) details.open = false;
    });
    closed.current = [];
  }, []);

  useLayoutEffect(() => {
    if (printing || !restorePending.current) return;
    restorePending.current = false;
    // Schedule after the screen DOM commits; a frame requested in finish()
    // can run before React has made the controls visible under browser load.
    focusFrame.current = requestAnimationFrame(() => {
      focusFrame.current = undefined;
      // Firefox resets offsets when a scrolling element is display:none.
      for (const { element, top, left } of scroll.current) {
        if (!element.isConnected) continue;
        element.scrollTop = top;
        element.scrollLeft = left;
      }
      scroll.current = [];
      if (focus.current?.isConnected) focus.current.focus({ preventScroll: true });
    });
    return () => {
      if (focusFrame.current !== undefined) cancelAnimationFrame(focusFrame.current);
    };
  }, [printing]);

  useEffect(() => {
    const media = window.matchMedia?.('print');
    // Print media may already be active when this page mounts (for example,
    // a new print view or browser automation). No change event follows it.
    if (active.current) {
      document.documentElement.dataset.printing = 'true';
      closed.current = [
        ...document.querySelectorAll<HTMLDetailsElement>('.wrap details:not([open])'),
      ];
      closed.current.forEach((details) => {
        details.open = true;
      });
    }
    const onMedia = (event: MediaQueryListEvent) => (event.matches ? begin() : finish());
    window.addEventListener('beforeprint', begin);
    window.addEventListener('afterprint', finish);
    media?.addEventListener('change', onMedia);
    return () => {
      window.removeEventListener('beforeprint', begin);
      window.removeEventListener('afterprint', finish);
      media?.removeEventListener('change', onMedia);
      if (focusFrame.current !== undefined) cancelAnimationFrame(focusFrame.current);
      delete document.documentElement.dataset.printing;
      closed.current.forEach((details) => {
        if (details.isConnected) details.open = false;
      });
    };
  }, [begin, finish]);

  return (
    <PrintContext.Provider value={{ printing, begin, finish }}>{children}</PrintContext.Provider>
  );
}

/** Bounded readiness: a broken image must never become a silent blank chart. */
async function waitForPrintAssets(signal: AbortSignal) {
  const images = [...document.querySelectorAll<HTMLImageElement>('img[data-print-chart]')];
  // Use the requested source: currentSrc can still name the previous variant
  // while the newly selected image is loading.
  const sources = images.map((img) => img.src);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let frame: number | undefined;
  let onAbort: (() => void) | undefined;
  let finished = false;
  const prepare = async () => {
    await Promise.all([
      document.fonts?.ready,
      ...images.map(async (img) => {
        await img.decode();
        if (!img.naturalWidth) throw new Error('Missing chart');
      }),
    ]);
    if (finished) return;
    signal.throwIfAborted();
    // Let image load handlers commit their captions/status before printing.
    // Keep this frame inside the timeout too: background tabs may suspend it.
    await new Promise<void>((resolve) => {
      frame = requestAnimationFrame(() => resolve());
    });
    signal.throwIfAborted();
    const current = [...document.querySelectorAll<HTMLImageElement>('img[data-print-chart]')];
    if (
      current.length !== images.length ||
      current.some(
        (img, i) =>
          img !== images[i] ||
          (img.currentSrc || img.src) !== sources[i] ||
          !img.complete ||
          !img.naturalWidth,
      ) ||
      document.querySelector('[data-print-error], [data-print-pending]')
    ) {
      throw new Error('Charts changed or could not finish loading');
    }
  };
  try {
    await Promise.race([
      prepare(),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(
          () => reject(new Error('Print preparation timed out')),
          PREPARE_TIMEOUT_MS,
        );
      }),
      new Promise<never>((_resolve, reject) => {
        onAbort = () => reject(new DOMException('Print preparation cancelled', 'AbortError'));
        signal.addEventListener('abort', onAbort, { once: true });
        if (signal.aborted) onAbort();
      }),
    ]);
  } finally {
    finished = true;
    if (timer !== undefined) clearTimeout(timer);
    if (frame !== undefined) cancelAnimationFrame(frame);
    if (onAbort) signal.removeEventListener('abort', onAbort);
  }
}

export function PrintControls({ ready = true }: { ready?: boolean }) {
  const { printing, begin, finish } = useContext(PrintContext);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => {
      // Controls are keyed by tab/org: navigation cancels the old preparation.
      if (!pending.current) return;
      pending.current.abort();
      pending.current = null;
      finish();
    };
  }, [finish]);
  useEffect(() => {
    if (!printing) pending.current?.abort();
  }, [printing]);
  const print = async () => {
    if (!ready || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setError(false);
    setBusy(true);
    begin();
    try {
      await waitForPrintAssets(controller.signal);
      window.print();
    } catch {
      if (pending.current === controller) {
        finish();
        if (!controller.signal.aborted) setError(true);
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
      }
    }
  };
  return (
    <div data-print-hide className="my-4">
      <button type="button" className="dl" disabled={!ready || busy} onClick={() => void print()}>
        {busy ? 'Preparing print…' : 'Print tab'}
      </button>
      {busy && (
        <span role="status" className="ml-3 text-[13px] text-muted">
          Loading charts for printing…
        </span>
      )}
      {error && (
        <p role="alert" className="error">
          Could not prepare every chart for printing. Check your connection, reload and try again.
        </p>
      )}
    </div>
  );
}
