/** The work-in-progress disclaimer footer. */

export function WipFooter() {
  return (
    <footer className="mt-9 mb-2 border-t border-solid border-edge px-4 py-3.5 text-[13px] leading-normal text-[#777] dark:text-[#999]">
      <span className="mr-1.5 inline-block rounded bg-[#fde68a] px-2 py-[2px] text-[11px] font-semibold tracking-[0.04em] uppercase text-[#92400e] dark:bg-[#78350f] dark:text-[#fde68a]">
        Work in progress
      </span>{" "}
      This dashboard is under active development. Organisation affiliations are curated and still being
      verified — figures are directional and may change. Spotted something wrong? Use a table&rsquo;s
      &ldquo;Suggest a correction&rdquo; link.
    </footer>
  );
}
