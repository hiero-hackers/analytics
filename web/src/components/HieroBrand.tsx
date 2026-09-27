/** Official assets from hiero-ledger/hiero-website; see public/brand/README.md. */
export function HieroBrand({ compact = false }: { compact?: boolean }) {
  const base = import.meta.env.BASE_URL;
  return (
    <div className="flex shrink-0 items-center gap-3" aria-label="Hiero analytics">
      <span className="sr-only">Hiero analytics</span>
      <img
        src={`${base}brand/hiero-logo.svg`}
        alt=""
        width={112}
        height={35}
        className="h-auto w-[90px] dark:hidden sm:w-28"
      />
      <img
        src={`${base}brand/hiero-logo-dark.svg`}
        alt=""
        width={112}
        height={35}
        className="hidden h-auto w-[90px] dark:block sm:w-28"
      />
      {!compact && (
        <span
          aria-hidden="true"
          className="hidden border-l pl-3 text-[11px] font-semibold tracking-[0.14em] text-muted-foreground min-[1100px]:block"
        >
          ANALYTICS
        </span>
      )}
    </div>
  );
}
