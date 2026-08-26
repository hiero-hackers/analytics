/**
 * The click-through behind a coverage-matrix cell: every referencing PR for
 * one (entity, repository) pair, qualified references included and flagged —
 * the panel exists so each cell's count is independently checkable.
 */

import { useEffect } from 'react';
import { safeUrl } from '../safety';

/** One evidence line, in the legacy panel's field order. */
export interface EvidenceItem {
  n: number;
  t: string;
  st: string;
  d: string;
  m: string;
  q: string;
  x: string;
}

export function EvidencePanel({
  hip,
  repo,
  items,
  onClose,
}: {
  hip: number;
  repo: string;
  items: EvidenceItem[];
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="hipev">
      <div className="hipev-head">
        <h3>
          HIP-{hip} · {repo}
        </h3>
        <span className="n">
          {items.length} referencing PR{items.length > 1 ? 's' : ''}
        </span>
        <button type="button" className="dl" onClick={onClose}>
          Close
        </button>
      </div>
      <ol>
        {items.map((item) => {
          const href = safeUrl(`https://github.com/${repo}/pull/${item.n}`);
          return (
            <li key={item.n}>
              <div className="l1">
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    #{item.n}
                  </a>
                ) : (
                  <span>#{item.n}</span>
                )}
                <span className="t">{item.t}</span>
                <span className="meta">
                  {item.st === 'MERGED' ? `merged ${item.d}` : item.st.toLowerCase()}
                </span>
                <span className="meta">matched in: {item.m.split('|').join(', ')}</span>
                {item.q && <span className="cue">not counted — “{item.q}”</span>}
              </div>
              {item.x && <div className="snip">{item.x}</div>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
