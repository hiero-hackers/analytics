/**
 * The analytics dashboard, driven entirely by the data-API manifest: a sticky
 * header, a sidebar of tabs, and the active tab's tiles, glossary and section groups.
 */

import { lazy, Suspense, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { CircleAlertIcon, RotateCwIcon } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { fetchManifest, type ChartSection, type Manifest } from './api';
import { AppHeader, FreshnessStatus } from './components/AppHeader';
import { OrgAvatar } from './components/OrgSwitcher';
import { OrgContext } from './orgContext';
import { PAGE_TITLE_ID } from './hooks/use-header-scroll';
import { NARROW_HEADER, useMediaQuery } from './hooks/use-media-query';
import { AppSidebar } from './components/AppSidebar';
import { ChartSectionCard } from './components/ChartSectionCard';
import { SectionBoundary } from './components/ErrorBoundary';
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
import { writeParams } from './urlState';
import { FocusBar } from './components/FocusBar';
import { EntityDirectoryContext, useEntity, useEntityDirectory } from './entities';
import { useSectionDocs } from './useSectionDocs';
import { useViewDocs } from './useViewDocs';
import { ViewCards } from './components/ViewCards';
import { PrintLayout } from './components/PrintFooter';
import { PrintControls, PrintProvider } from './printing';
import { stamp } from './format';
import './print.css';

// Loaded when a reader first opens a repository or contributor, with its charts.
const EntityView = lazy(() => import('./components/EntityView'));

const FLASH_MS = 1800; // shared link jump: flash the target for this long, then remove the highlight
// Charts above a jump target load after the tab settles and push it down mid-scroll;
// the jump keeps the target in place while the page grows, for at most this long.
const HOLD_MS = 4000;

function OrgPanel({
  org,
  manifest,
  macro,
  onToc,
}: {
  org: string;
  manifest: Manifest;
  macro: string;
  /** Reports this tab's table of contents to the sidebar. */
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
    let hold: ResizeObserver | undefined;
    let holdTimer: number | undefined;
    // The reader taking over (scrolling, a key, a tap) ends the hold at once.
    const release = () => {
      hold?.disconnect();
      window.clearTimeout(holdTimer);
      for (const name of ['wheel', 'touchstart', 'keydown'] as const) {
        window.removeEventListener(name, release);
      }
    };
    const jump = () => {
      const target = document.getElementById(absorbedInto[widget] ?? widget);
      target?.scrollIntoView({ block: 'start', behavior: 'smooth' });
      target?.classList.add('flash');
      if (flashTimer.current) window.clearTimeout(flashTimer.current);
      flashTimer.current = window.setTimeout(() => target?.classList.remove('flash'), FLASH_MS);
      if (!target || typeof ResizeObserver === 'undefined') return;
      hold = new ResizeObserver(() => target.scrollIntoView({ block: 'start' }));
      hold.observe(document.body);
      holdTimer = window.setTimeout(release, HOLD_MS);
      for (const name of ['wheel', 'touchstart', 'keydown'] as const) {
        window.addEventListener(name, release, { passive: true });
      }
    };
    const canRequestFrame = typeof window.requestAnimationFrame === 'function';
    const raf = canRequestFrame ? window.requestAnimationFrame(jump) : undefined;
    if (raf === undefined) jump();
    return () => {
      if (typeof window.cancelAnimationFrame === 'function' && raf !== undefined) {
        window.cancelAnimationFrame(raf as number);
      }
      if (flashTimer.current) window.clearTimeout(flashTimer.current);
      release();
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
                <SectionBoundary key={section.id} id={section.id} title={section.title}>
                  <ChartSectionCard section={section} provenance={provenance} />
                </SectionBoundary>
              ))}
              {groupDocs.map((doc) => (
                <SectionBoundary key={doc.id} id={doc.id} title={doc.title}>
                  <SectionTable
                    doc={doc}
                    provenance={provenance}
                    periodLabels={manifest.period_labels}
                  />
                </SectionBoundary>
              ))}
            </>,
          ],
        ];
      });

  // Keyed by content so a re-render with the same groups doesn't re-report them.
  const toc = tocEntries(groups);
  const tocKey = JSON.stringify(toc);
  useEffect(() => {
    onToc(toc);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tocKey is toc's identity
  }, [tocKey, onToc]);
  useEffect(() => () => onToc([]), [onToc]);

  return (
    <>
      {/* Keyed by tab and org: navigating away cancels a pending preparation. */}
      <PrintControls key={`${org}/${macro}`} ready={settled} />
      {!settled && (
        <p data-print-only>
          Incomplete document: this tab is still loading. Close print preview and use Print tab when
          loading finishes.
        </p>
      )}
      <MetricTiles tiles={entry.metrics?.[macro] ?? []} />
      {/* A section that could not load leaves a named gap rather than blanking
          the tab — the rest of the page is still worth reading. */}
      {unavailable.length > 0 && (
        <Alert variant="destructive" className="mb-6" data-print-incomplete>
          <CircleAlertIcon />
          <AlertTitle>
            Could not load {unavailable.length === 1 ? 'this section' : 'these sections'}:{' '}
            {unavailable.join(', ')}.
          </AlertTitle>
          <AlertDescription>
            Everything else on this tab is unaffected — reload to try again.
          </AlertDescription>
        </Alert>
      )}
      {settled ? <SectionGroups groups={groups} /> : <Skeleton label="Loading tab" rows={6} />}
    </>
  );
}

