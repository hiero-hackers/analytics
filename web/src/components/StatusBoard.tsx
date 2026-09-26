/**
 * Entities placed in lifecycle columns (today: HIP specs by governance
 * status). Clicking a chip reveals its title and status in the info bar; the
 * bar's button jumps to the entity's row in the target view (the matrix).
 */

import { useState } from 'react';
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
                <button
                  key={item.key}
                  type="button"
                  className={picked?.key === item.key ? 'hipchip active' : 'hipchip'}
                  title={`${item.title} · ${item.status}`}
                  onClick={() => setPicked((current) => (current?.key === item.key ? null : item))}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {/* Keep the scrolling board mounted so print/cancel preserves its
          scroll and focus, while paper gets an ordinary list per status. */}
      {printing &&
        view.columns.map((column) => (
          <div key={column.title} className="mb-4">
            <h3>
              {column.title} <span className="n">{column.items.length}</span>
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
        <div className="hipboard-info" hidden={printing} data-print-hide>
          <strong>{picked.label}</strong>
          <span className="t">{picked.title}</span>
          <span className="chip chip-spec">{picked.status}</span>
          <button type="button" className="dl" onClick={() => onJump(picked.key)}>
            Show in coverage matrix ↓
          </button>
        </div>
      )}
    </>
  );
}
