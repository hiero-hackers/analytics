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

export function StatusBoard({ view, onJump }: { view: BoardView; onJump: (hip: number) => void }) {
  const [picked, setPicked] = useState<BoardItem | null>(null);

  return (
    <>
      <div className="hipboard">
        {view.columns.map((column) => (
          <div key={column.title} className="hipboard-col">
            <h3>
              {column.title} <span className="n">{column.items.length}</span>
            </h3>
            <div className="hipboard-chips">
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
      {picked && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2.5 rounded-lg border px-3 py-2 text-xs">
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