/** Human-readable fatal error: retry button up front, raw cause tucked away. */
function FatalError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Alert variant="destructive" className="my-6">
      <CircleAlertIcon />
      <AlertTitle>Failed to load the dashboard data.</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-3">
        <p>This is usually temporary — try again in a moment.</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCwIcon data-icon="inline-start" />
          Retry
        </Button>
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="link" size="sm" className="px-0">
              Error details
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre className="mt-1 font-mono break-all whitespace-pre-wrap">{message}</pre>
          </CollapsibleContent>
        </Collapsible>
      </AlertDescription>
    </Alert>
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
  const narrowHeader = useMediaQuery(NARROW_HEADER);
  const { activeMacro, shownOrg, orgHasMacro } = nav;
  const glossary = orgHasMacro ? manifest.macro_glossaries?.[activeMacro] : undefined;
  const dataAsOf = manifest.provenance.data_as_of;
  const directory = useContext(EntityDirectoryContext);
  const entity = useEntity();
  const footer = (
    // One footer bar: WIP notice left, provenance right — same rule, same baseline.
    <div className="mt-10 flex flex-wrap items-baseline justify-between gap-4 border-t pt-4">
      {manifest.wip !== false && <WipFooter issuesUrl={manifest.issues_url} />}
      <ProvenanceFooter provenance={manifest.provenance} />
    </div>
  );

  if (entity) {
    // A repository or contributor in place of the tab; the tab (and its focus) waits underneath.
    return (
      <PrintLayout provenance={manifest.provenance}>
        <p data-print-only className="print-title">
          {entity.kind === 'repo' ? 'Repository' : 'Contributor'} · {shownOrg}
        </p>
        <OrgContext.Provider value={shownOrg}>
          <Suspense fallback={<Skeleton label="Loading details" rows={6} />}>
            <EntityView
              key={`${shownOrg}/${entity.kind}/${entity.id}`}
              entity={entity}
              directory={directory}
              manifest={manifest}
              returnTo={activeMacro}
              onToc={onToc}
            />
          </Suspense>
        </OrgContext.Provider>
        {footer}
      </PrintLayout>
    );
  }

  return (
    <PrintLayout provenance={manifest.provenance}>
      <p data-print-only className="print-title">
        {activeMacro} · {shownOrg}
      </p>
      <p data-print-only>
        Generated {stamp(manifest.generated_at)} UTC. Periods and filters are stated beside each
        table or chart.
      </p>
      <div className="mb-6 border-b pb-6">
        <p className="mb-2.5 flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <OrgAvatar org={shownOrg} className="size-5 rounded" />
          {shownOrg}
          {nav.topOf(activeMacro) !== activeMacro && (
            <>
              <span aria-hidden="true">/</span>
              {nav.topOf(activeMacro)}
            </>
          )}
        </p>
        <h1 id={PAGE_TITLE_ID} className="font-display text-4xl font-bold tracking-tight">
          {activeMacro}
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {manifest.macro_summaries?.[activeMacro] ??
            'Explore activity and insights across the Hiero ecosystem.'}
        </p>
        {narrowHeader && dataAsOf && (
          <div className="mt-3">
            <FreshnessStatus dataAsOf={dataAsOf} />
          </div>
        )}
      </div>
      {/* Every macro ships its own explainer, listing only what that tab
          shows. It may be absent when a cached bundle meets an older manifest
          — degrade to no glossary, never a crash. */}
      {glossary && <Glossary glossary={glossary} />}
      <FocusBar />
      {orgHasMacro ? (
        <OrgContext.Provider value={shownOrg}>
          <OrgPanel org={shownOrg} manifest={manifest} macro={activeMacro} onToc={onToc} />
        </OrgContext.Provider>
      ) : (
        // Sized to read as information rather than an error.
        <>
          <PrintControls />
          <Empty className="my-12">
            <EmptyHeader>
              <EmptyTitle>
                No {activeMacro} data for {shownOrg}
              </EmptyTitle>
              {manifest.macro_absent_notes?.[activeMacro] && (
                <EmptyDescription>{manifest.macro_absent_notes[activeMacro]}</EmptyDescription>
              )}
            </EmptyHeader>
          </Empty>
        </>
      )}
      {footer}
    </PrintLayout>
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
  const entity = useEntity();
  // Every table and chart links the names the shown org has detail views for.
  const directory = useEntityDirectory(
    nav?.shownOrg ?? '',
    nav ? manifest?.orgs[nav.shownOrg]?.entities : undefined,
  );
  // Choosing a tab closes an open detail view, as one history entry.
  const onTab = (next: string) =>
    entity ? writeParams({ tab: next, entity: null }, { push: true }) : setMacro(next);
  // A detail view has its own table of contents, whatever the tab behind it holds.
  const shownToc = nav?.orgHasMacro || entity ? toc : [];

  return (
    // The header renders in every state; only the content beneath it changes shape.
    <PrintProvider>
      <SidebarProvider
        className="flex-col"
        style={{ '--sidebar-width': '17.5rem' } as React.CSSProperties}
      >
        <AppHeader
          nav={nav}
          // A focused repository or person belongs to one organisation.
          // So does an open repository or contributor: both close on switching.
          onOrg={(next) => {
            writeParams({ focus: null, entity: null });
            setOrg(next);
          }}
          toc={shownToc}
          onTab={onTab}
          dataAsOf={manifest?.provenance.data_as_of}
        />
        <div className="flex flex-1">
          <AppSidebar nav={nav} toc={shownToc} onTab={onTab} />
          {/* min-w-0: otherwise a wide table or nowrap stamp widens the page sideways. */}
          <SidebarInset className="min-w-0">
            <div className="mx-auto w-full max-w-[1440px] p-4 min-[600px]:p-6 lg:p-8">
              {error ? (
                <FatalError message={error} onRetry={retry} />
              ) : !manifest || !nav ? (
                <>
                  <p data-print-only>
                    Incomplete document: dashboard data is still loading. Close print preview and
                    wait for the dashboard to finish loading.
                  </p>
                  <Skeleton label="Loading dashboard" rows={5} />
                </>
              ) : (
                <EntityDirectoryContext.Provider value={directory}>
                  <Dashboard manifest={manifest} nav={nav} onToc={setToc} />
                </EntityDirectoryContext.Provider>
              )}
            </div>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </PrintProvider>
  );
}
