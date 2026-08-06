/**
 * The jump bar plus collapsible section groups (legacy `.jump` / `.group`).
 * With a single group, sections render bare — the header would be redundant.
 */

import type { ReactNode } from "react";

export type Group = [name: string, content: ReactNode];

// Position-qualified so two groups can never collide on a key or an anchor —
// distinct names can slug to the same string ("Roles & teams" / "Roles teams"),
// and a name could in principle repeat.
const anchorId = (name: string, index: number) => `grp-${index}-${name.replace(/\W+/g, "-")}`;

export function SectionGroups({ groups }: { groups: Group[] }) {
  const showHeaders = groups.length > 1;
  return (
    <>
      {showHeaders && (
        <div className="jump">
          <span className="jlabel">Jump to</span>
          {groups.map(([name], index) => (
            // Deliberately NOT an <a href="#…">: the URL hash is the app's
            // state store (tab/org via useHashState), and fragment navigation
            // would overwrite it — resetting the active tab (#342). Scrolling
            // programmatically leaves the hash, and therefore the tab, alone.
            <button
              key={anchorId(name, index)}
              type="button"
              className="jbtn"
              onClick={() => document.getElementById(anchorId(name, index))?.scrollIntoView()}
            >
              {name}
            </button>
          ))}
        </div>
      )}
      {groups.map(([name, content], index) =>
        showHeaders ? (
          <details className="group" id={anchorId(name, index)} open key={anchorId(name, index)}>
            <summary className="grouphdr">{name}</summary>
            {content}
          </details>
        ) : (
          <div key={anchorId(name, index)}>{content}</div>
        ),
      )}
    </>
  );
}
