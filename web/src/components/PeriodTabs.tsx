/** Rolling-period tabs (the `.periodtabs` container rail), for tables and future charts. */

const TAB =
  "-mb-px cursor-pointer border-0 border-b-2 border-solid bg-transparent px-3 py-1.5 text-[13px] [font:inherit]";
const IDLE = `${TAB} border-transparent text-muted hover:text-ink`;
const ACTIVE = `${TAB} border-[#555] font-semibold text-ink dark:border-[#888]`;

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
    <div className="periodtabs">
      <button className={active === null ? ACTIVE : IDLE} onClick={() => onChange(null)}>
        All time
      </button>
      {periods.map((key) => (
        <button key={key} className={active === key ? ACTIVE : IDLE} onClick={() => onChange(key)}>
          {labels?.[key] ?? key}
        </button>
      ))}
    </div>
  );
}
