/** The work-in-progress disclaimer footer. */

export function WipFooter() {
  return (
    <footer className="mb-2 max-w-[62ch] text-[13px] leading-normal text-muted">
      <span className="mr-1.5 inline-block rounded bg-warn/20 px-2 py-[2px] text-[11px] font-semibold tracking-[0.04em] uppercase text-warn-ink">
        Work in progress
      </span>{" "}
      This dashboard is under active development. Organisation affiliations are curated and still being
      verified — figures are directional and may change. Spotted something wrong? Use a table&rsquo;s
      &ldquo;Suggest a correction&rdquo; link.
    </footer>
  );
}
