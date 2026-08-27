/** Rolling-period selector for tables and future charts. */

const TAB =
  'cursor-pointer whitespace-nowrap rounded-md border-0 px-3 py-1.5 text-[13px] [font:inherit]';
const IDLE = `${TAB} bg-transparent text-muted hover:bg-raise hover:text-ink`;
const ACTIVE = `${TAB} bg-accent font-semibold text-on-accent shadow-sm`;

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
    <div
      className="mb-3 flex w-fit max-w-full gap-1 overflow-x-auto rounded-lg border border-solid border-edge bg-page p-1"
      role="group"
      aria-label="Time range"
    >
      {periods.map((key) => (
        <button
          key={key}
          type="button"
          className={active === key ? ACTIVE : IDLE}
          aria-pressed={active === key}
          onClick={() => onChange(key)}
        >
          {labels?.[key] ?? key}
        </button>
      ))}
      {/* Last, not first: the windows read shortest to longest (30 days →
          1 year), and all-time is the end of that scale rather than a
          separate mode sitting before it. */}
      <button
        type="button"
        className={active === null ? ACTIVE : IDLE}
        aria-pressed={active === null}
        onClick={() => onChange(null)}
      >
        All time
      </button>
    </div>
  );
}
