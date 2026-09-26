import { useEffect, useState, type ReactNode } from 'react';
import type { Manifest } from '../api';
import { cssString, provenanceLine, supportsPageMargins } from '../printUtils';
import { usePrintMode } from '../printContext';

export function PrintLayout({
  provenance,
  children,
}: {
  provenance: Manifest['provenance'];
  children: ReactNode;
}) {
  const [marginBoxes] = useState(supportsPageMargins);
  const printing = usePrintMode();
  const line = provenanceLine(provenance, true);
  useEffect(() => {
    document.documentElement.style.setProperty('--print-provenance', cssString(line));
    return () => {
      document.documentElement.style.removeProperty('--print-provenance');
    };
  }, [line]);
  if (marginBoxes) return children;
  // CSS margin boxes are not implemented by Firefox/WebKit. A real table
  // footer reserves space on each sheet; a fixed footer can overlap rows or
  // be clipped outside the page. This wrapper is display:contents on screen
  // and stays mounted throughout printing, so selections cannot reset.
  return (
    <>
      <p data-print-hide className="text-[12px] text-muted">
        For page numbers, enable headers and footers in your browser’s print settings. Chrome and
        Edge also print the document’s own page numbers.
      </p>
      <table role="presentation" data-print-layout>
        <tbody>
          <tr>
            <td>{children}</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td data-print-footer>{printing ? line : null}</td>
          </tr>
        </tfoot>
      </table>
    </>
  );
}
