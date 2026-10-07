import type { ReactNode } from 'react';

/** A setting or selection stated on a printed chart: "Chart style Bars". */
export function PrintFilter({ label, value }: { label: string; value: ReactNode }) {
  return (
    <p
      data-print-filter
      className="inline-flex max-w-full items-baseline gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] leading-snug"
    >
      <span className="text-muted-foreground">{label}</span>{' '}
      <span className="font-medium text-foreground">{value}</span>
    </p>
  );
}
