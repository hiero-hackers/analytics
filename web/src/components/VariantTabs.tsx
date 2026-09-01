/**
 * A row of exclusive variant tabs, in the existing `.charttabs` / `.ctab`
 * vocabulary. Used for a chart's own tabs, for a card's shared role axis, and
 * for a table's role tabs — one component so the three cannot drift into three
 * tab styles.
 *
 * Deliberately *not* `PeriodTabs`: that carries an "All time" null state, which
 * a role axis has no equivalent of (there is no "all roles" table). Keeping the
 * two visually distinct is also what lets a reader tell the axes apart on a
 * table that has both.
 */

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
    <div className="charttabs" role="group" aria-label={ariaLabel}>
      {labels.map((label, index) => (
        <button
          key={label}
          type="button"
          className={index === active ? 'ctab active' : 'ctab'}
          aria-pressed={index === active}
          onClick={() => onSelect(index)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
