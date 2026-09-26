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

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

export function VariantTabs({
  labels,
  active,
  onSelect,
  ariaLabel,
}: {
  labels: string[];
  active: number;
  onSelect: (index: number) => void;
  ariaLabel: string;
}) {
  if (labels.length < 2) {
    return null;
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
      className="mb-3 max-w-full flex-wrap"
    >
      {labels.map((label, index) => (
        <ToggleGroupItem key={label} value={String(index)}>
          {label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
