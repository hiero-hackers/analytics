/**
 * A chart axis label that opens its repository's or contributor's detail view.
 * Plain text, styled like any other tick, when the name has none.
 */

import { useEntityLink, type EntityKind } from '../../entities';

export function EntityTick({
  x,
  y,
  textAnchor = 'end',
  fontSize,
  kind,
  name,
  label,
}: {
  x: number;
  y: number;
  textAnchor?: 'start' | 'middle' | 'end' | 'inherit';
  /** The axis's own label size, when it sets one (a dense printed ranking). */
  fontSize?: number | string;
  kind: EntityKind | null;
  /** The full name the link resolves. */
  name: string;
  /** What the axis shows (a shortened name, a count beside it). */
  label: string;
}) {
  const link = useEntityLink(kind, name);
  const text = (
    <text
      x={x}
      y={y}
      dy="0.355em"
      textAnchor={textAnchor}
      fontSize={fontSize}
      fill="var(--muted)"
      // Recharts' own label class: the printed sheet finds its row breaks by it (chartPrint.breakPoints).
      className={`recharts-cartesian-axis-tick-value${link ? ' underline-offset-2 hover:fill-(--link) hover:underline' : ''}`}
    >
      {label}
    </text>
  );
  if (!link) return text;
  return (
    <a href={link.href} aria-label={`Open the details for ${name}`}>
      <title>{`Open the details for ${name}`}</title>
      {text}
    </a>
  );
}
