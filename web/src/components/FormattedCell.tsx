/**
 * One table cell rendered per the API's column format — the single place the
 * display formats (hip, date, link, evidence, status, flag) live. The HIP
 * views add their formats here rather than growing their own switches.
 */

import { safeUrl } from "../safety";

export function FormattedCell({ value, format }: { value: unknown; format?: string }) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const text = String(value);
  switch (format) {
    case "hip":
      return <span className="cell-hip">HIP-{text}</span>;
    case "date":
      return <>{text.slice(0, 10)}</>;
    case "link": {
      // The href comes from generated data; an unsafe scheme renders as inert
      // text rather than a clickable link.
      const href = safeUrl(text);
      return href ? (
        <a href={href} target="_blank" rel="noopener noreferrer" className="cell-link">
          open ↗
        </a>
      ) : (
        <>{text}</>
      );
    }
    case "evidence": {
      const tone = text === "merged" ? "chip-merged" : text === "open_only" ? "chip-open" : "chip-none";
      return <span className={`chip ${tone}`}>{text.replace("_", " ")}</span>;
    }
    case "status":
      return <span className="chip chip-spec">{text}</span>;
    case "flag":
      return <>{text === "true" || text === "True" ? "✓" : "—"}</>;
    case "presence": {
      // A yes/no column: a labelled chip reads at a glance where a bare tick
      // leaves the reader decoding an empty-looking cell.
      const present = text === "true" || text === "True";
      return (
        <span className={present ? "chip chip-merged" : "chip chip-none"}>{present ? "present" : "missing"}</span>
      );
    }
    default:
      return <>{text}</>;
  }
}
