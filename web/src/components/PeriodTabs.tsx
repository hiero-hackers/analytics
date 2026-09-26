/**
 * Rolling-period selector for tables: a segmented bar of windows, shortest
 * first, with "All time" (the null period) at the end of the scale. A
 * single-select ToggleGroup, so it reads as one choice among options.
 */

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

/** The value standing for "no window" — every row, not a rolling period. */
const ALL_TIME = '__all__';

export function PeriodTabs({
  periods,
  active,
  onChange,
  labels,
}: {
  periods: string[];
  active: string | null;
  onChange: (period: string | null) => void;
  /** Display labels per period key ("30d" -> "30 days"). */
  labels?: Record<string, string>;
}) {
  if (periods.length === 0) {
    return null;
  }
  return (
    <ToggleGroup
      type="single"
      spacing={0}
      aria-label="Time range"
      value={active ?? ALL_TIME}
      // "" means the active option was clicked again: keep the window.
      onValueChange={(value) => value && onChange(value === ALL_TIME ? null : value)}
      // One bordered bar: the segmented look that sets it apart from role tabs.
      className="mb-3 max-w-full overflow-x-auto rounded-lg border bg-card p-0.5"
    >
      {periods.map((key) => (
        <ToggleGroupItem key={key} value={key}>
          {labels?.[key] ?? key}
        </ToggleGroupItem>
      ))}
      {/* Last, not first: the windows read shortest to longest (30 days →
          1 year), and all-time is the end of that scale rather than a
          separate mode sitting before it. */}
      <ToggleGroupItem value={ALL_TIME}>All time</ToggleGroupItem>
    </ToggleGroup>
  );
}
