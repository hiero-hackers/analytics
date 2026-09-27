/**
 * A row of exclusive variant switches: a chart's own tabs, a card's shared
 * role axis, and a table's role tabs — one component so the three cannot drift
 * into three styles. A single-select ToggleGroup (radiogroup/radio to
 * assistive tech): the choice swaps the data inside one card rather than
 * showing separate panels, so it is not a Tabs widget.
 *
 * Deliberately *not* `PeriodTabs`: that carries an "All time" null state, which
 * a role axis has no equivalent of (there is no "all roles" table). The two
 * also look different — separate outlined options here, one segmented bar
 * there — so a reader can tell the axes apart on a table that has both.
 */

import type { ReactNode } from 'react';
import { cn } from 'cn';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

/**
 * `outline` (the default): separate outlined options, for a card's own axis
 * and a table's role tabs. `segmented`: one muted track with the active
 * option lifted onto the card surface, for a chart's toolbar, where several
 * small switches sit side by side and must read as one row of settings rather
 * than a stack of button groups.
 */
export function VariantTabs({
  labels,
  active,
  onSelect,
  ariaLabel,
  appearance = 'outline',
  icons,
  className,
}: {
  labels: string[];
  active: number;
  onSelect: (index: number) => void;
  ariaLabel: string;
  appearance?: 'outline' | 'segmented';
  /** Draw these instead of the labels; each label stays the option's accessible name and tooltip. */
  icons?: ReactNode[];
  className?: string;
}) {
  if (labels.length < 2) {
    return null;
  }
  if (appearance === 'segmented') {
    return (
      <ToggleGroup
        type="single"
        spacing={0}
        aria-label={ariaLabel}
        value={String(active)}
        onValueChange={(value) => value && onSelect(Number(value))}
        className={cn('max-w-full flex-wrap rounded-lg bg-muted p-0.5', className)}
      >
        {labels.map((label, index) => (
          <ToggleGroupItem
            key={label}
            value={String(index)}
            aria-label={icons ? label : undefined}
            title={icons ? label : undefined}
            className="h-7 rounded-md border-0 bg-transparent px-2.5 text-xs font-medium text-muted-foreground shadow-none hover:bg-transparent hover:text-foreground data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-xs"
          >
            {icons ? icons[index] : label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    );
  }
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      aria-label={ariaLabel}
      value={String(active)}
      // Radix reports "" when the active option is clicked again; a variant is
      // always selected, so that click changes nothing.
      onValueChange={(value) => value && onSelect(Number(value))}
      className={cn('mb-3 max-w-full flex-wrap', className)}
    >
      {labels.map((label, index) => (
        <ToggleGroupItem key={label} value={String(index)}>
          {label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
