/**
 * The jump bar plus collapsible section groups (legacy `.jump` / `.group`).
 * With a single group, sections render bare — the header would be redundant.
 */

import type { ReactNode } from "react";

export type Group = [name: string, content: ReactNode];

const slug = (name: string) => name.replace(/\W+/g, "-");

export function SectionGroups({ groups }: { groups: Group[] }) {
  const showHeaders = groups.length > 1;
  return (
    <>
      {showHeaders && (
        <div className="jump">
          <span className="jlabel">Jump to</span>
          {groups.map(([name]) => (
            <a key={name} className="jbtn" href={`#grp-${slug(name)}`}>
              {name}
            </a>
          ))}
        </div>
      )}
      {groups.map(([name, content]) =>
        showHeaders ? (
          <details className="group" id={`grp-${slug(name)}`} open key={name}>
            <summary className="grouphdr">{name}</summary>
            {content}
          </details>
        ) : (
          <div key={name}>{content}</div>
        ),
      )}
    </>
  );
}
