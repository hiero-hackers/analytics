/**
 * Exclusive variant switches for chart tabs, a card's shared role axis and table role tabs.
 * A single-select ToggleGroup rather than Tabs: the choice swaps data inside one card.
 * Separate from `PeriodTabs`, whose "All time" null state has no role-axis equivalent.
 */

import type { ReactNode } from 'react';
import { cn } from 'cn';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

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
  /** `outline` for card and table axes; `segmented` (one muted track) for chart toolbars. */
  appearance?: 'outline' | 'segmented';
  /** Draw these instead of labels; each label stays the accessible name and tooltip. */
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
      // Radix reports "" when the active option is re-clicked; a variant stays selected.
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
