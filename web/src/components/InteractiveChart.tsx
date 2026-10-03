/**
 * Loads one exported `ChartDocument` (export/chart_data.py) and renders the view
 * for its kind. A failed load offers Retry; chart images are never substituted.
 */

import { useEffect, useState } from 'react';
import { RotateCwIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ChartDocument, ChartVariant, Manifest } from '../api';
import { fetchChartDocument } from '../chartData';
import { chartViewName } from '../format';
import { EventsView } from './charts/EventsView';
import { MatrixView } from './charts/MatrixView';
import { NetworkView } from './charts/NetworkView';
import { SeriesView } from './charts/SeriesView';
import { ChartLeading } from './charts/leading';

function View({
  data,
  ...props
}: {
  data: ChartDocument;
  title: string;
  period: string;
  provenance: Manifest['provenance'];
  roomy?: boolean;
}) {
  switch (data.kind) {
    case 'matrix':
      return <MatrixView data={data} {...props} />;
    case 'network':
      return <NetworkView data={data} {...props} />;
    case 'events':
      return <EventsView data={data} {...props} />;
    default:
      return <SeriesView data={data} {...props} />;
  }
}

export default function InteractiveChart({
  variant,
  title,
  provenance,
  roomy,
  leading,
}: {
  variant: ChartVariant;
  title: string;
  provenance: Manifest['provenance'];
  /** Taller than its peers (a gallery's lead): rankings show more rows. */
  roomy?: boolean;
  /** The container's own switches (the card's period tabs), placed first in the toolbar. */
  leading?: React.ReactNode;
}) {
  const path = variant.interactive.path;
  const [result, setResult] = useState<{
    path: string;
    data?: ChartDocument;
    error?: boolean;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    fetchChartDocument(path)
      .then((data) => {
        if (active) setResult({ path, data });
      })
      .catch(() => {
        if (active) setResult({ path, error: true });
      });
    return () => {
      active = false;
    };
  }, [path, attempt]);
  // Keep the container's switches reachable while loading or failed, so a reader can switch period.
  const lead = leading ? <div className="mb-3">{leading}</div> : null;
  if (result?.path !== path)
    return (
      <>
        {lead}
        <div
          role="status"
          // Print preparation waits until no chart is pending.
          data-print-pending
          className="flex h-[340px] items-center justify-center text-sm text-muted-foreground"
        >
          Loading interactive chart: {chartViewName(title, variant.label)}…
        </div>
      </>
    );
  if (!result.data)
    return (
      <div>
        {lead}
        <div
          role="alert"
          data-print-error
          className="print-chart-status mb-4 flex flex-wrap items-center gap-3 rounded-lg border p-4 text-sm"
        >
          Could not load chart data: {chartViewName(title, variant.label)}.
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setResult(null);
              setAttempt((n) => n + 1);
            }}
          >
            <RotateCwIcon />
            Retry chart
          </Button>
        </div>
      </div>
    );
  return (
    <ChartLeading.Provider value={leading}>
      <View
        key={path}
        data={result.data}
        title={title}
        period={variant.label}
        provenance={provenance}
        roomy={roomy}
      />
    </ChartLeading.Provider>
  );
}
