/**
 * The analytics dashboard, driven entirely by the data-API manifest. The shell
 * is a sticky header (wordmark, org switcher, freshness, theme), a sidebar of
 * tabs with the active tab's table of contents, and the tab itself: metric
 * tiles, the "how to read this" glossary, then collapsible section groups of
 * views, chart-section cards and tables.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { SidebarInset, SidebarProvider, useSidebar } from '@/components/ui/sidebar';
import { fetchManifest, type ChartSection, type Manifest } from './api';
import { AppHeader, Freshness } from './components/AppHeader';
import { AppSidebar } from './components/AppSidebar';
import { ChartSectionCard } from './components/ChartSectionCard';
import { Glossary } from './components/Glossary';
import { MetricTiles } from './components/MetricTiles';
import { ProvenanceFooter } from './components/ProvenanceFooter';
import { SectionGroups } from './components/SectionGroups';
import { SectionTable } from './components/SectionTable';
import { Skeleton } from './components/Skeleton';
import { WipFooter } from './components/WipFooter';
import { navModel, type NavModel } from './nav';
import { tocEntries, type Group, type TocEntry } from './toc';
import { useHashState } from './useHashState';
import { useSectionDocs } from './useSectionDocs';
import { useViewDocs } from './useViewDocs';
import { ViewCards } from './components/ViewCards';

const FLASH_MS = 1800; // shared link jump: flash the target for this long, then remove the highlight

function OrgPanel({
  org,
  manifest,
  macro,
  onToc,
}: {
  org: string;
  manifest: Manifest;
  macro: string;
  /** Reports this tab's table of contents to the sidebar (empty while loading). */
  onToc: (entries: TocEntry[]) => void;
}) {
  const entry = manifest.orgs[org];
  // An absorbed section is a role variant another card renders as a tab. Its
  // document still exists (v1 may not withdraw an id), but its rows travel
  // inside the absorbing card, so fetching it would only duplicate the card.
  const refs = useMemo(
    () =>
      (entry.sections ?? []).filter((section) => section.macro === macro && !section.absorbed_by),
    [entry, macro],
  );
  // …and a link to one still has to land: `#widget=committeraffiliations`
  // resolves to the card that absorbed it, which then activates that tab.
  const absorbedInto = useMemo(
    () =>
      Object.fromEntries(
        (entry.sections ?? [])
          .filter((section) => section.absorbed_by)
          .map((section) => [section.id, section.absorbed_by as string]),
      ),
    [entry],
  );
  const viewRefs = useMemo(
    () => (entry.views ?? []).filter((view) => view.macro === macro),
    [entry, macro],
  );
  const { docs, failed, loading: docsLoading } = useSectionDocs(refs);
  const { views, failed: failedViews, loading: viewsLoading } = useViewDocs(viewRefs);
  const unavailable = [...failedViews, ...failed];

  const chartSections = (entry.chart_sections ?? []).filter((section) => section.macro === macro);
  const provenance = manifest.provenance;
  // A shared section link names its target here; see the effect below.
  const [widget] = useHashState('widget', '');

  // The tab is a sequence of named sections: each group renders its views,
  // then its chart cards, then its tables, and the jump bar links each one —
  // there is no generic "Charts" section. Order comes from the manifest's
  // group_order; anything it doesn't mention (older manifest, ad-hoc group)
  // is appended in order of appearance. Groups with nothing to show for this
  // org are dropped entirely.
  //
  // Held back until views and tables settle: sections would otherwise paint
  // partially and then reshuffle as the async pieces arrive. A brief wait for
  // the whole tab in its final order beats content that moves.
  const chartGroup = (section: ChartSection) => section.group || section.title;
  const declaredOrder = manifest.group_order?.[macro] ?? [];
  const names = [...declaredOrder];
  for (const section of chartSections) {
    if (!names.includes(chartGroup(section))) names.push(chartGroup(section));
  }
  for (const doc of docs) {
    if (!names.includes(doc.group || '')) names.push(doc.group || '');
  }
  const settled = !viewsLoading && !docsLoading;
  // A shared #widget=<section id> link: once the tab settles, scroll to and flash that section
  const flashTimer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!settled || !widget) return;
    const jump = () => {
      const target = document.getElementById(absorbedInto[widget] ?? widget);
      target?.scrollIntoView({ block: 'start', behavior: 'smooth' });
      target?.classList.add('flash');
      if (flashTimer.current) window.clearTimeout(flashTimer.current);
      flashTimer.current = window.setTimeout(() => target?.classList.remove('flash'), FLASH_MS);
    };
    const canRequestFrame = typeof window.requestAnimationFrame === 'function';
    const raf = canRequestFrame ? window.requestAnimationFrame(jump) : undefined;
    if (raf === undefined) jump();
    return () => {
      if (typeof window.cancelAnimationFrame === 'function' && raf !== undefined) {
        window.cancelAnimationFrame(raf as number);
      }
      if (flashTimer.current) window.clearTimeout(flashTimer.current);
      document.getElementById(absorbedInto[widget] ?? widget)?.classList.remove('flash');
    };
  }, [settled, widget, absorbedInto]);
  const groups: Group[] = !settled
    ? []
    : names.flatMap((name): Group[] => {
        const groupViews = views.filter((view) => (view.group ?? names[0]) === name);
        const groupCharts = chartSections.filter((section) => chartGroup(section) === name);
        const groupDocs = docs.filter((doc) => (doc.group || '') === name);
        if (!groupViews.length && !groupCharts.length && !groupDocs.length) return [];
        return [
          [
            name,
            <>
              {groupViews.length > 0 && (
                <ViewCards views={groupViews} sectionDocs={docs} provenance={provenance} />
              )}
              {groupCharts.map((section) => (
                <ChartSectionCard key={section.id} section={section} provenance={provenance} />
              ))}
              {groupDocs.map((doc) => (
                <SectionTable
                  key={doc.id}
                  doc={doc}
                  provenance={provenance}
                  periodLabels={manifest.period_labels}
                />
              ))}
            </>,
          ],
        ];
      });

  // The sidebar's "On this page" lists these groups; keyed by content so a
  // re-render with the same groups doesn't re-report them.
  const toc = tocEntries(groups);
  const tocKey = JSON.stringify(toc);
  useEffect(() => {
    onToc(toc);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tocKey is toc's identity
  }, [tocKey, onToc]);
  useEffect(() => () => onToc([]), [onToc]);

  return (
    <>
      <MetricTiles tiles={entry.metrics?.[macro] ?? []} />
      {/* A section that could not load leaves a named gap rather than blanking
          the tab — the rest of the page is still worth reading. */}
      {unavailable.length > 0 && (
        <p className="error">
          Could not load {unavailable.length === 1 ? 'this section' : 'these sections'}:{' '}
          {unavailable.join(', ')}. Everything else on this tab is unaffected — reload to try again.
        </p>
      )}
      {settled ? <SectionGroups groups={groups} /> : <Skeleton label="Loading tab" rows={6} />}
    </>
  );
}

