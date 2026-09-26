import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PrintControls, PrintProvider } from '../printing';
import { usePrintMode } from '../printContext';
import { PrintLayout } from '../components/PrintFooter';
import { cssString, provenanceLine, supportsPageMargins } from '../printUtils';

const originalFonts = Object.getOwnPropertyDescriptor(document, 'fonts');
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  if (originalFonts) Object.defineProperty(document, 'fonts', originalFonts);
  else Reflect.deleteProperty(document, 'fonts');
});

function PrintProbe() {
  return <p>{usePrintMode() ? 'Print content' : 'Screen content'}</p>;
}

describe('Print lifecycle', () => {
  it('synchronously prepares native printing and restores only previously closed sections', () => {
    render(
      <PrintProvider>
        <div className="wrap">
          <PrintProbe />
          <details data-testid="closed">
            <summary>Closed</summary>Hidden content
          </details>
          <details data-testid="open" open>
            <summary>Open</summary>Visible content
          </details>
        </div>
      </PrintProvider>,
    );

    act(() => {
      window.dispatchEvent(new Event('beforeprint'));
    });
    expect(screen.getByText('Print content')).toBeInTheDocument();
    expect(screen.getByTestId('closed')).toHaveAttribute('open');
    // Duplicate native events must not overwrite the saved closed state.
    act(() => {
      window.dispatchEvent(new Event('beforeprint'));
    });
    act(() => {
      window.dispatchEvent(new Event('afterprint'));
    });
    expect(screen.getByText('Screen content')).toBeInTheDocument();
    expect(screen.getByTestId('closed')).not.toHaveAttribute('open');
    expect(screen.getByTestId('open')).toHaveAttribute('open');
    expect(document.documentElement).not.toHaveAttribute('data-printing');
  });

  it('bounds font/image preparation and restores the screen after a timeout', async () => {
    vi.useFakeTimers();
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    Object.defineProperty(document, 'fonts', {
      configurable: true,
      value: { ready: new Promise(() => {}) },
    });
    render(
      <PrintProvider>
        <PrintControls />
        <PrintProbe />
      </PrintProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Print tab' }));
    expect(screen.getByRole('button', { name: 'Preparing print…' })).toBeDisabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Could not prepare every chart');
    expect(screen.getByText('Screen content')).toBeInTheDocument();
    expect(print).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Print tab' })).toBeEnabled();
  });

  it('cleans up the global print marker when the provider unmounts', () => {
    const { unmount } = render(
      <PrintProvider>
        <PrintProbe />
      </PrintProvider>,
    );
    act(() => {
      window.dispatchEvent(new Event('beforeprint'));
    });
    unmount();
    expect(document.documentElement).not.toHaveAttribute('data-printing');
    act(() => {
      window.dispatchEvent(new Event('beforeprint'));
    });
    expect(document.documentElement).not.toHaveAttribute('data-printing');
  });

  it('also times out a suspended animation frame before opening the dialog', async () => {
    vi.useFakeTimers();
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    const requestFrame = vi.fn(() => 42);
    const cancelFrame = vi.fn();
    vi.stubGlobal('requestAnimationFrame', requestFrame);
    vi.stubGlobal('cancelAnimationFrame', cancelFrame);
    render(
      <PrintProvider>
        <PrintControls />
        <PrintProbe />
      </PrintProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Print tab' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(requestFrame).toHaveBeenCalled();
    expect(cancelFrame).toHaveBeenCalledWith(42);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Screen content')).toBeInTheDocument();
    expect(print).not.toHaveBeenCalled();
  });
  it('refuses to print when a decoded chart changes source during preparation', async () => {
    let releaseFonts: () => void = () => {};
    const fonts = new Promise<void>((resolve) => {
      releaseFonts = resolve;
    });
    Object.defineProperty(document, 'fonts', { configurable: true, value: { ready: fonts } });
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    render(
      <PrintProvider>
        <img data-print-chart src="old.png" alt="Chart being prepared" />
        <PrintControls />
      </PrintProvider>,
    );
    const image = screen.getByRole('img') as HTMLImageElement;
    let width = 1;
    image.decode = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(image, 'naturalWidth', { get: () => width });
    Object.defineProperty(image, 'complete', { get: () => width > 0 });
    fireEvent.click(screen.getByRole('button', { name: 'Print tab' }));
    await act(async () => {
      await Promise.resolve();
    });

    // The earlier decode has finished, but the current source has not. A
    // stale readiness promise must never turn a missing chart into a PDF.
    width = 0;
    image.src = 'new-still-loading.png';
    await act(async () => {
      releaseFonts();
      await Promise.resolve();
    });
    expect(print).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Could not prepare every chart');
    expect(screen.getByRole('button', { name: 'Print tab' })).toBeEnabled();
  });
});

describe('Print provenance', () => {
  it('escapes quotes, slashes, and control characters in CSS content strings', () => {
    expect(cssString('code "rev"\\line\n\r\t\0')).toBe(
      '"code \\22 rev\\22 \\5c line\\a \\d \\9 \\0 "',
    );
    expect(cssString('data · revision')).toBe('"data · revision"');
    expect(provenanceLine({ git_sha: null, data_as_of: null }, true)).toBe(
      'data as of unknown · code unknown',
    );
  });

  it('falls back when CSS margin boxes are unavailable', () => {
    vi.stubGlobal(
      'CSSStyleSheet',
      class {
        replaceSync() {
          throw new Error('Unsupported');
        }
      },
    );
    expect(supportsPageMargins()).toBe(false);
    const provenance = { data_as_of: '2026-07-25T21:00:00Z', git_sha: 'abc1234' };
    render(
      <PrintProvider>
        <PrintLayout provenance={provenance}>
          <PrintProbe />
        </PrintLayout>
      </PrintProvider>,
    );
    expect(screen.getByText(/enable headers and footers/)).toBeInTheDocument();
    expect(screen.queryByText(/code abc1234/)).not.toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event('beforeprint'));
    });
    expect(screen.getByText(/code abc1234/)).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event('afterprint'));
    });
    expect(screen.queryByText(/code abc1234/)).not.toBeInTheDocument();
  });
});
