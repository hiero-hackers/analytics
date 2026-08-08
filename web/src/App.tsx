/**
 * The analytics dashboard, driven entirely by the data-API manifest: metric
 * tiles, the "how to read this" glossary, a jump bar over collapsible section
 * groups, chart-section cards, then the table sections.
 */

import { useEffect, useMemo, useState } from "react";
import { fetchManifest, type ChartSection, type Manifest } from "./api";
import { ChartSectionCard } from "./components/ChartSectionCard";
import { Glossary } from "./components/Glossary";
import { MetricTiles } from "./components/MetricTiles";
import { ProvenanceFooter } from "./components/ProvenanceFooter";
import { SectionGroups, type Group } from "./components/SectionGroups";
import { SectionTable } from "./components/SectionTable";
import { Skeleton } from "./components/Skeleton";
import { TabBar } from "./components/TabBar";
import { WipFooter } from "./components/WipFooter";
import { stamp } from "./format";
import { useHashState } from "./useHashState";
import { useSectionDocs } from "./useSectionDocs";
import { useViewDocs } from "./useViewDocs";
import { ViewCards } from "./components/ViewCards";

function OrgPanel({ org, manifest, macro }: { org: string; manifest: Manifest; macro: string }) {
  const entry = manifest.orgs[org];
  const refs = useMemo(
    () => (entry.sections ?? []).filter((section) => section.macro === macro),
    [entry, macro],
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
    if (!names.includes(doc.group || "")) names.push(doc.group || "");
  }
  const settled = !viewsLoading && !docsLoading;
  const groups: Group[] = !settled
    ? []
    : names.flatMap((name): Group[] => {
        const groupViews = views.filter((view) => (view.group ?? names[0]) === name);
        const groupCharts = chartSections.filter((section) => chartGroup(section) === name);
        const groupDocs = docs.filter((doc) => (doc.group || "") === name);
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
                <SectionTable key={doc.id} doc={doc} provenance={provenance} periodLabels={manifest.period_labels} />
              ))}
            </>,
          ],
        ];
      });

  return (
    <>
      <MetricTiles tiles={entry.metrics?.[macro] ?? []} />
      {/* A section that could not load leaves a named gap rather than blanking
          the tab — the rest of the page is still worth reading. */}
      {unavailable.length > 0 && (
        <p className="error">
          Could not load {unavailable.length === 1 ? "this section" : "these sections"}:{" "}
          {unavailable.join(", ")}. Everything else on this tab is unaffected — reload to try again.
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
      <details className="mt-3 text-[13px] text-muted">
        <summary className="cursor-pointer">Error details</summary>
        <pre className="mt-2 whitespace-pre-wrap break-all">{message}</pre>
      </details>
    </div>
  );
}

/** Everything that depends on a loaded manifest — tabs, org filter, panels, footer. */
function Dashboard({
  manifest,
  macro,
  setMacro,
  org,
  setOrg,
}: {
  manifest: Manifest;
  macro: string;
  setMacro: (value: string) => void;
  org: string;
  setOrg: (value: string) => void;
}) {
  const orgs = Object.keys(manifest.orgs);
  const derived = [
    ...new Set(
      Object.values(manifest.orgs).flatMap((entry) => [
        ...(entry.sections ?? []).map((section) => section.macro),
        ...(entry.chart_sections ?? []).map((section) => section.macro),
        ...(entry.views ?? []).map((view) => view.macro),
      ]),
    ),
  ];
  // The manifest's family order wins where it knows the macro; anything it
  // doesn't list (older manifest, ad-hoc macro) keeps its derived position.
  const declared = (manifest.macro_order ?? []).filter((name) => derived.includes(name));
  const macros = [...declared, ...derived.filter((name) => !declared.includes(name))];
  const activeMacro = macros.includes(macro) ? macro : macros[0];
  // Umbrella tabs: a macro with a parent renders as a sub-tab of that parent.
  // The top bar shows one entry per umbrella (in content order); a second tab
  // row appears for the active umbrella's members. The hash keeps storing the
  // actual macro, so old links keep working.
  const parents = manifest.macro_parents ?? {};
  const topOf = (name: string) => parents[name] ?? name;
  const topTabs = [...new Set(macros.map(topOf))];
  const activeTop = topOf(activeMacro);
  const subTabs = macros.filter((name) => parents[name] === activeTop);
  // The org filter is global: it lists every org and the selection sticks as
  // tabs change. A tab the selected org has no content for renders a short
  // explanation (from the manifest) instead of a blank page, so absence reads
  // as a property of the data rather than a bug.
  const shownOrg = orgs.includes(org) ? org : orgs[0];
  const shownEntry = manifest.orgs[shownOrg];
  const orgHasMacro =
    (shownEntry.sections ?? []).some((section) => section.macro === activeMacro) ||
    (shownEntry.chart_sections ?? []).some((section) => section.macro === activeMacro) ||
    (shownEntry.views ?? []).some((view) => view.macro === activeMacro);
  const glossary = orgHasMacro ? manifest.macro_glossaries?.[activeMacro] : undefined;

  return (
    <>
      <p className="sub">
        Generated {stamp(manifest.generated_at)} UTC · every table filters and sorts · click a chart to enlarge.
      </p>
      {/* The org filter is the outermost scope — everything below it is "this
          org's view" — so it sits above the content tabs. */}
      {orgs.length > 1 && <TabBar items={orgs} active={shownOrg} onSelect={setOrg} kind="tab" />}
      <TabBar
        items={topTabs}
        active={activeTop}
        onSelect={(name) => setMacro(macros.find((candidate) => topOf(candidate) === name) ?? name)}
        kind="macro"
      />
      {subTabs.length > 0 && <TabBar items={subTabs} active={activeMacro} onSelect={setMacro} kind="tab" />}
      {/* Every macro ships its own explainer, listing only what that tab
          shows. It may be absent when a cached bundle meets an older manifest
          — degrade to no glossary, never a crash. */}
      {glossary && <Glossary glossary={glossary} />}
      {orgHasMacro ? (
        <OrgPanel org={shownOrg} manifest={manifest} macro={activeMacro} />
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
  const [macro, setMacro] = useHashState("tab", "");
  const [org, setOrg] = useHashState("org", "");

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

  return (
    <div className="wrap">
      <h1>Hiero — analytics dashboard</h1>
      {/* The header renders in every state below; only the content beneath it
          changes shape — chrome never pops in after the fact. */}
      {error ? (
        <FatalError message={error} onRetry={retry} />
      ) : !manifest ? (
        <>
          <p className="sub">Loading…</p>
          <Skeleton label="Loading dashboard" rows={5} />
        </>
      ) : (
        <Dashboard manifest={manifest} macro={macro} setMacro={setMacro} org={org} setOrg={setOrg} />
      )}
    </div>
  );
}
