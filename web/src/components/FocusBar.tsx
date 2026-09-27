/**
 * The dashboard focus, stated once at the top of the tab: what is focused,
 * what it does and does not change, and how to clear it. On wide screens it
 * docks under the sticky header, so the reader always knows why a table is
 * shorter without it ever covering the header's controls. On phones the
 * group strip already holds that place, so the bar stays in the page flow.
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
      className="z-20 mb-6 flex flex-wrap items-center gap-x-3 gap-y-1 overflow-hidden rounded-lg border border-link/30 bg-card/95 py-2 pr-2 pl-4 text-sm shadow-sm backdrop-blur-xl md:sticky md:top-[calc(var(--header-h)+0.75rem)] relative before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-link"
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
