/**
 * A stateless placeholder standing in for content that hasn't arrived yet —
 * used both for the very first manifest fetch and for a tab switch, so
 * loading always reads the same rather than flickering between shapes.
 */

export function Skeleton({ label, rows = 4 }: { label: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className="my-3">
      <div aria-hidden="true" className="flex flex-col gap-2">
        {Array.from({ length: rows }, (_, index) => (
          <div
            key={index}
            className="h-[27px] animate-pulse rounded bg-raise"
            style={{ width: `${85 - index * 6}%` }}
          />
        ))}
      </div>
    </div>
  );
}
