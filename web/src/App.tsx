/**
 * The analytics dashboard, driven entirely by the data-API manifest. The shell
 * is a sticky header (wordmark, org switcher, freshness, theme), a sidebar of
 * tabs with the active tab's table of contents, and the tab itself: metric
 * tiles, the "how to read this" glossary, then collapsible section groups of
 * views, chart-section cards and tables.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { CircleAlertIcon, RotateCwIcon } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';
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
        <Alert variant="destructive" className="mb-6">
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
  const { isMobile } = useSidebar();
  const { activeMacro, shownOrg, orgHasMacro } = nav;
  const glossary = orgHasMacro ? manifest.macro_glossaries?.[activeMacro] : undefined;
  const dataAsOf = manifest.provenance.data_as_of;

  return (
    <>
      {/* The active page owns the h1; content cards use h2 headings. */}
      <div className="mb-6 border-b pb-6">
        <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground">
          {shownOrg}{' '}
          <span aria-hidden="true" className="px-2">
            /
          </span>{' '}
          Analytics
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">{activeMacro}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {(
            {
              Contributors:
                'Explore the people behind Hiero. Follow contribution activity, collaboration, and community growth.',
              Governance:
                'Understand project stewardship, role coverage, and the people guiding the ecosystem.',
              HIPs: 'Follow improvement proposals from discussion to implementation.',
              'Security & scorecards':
                'Explore repository health, security practices, and scorecard results.',
              'Issues & onboarding': 'Track the path from first issue to meaningful contribution.',
              Community: 'Discover how the Hiero community connects and grows.',
              Releases: 'Follow release activity and delivery across the ecosystem.',
            } as Record<string, string>
          )[activeMacro] ?? 'Explore activity and insights across the Hiero ecosystem.'}
        </p>
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
        // A tab the selected org has no content for: the manifest's "why",
        // sized to read as information rather than an error.
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
      )}
      {/* One footer bar: WIP notice left, provenance right — same rule, same baseline. */}
      <div className="mt-10 flex flex-wrap items-baseline justify-between gap-4 border-t pt-4">
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
          {/* Left-aligned next to the sidebar (not centred), so the content
              edge lines up with the header's org switcher at every width. */}
          <div className="mx-auto w-full max-w-[1440px] p-4 min-[600px]:p-6 lg:p-8">
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
