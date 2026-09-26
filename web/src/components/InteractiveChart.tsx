/**
 * The interactive replacement for a chart PNG: loads one `ChartDocument` the
 * exporter publishes (export/chart_data.py) and hands it to the view for its
 * kind. Every view shares `ChartShell` — Chart / Data, CSV of the selected
 * rows, the expanded dialog and the explanatory footer — so migrating another
 * chart is a spec declaration, not a new component.
 *
 * A failed load offers Retry and keeps the PNG (when one exists) in view.
 */

import { useEffect, useState } from 'react';
import { RotateCwIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ChartDocument, ChartVariant, Manifest } from '../api';
import { fetchChartDocument } from '../chartData';
import { EventsView } from './charts/EventsView';
import { MatrixView } from './charts/MatrixView';
import { NetworkView } from './charts/NetworkView';
import { SeriesView } from './charts/SeriesView';

function View({
  data,
  ...props
}: {
  data: ChartDocument;
  title: string;
  period: string;
  provenance: Manifest['provenance'];
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
  fallback,
}: {
  variant: ChartVariant;
  title: string;
  provenance: Manifest['provenance'];
  fallback?: React.ReactNode;
}) {
  const path = variant.interactive!.path;
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
  if (result?.path !== path)
    return (
      <div
        role="status"
        className="flex h-[340px] items-center justify-center text-sm text-muted-foreground"
      >
        Loading interactive chart…
      </div>
    );
  if (!result.data)
    return (
      <div>
        <div
          role="alert"
          className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border p-4 text-sm"
        >
          Interactive data could not be loaded.
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
        {fallback}
      </div>
    );
  return (
    <View
      key={path}
      data={result.data}
      title={title}
      period={variant.label}
      provenance={provenance}
    />
  );
}
