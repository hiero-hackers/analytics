/**
 * The click-through behind a coverage-matrix cell: every referencing PR for
 * one (entity, repository) pair, qualified references included and flagged —
 * the panel exists so each cell's count is independently checkable.
 */

import { useEffect } from 'react';
import { XIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
    <div className="mt-3 rounded-lg border p-3">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-2.5">
        {/* "HIP-1200 · repo": the pair the evidence is for — an identifier, not a meta string. */}
        <h3 className="text-sm font-semibold">
          HIP-{hip} · {repo}
        </h3>
        <span className="text-xs text-soft">
          {items.length} referencing PR{items.length > 1 ? 's' : ''}
        </span>
        <Button type="button" variant="outline" size="sm" className="ml-auto" onClick={onClose}>
          <XIcon data-icon="inline-start" />
          Close
        </Button>
      </div>
      <ol className="max-h-[300px] overflow-y-auto">
        {items.map((item) => {
          const href = safeUrl(`https://github.com/${repo}/pull/${item.n}`);
          return (
            <li key={item.n} className="border-b border-row-line py-1.5 text-xs last:border-b-0">
              <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold text-link tabular-nums underline-offset-4 hover:underline"
                  >
                    #{item.n}
                  </a>
                ) : (
                  <span className="font-semibold tabular-nums">#{item.n}</span>
                )}
                <span className="text-muted-foreground">{item.t}</span>
                <span className="whitespace-nowrap text-soft">
                  {item.st === 'MERGED' ? `merged ${item.d}` : item.st.toLowerCase()}
                </span>
                <span className="whitespace-nowrap text-soft">
                  matched in: {item.m.split('|').join(', ')}
                </span>
                {item.q && <Badge variant="warn">not counted — “{item.q}”</Badge>}
              </div>
              {/* The matched text itself: a literal excerpt of the PR, so monospace. */}
              {item.x && (
                <div className="mt-0.5 truncate font-mono text-[11px] text-soft">{item.x}</div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
