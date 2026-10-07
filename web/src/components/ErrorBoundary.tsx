/**
 * Render-error containment. A section that throws — most often from view state in
 * a hand-edited share link — collapses to a named notice instead of unmounting the
 * whole app; the root boundary is the last resort for anything outside a section.
 */

import { Component, type ReactNode } from 'react';
import { CircleAlertIcon, RotateCwIcon } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { clearParams } from '../urlState';

type Props = {
  children: ReactNode;
  /** Renders in place of the children once they throw; `reset` re-renders them. */
  fallback: (reset: () => void) => ReactNode;
};

export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  reset = () => this.setState({ failed: false });

  render() {
    return this.state.failed ? this.props.fallback(this.reset) : this.props.children;
  }
}

/** One section's boundary; resetting drops the section's view state from the URL first. */
export function SectionBoundary({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <ErrorBoundary
      fallback={(reset) => (
        <Alert variant="destructive" className="mb-6">
          <CircleAlertIcon />
          <AlertTitle>Could not display {title}.</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-2">
            <p>
              The view saved in this link may be out of date. The rest of the page is unaffected.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                clearParams(id);
                reset();
              }}
            >
              <RotateCwIcon data-icon="inline-start" />
              Reset this view
            </Button>
          </AlertDescription>
        </Alert>
      )}
    >
      {children}
    </ErrorBoundary>
  );
}

/** The app-wide boundary: a reload is the only generic recovery left at this level. */
export function RootBoundary({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary
      fallback={() => (
        <main className="mx-auto max-w-xl p-6">
          <Alert variant="destructive">
            <CircleAlertIcon />
            <AlertTitle>Something went wrong displaying the dashboard.</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2">
              <p>Reloading without the view saved in the link usually fixes it.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  window.location.hash = '';
                  window.location.reload();
                }}
              >
                <RotateCwIcon data-icon="inline-start" />
                Reload
              </Button>
            </AlertDescription>
          </Alert>
        </main>
      )}
    >
      {children}
    </ErrorBoundary>
  );
}
