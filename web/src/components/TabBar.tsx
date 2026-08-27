/**
 * A row of exclusive tabs. `kind` selects the visual: "macro" is the pill row
 * for top-level sections, "tab" the underlined row for orgs. (Period tabs are
 * not this component — they carry an "All time" null state.)
 */

export function TabBar({
  items,
  active,
  onSelect,
  kind,
}: {
  items: string[];
  active: string;
  onSelect: (item: string) => void;
  kind: 'macro' | 'tab';
}) {
  return (
    <nav className={kind === 'macro' ? 'macrobar' : 'tabbar'}>
      {items.map((name) => (
        <button
          key={name}
          className={name === active ? `${kind} active` : kind}
          onClick={() => onSelect(name)}
        >
          {name}
        </button>
      ))}
    </nav>
  );
}