/** Human-readable fatal error: retry button up front, raw cause tucked away. */
function FatalError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="my-6">
      <p className="error">
        Failed to load the dashboard data. This is usually temporary — try again in a moment.
      </p>
      <button type="button" className="dl mt-2" onClick={onRetry}>
        Retry
      </button>
      <details className="mt-3 text-[13px] text-muted-foreground">
        <summary className="cursor-pointer">Error details</summary>
        <pre className="mt-2 whitespace-pre-wrap break-all">{message}</pre>
      </details>
    </div>
  );
}

/** The active tab, for the org selected in the header. */
function Dashboard({
  manifest,
  nav,
  onToc,
}: {
  manifest: Manifest;
  nav: NavModel;
  onToc: (entries: TocEntry[]) => void;
}) {
  const { isMobile } = useSidebar();
  const { activeMacro, shownOrg, orgHasMacro } = nav;
  const glossary = orgHasMacro ? manifest.macro_glossaries?.[activeMacro] : undefined;
  const dataAsOf = manifest.provenance.data_as_of;

  return (
    <>
      {/* Styled text, not a heading: card titles are the page's h2s, and the
          sidebar already marks the tab as the current page. */}
      <div className="mb-4">
        <p className="text-[21px] font-semibold tracking-tight">{activeMacro}</p>
        {/* The header shows freshness on wide screens; phones get it here. */}
        {isMobile && dataAsOf && (
          <Freshness dataAsOf={dataAsOf} className="mt-0.5 text-xs text-muted-foreground" />
        )}
      </div>
      {/* Every macro ships its own explainer, listing only what that tab
          shows. It may be absent when a cached bundle meets an older manifest
          — degrade to no glossary, never a crash. */}
      {glossary && <Glossary glossary={glossary} />}
      {orgHasMacro ? (
        <OrgPanel org={shownOrg} manifest={manifest} macro={activeMacro} onToc={onToc} />
      ) : (
        <p className="empty">
          {manifest.macro_absent_notes?.[activeMacro] ?? `No ${activeMacro} data for ${shownOrg}.`}
        </p>
      )}
      {/* One footer bar: WIP notice left, provenance right — same rule, same baseline. */}
      <div className="footrow">
        {manifest.wip !== false && <WipFooter issuesUrl={manifest.issues_url} />}
        <ProvenanceFooter provenance={manifest.provenance} />
      </div>
    </>
  );
}

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped by retry to re-run the fetch below without duplicating its body.
  const [reloadKey, setReloadKey] = useState(0);
  const [macro, setMacro] = useHashState('tab', '');
  const [org, setOrg] = useHashState('org', '');

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchManifest()
      .then((data) => {
        if (!cancelled) setManifest(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(String(cause));
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const retry = () => {
    setManifest(null);
    setReloadKey((key) => key + 1);
  };

  const nav = manifest ? navModel(manifest, macro, org) : null;
  const [toc, setToc] = useState<TocEntry[]>([]);

  return (
    // The header renders in every state below; only the content beneath it
    // changes shape — chrome never pops in after the fact.
    <SidebarProvider className="flex-col">
      <AppHeader nav={nav} onOrg={setOrg} dataAsOf={manifest?.provenance.data_as_of} />
      <div className="flex flex-1">
        <AppSidebar nav={nav} toc={nav?.orgHasMacro ? toc : []} onTab={setMacro} />
        {/* min-w-0: a flex item defaults to min-width:auto and would widen to
            its longest unbreakable line (a nowrap stamp, a wide table) instead
            of shrinking to the viewport — the page would scroll sideways. */}
        <SidebarInset className="min-w-0">
          <div className="mx-auto w-full max-w-[1148px] p-3 min-[600px]:p-4 md:p-6">
            {error ? (
              <FatalError message={error} onRetry={retry} />
            ) : !manifest || !nav ? (
              <Skeleton label="Loading dashboard" rows={5} />
            ) : (
              <Dashboard manifest={manifest} nav={nav} onToc={setToc} />
            )}
          </div>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
