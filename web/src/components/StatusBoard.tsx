/**
 * Entities placed in lifecycle columns (today: HIP specs by governance
 * status). Clicking a chip reveals its title and status in the info bar; the
 * bar's button jumps to the entity's row in the target view (the matrix).
 */

import { useState } from 'react';
import { ArrowDownIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Toggle } from '@/components/ui/toggle';
import type { BoardItem, BoardView } from '../api';
import { usePrintMode } from '../printContext';

export function StatusBoard({ view, onJump }: { view: BoardView; onJump: (hip: number) => void }) {
  const printing = usePrintMode();
  const [picked, setPicked] = useState<BoardItem | null>(null);

  return (
    <>
      <div className="hipboard" hidden={printing} data-print-hide data-scroll-restore>
        {view.columns.map((column) => (
          <div key={column.title} className="hipboard-col">
            <h3>
              {column.title} <span className="n">{column.items.length}</span>
            </h3>
            <div className="hipboard-chips" data-scroll-restore>
              {column.items.length === 0 && <span className="none">none</span>}
              {column.items.map((item) => (
                <Toggle
                  key={item.key}
                  variant="outline"
                  size="sm"
                  className="bg-card font-semibold text-link-ink tabular-nums"
                  title={`${item.title} (${item.status})`}
                  pressed={picked?.key === item.key}
                  onPressedChange={(pressed) => setPicked(pressed ? item : null)}
                >
                  {item.label}
                </Toggle>
              ))}
            </div>
          </div>
        ))}
      </div>
      {/* The scrolling board stays mounted (hidden) so print/cancel keeps its
          scroll and focus; paper gets an ordinary list per status instead. */}
      {printing &&
        view.columns.map((column) => (
          <div key={column.title} className="mb-4">
            <h3 className="text-sm font-semibold">
              {column.title} <span className="text-muted-foreground">{column.items.length}</span>
            </h3>
            <ul className="print-board-list" data-print-board>
              {column.items.length === 0 && <li>None</li>}
              {column.items.map((item) => (
                <li key={item.key}>
                  <strong>{item.label}</strong> — {item.title} ({item.status})
                </li>
              ))}
            </ul>
          </div>
        ))}
      {picked && (
        <div
          hidden={printing}
          data-print-hide
          className="mt-2.5 flex flex-wrap items-center gap-2.5 rounded-lg border px-3 py-2 text-xs"
        >
          <strong className="font-semibold tabular-nums">{picked.label}</strong>
          <span className="text-muted-foreground">{picked.title}</span>
          <Badge variant="info">{picked.status}</Badge>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => onJump(picked.key)}
          >
            Show in coverage matrix
            <ArrowDownIcon data-icon="inline-end" />
          </Button>
        </div>
      )}
    </>
  );
}
