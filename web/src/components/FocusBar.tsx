/**
 * The dashboard focus, stated once at the top of the tab: what is focused,
 * what it does and does not change, and how to clear it. It sticks to the
 * top of the page so the reader always knows why a table is shorter.
 */

import { CrosshairIcon, XIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DIMENSION_LABELS, useFocus } from '../focus';

export function FocusBar() {
  const [focus, setFocus] = useFocus();
  if (!focus) return null;
  const noun = DIMENSION_LABELS[focus.dimension];
  return (
    <div
      role="region"
      aria-label="Dashboard focus"
      className="sticky top-2 z-30 mb-6 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-link/40 bg-card px-4 py-2.5 text-sm shadow-sm"
    >
      <CrosshairIcon className="size-4 text-link" aria-hidden="true" />
      <span>
        Focused on {noun} <strong>{focus.value}</strong>
      </span>
      <span className="text-xs text-muted-foreground">
        Tables with a {noun} column are filtered and charts with a {noun} breakdown highlight it;
        everything else still shows the whole organisation.
      </span>
      <Button variant="outline" size="sm" className="ml-auto" onClick={() => setFocus(null)}>
        <XIcon data-icon="inline-start" />
        Clear focus
      </Button>
    </div>
  );
}
