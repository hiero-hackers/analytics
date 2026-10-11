import { useEffect, useMemo, useState } from 'react';

import type { CIHealthMatrixView, CIHealthCell } from '../api';
import { CIHealthEvidencePanel } from './CIHealthEvidencePanel';

const STATUS_LABELS: Record<CIHealthCell['status'], string> = {
  pass: 'pass',
  fail: 'fail',
  review: 'review',
  na: 'not applicable',
};

function cellClass(status: CIHealthCell['status']): string {
  return `cimx-cell cimx-${status}`;
}

function haystack(row: CIHealthMatrixView['rows'][number]): string {
  return [
    row.label,
    ...row.cells.map((cell) => `${cell.label} ${cell.status} ${cell.evidence} ${cell.location}`),
  ]
    .join(' ')
    .toLowerCase();
}

export function CIHealthMatrix({
  view,
  onFilteredRows,
}: {
  view: CIHealthMatrixView;
  onFilteredRows?: (viewId: string, rows: CIHealthMatrixView['rows']) => void;
}) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<{
    repo: string;
    cell: CIHealthCell;
  } | null>(null);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();

    return view.rows.filter(
      (row) =>
        (status === '' || row.cells.some((cell) => cell.status === status)) &&
        (needle === '' || haystack(row).includes(needle)),
    );
  }, [view.rows, query, status]);

  useEffect(() => {
    onFilteredRows?.(view.id, rows);
  }, [onFilteredRows, rows, view.id]);

  const toggleCell = (repo: string, cell: CIHealthCell) => {
    if (cell.status === 'pass' || cell.status === 'na') {
      return;
    }

    setSelected((current) =>
      current?.repo === repo && current.cell.key === cell.key ? null : { repo, cell },
    );
  };

  const bands = view.bands ?? [];
  const bandHeader = bands.length > 0;

  return (
    <>
      <div className="cimx-filters">
        <input
          className="search"
          aria-label="Filter CI health by repository or check"
          placeholder="Filter by repository or check…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />

        <div className="cimx-fbar">
          <span>Has status:</span>

          {view.filters.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={status === option}
              className={option === status ? 'cimx-fbtn active' : 'cimx-fbtn'}
              onClick={() => setStatus((current) => (current === option ? '' : option))}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="cimx-wrap">
        <table className={bandHeader ? 'cimx cimx-banded' : 'cimx'}>
          <thead>
            {bandHeader && (
              <tr className="cimx-band">
                <th scope="col" aria-label="Blank header cell" />
                {bands.map((band) => (
                  <th key={band.label} scope="col" colSpan={band.span}>
                    {band.label}
                  </th>
                ))}
              </tr>
            )}

            <tr>
              <th scope="col">{view.row_header}</th>
              {view.columns.map((column) => (
                <th key={column.key} scope="col">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <th scope="row">{row.label}</th>

                {row.cells.map((cell) => {
                  const clickable = cell.status === 'fail' || cell.status === 'review';
                  const ariaLabel = `${row.label} — ${cell.label}: ${STATUS_LABELS[cell.status]}`;
                  const isSelected = selected?.repo === row.key && selected.cell.key === cell.key;

                  return (
                    <td
                      key={cell.key}
                      className={`${cellClass(cell.status)}${isSelected ? ' selected' : ''}`}
                      title={clickable ? `${cell.status}: click for evidence` : cell.status}
                      aria-label={ariaLabel}
                      {...(clickable && {
                        onClick: () => toggleCell(row.key, cell),
                        onKeyDown: (event: React.KeyboardEvent) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            toggleCell(row.key, cell);
                          }
                        },
                        tabIndex: 0,
                        role: 'button',
                      })}
                    >
                      {cell.status === 'na' ? '—' : cell.status}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="cimx-legend">
        <span>
          <i className="cimx-cell cimx-pass" /> pass
        </span>
        <span>
          <i className="cimx-cell cimx-fail" /> fail
        </span>
        <span>
          <i className="cimx-cell cimx-review" /> review
        </span>
        <span>
          <i className="cimx-cell cimx-na" /> na
        </span>
        <span>· click fail/review cells for evidence</span>
      </div>

      {selected && (
        <CIHealthEvidencePanel
          repo={selected.repo}
          cell={selected.cell}
          onClose={() => setSelected(null)}
        />
      )}

      <p className="count">{rows.length} repositories</p>
    </>
  );
}
