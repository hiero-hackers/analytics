/**
 * The shared "how to read this" column glossary, rendered from the manifest's
 * term/definition data. Definitions may mark emphasis with *asterisks* — the
 * only inline markup the glossary contract allows.
 */

import { Fragment } from "react";
import type { Glossary as GlossaryData } from "../api";
import { emphasized } from "../markup";

export function Glossary({ glossary }: { glossary: GlossaryData }) {
  if (glossary.layout === "notes") {
    // Interpretation notes (e.g. the HIPs tab's HIP-1 reading rules): bolded
    // lead-ins with prose, not the term/definition grid.
    return (
      <details className="glossary">
        <summary>{glossary.title}</summary>
        <ul className="hipabout">
          {glossary.terms.map(({ term, definition }) => (
            <li key={term}>
              <strong>{term}</strong> {emphasized(definition)}
            </li>
          ))}
        </ul>
      </details>
    );
  }
  return (
    <details className="glossary">
      <summary>{glossary.title}</summary>
      <dl>
        {glossary.terms.map(({ term, definition }) => (
          <Fragment key={term}>
            <dt>{term}</dt>
            <dd>{emphasized(definition)}</dd>
          </Fragment>
        ))}
      </dl>
      {glossary.note && <p className="gnote">{glossary.note}</p>}
    </details>
  );
}
