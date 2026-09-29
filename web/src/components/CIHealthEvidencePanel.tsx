import { useEffect } from 'react';

import type { CIHealthCell } from '../api';

export function CIHealthEvidencePanel({
  repo,
  cell,
  onClose,
}: {
  repo: string;
  cell: CIHealthCell;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const locations = cell.location
    .split(';')
    .map((location) => location.trim())
    .filter(Boolean);

  return (
    <div className="cimx-evidence">
      <div className="cimx-evidence-head">
        <div>
          <h3>{repo}</h3>
          <span className={`cimx-status ${cell.status}`}>{cell.status}</span>
        </div>

        <button type="button" className="dl" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="cimx-evidence-body">
        <h4>{cell.label}</h4>

        <p>{cell.evidence}</p>

        {locations.length > 0 && (
          <>
            <h4>Locations</h4>
            <ul>
              {locations.map((location) => (
                <li key={location}>
                  <code>{location}</code>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
