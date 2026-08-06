/**
 * The analytics dashboard, driven entirely by the data-API manifest: metric
 * tiles, the "how to read this" glossary, a jump bar over collapsible section
 * groups, chart-section cards, then the table sections.
 */

import { useEffect, useMemo, useState } from "react";
import { fetchManifest, type Manifest, type SectionDoc } from "./api";
import { ChartSectionCard } from "./components/ChartSectionCard";
import { Glossary } from "./components/Glossary";
import { MetricTiles } from "./components/MetricTiles";
import { ProvenanceFooter } from "./components/ProvenanceFooter";
import { SectionGroups, type Group } from "./components/SectionGroups";
import { SectionTable } from "./components/SectionTable";
import { TabBar } from "./components/TabBar";
import { WipFooter } from "./components/WipFooter";
import { stamp } from "./format";
import { useHashState } from "./useHashState";
import { useSectionDocs } from "./useSectionDocs";
import { useViewDocs } from "./useViewDocs";
import { ViewCards } from "./components/ViewCards";

/** Sections in order, grouped by their `group` label (order of appearance). */
function groupSections(docs: SectionDoc[]): [string, SectionDoc[]][] {
  const groups: [string, SectionDoc[]][] = [];
  for (const doc of docs) {
    const name = doc.group || "";
    const last = groups[groups.length - 1];
    if (last && last[0] === name) {
      last[1].push(doc);
    } else {
      groups.push([name, [doc]]);
    }
  }
  return groups;
}

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

  const allChartSections = (entry.chart_sections ?? []).filter((section) => section.macro === macro);
  // A chart section with a `group` renders inside that named table group,
  // directly above its companion tables; the rest form the tab-top Charts block.
  const chartSections = allChartSections.filter((section) => !section.group);
  const groupedCharts = allChartSections.filter((section) => section.group);
  const provenance = manifest.provenance;
  const groups: Group[] = [
    // Legacy order: a family's bespoke views (board, matrix) lead its chart
    // galleries, then its tables — governance context first, then the
    // supporting charts, then the individual evidence.
    //
    // Held back until the views settle. Chart sections come off the manifest
    // and would otherwise paint alone, only for the views to arrive and take
    // the position above them — the reader watches the page reshuffle. A brief
    // wait for the whole group in its final order beats content that moves.
    ...((chartSections.length || views.length) && !viewsLoading
      ? ([
          [
            "Charts",
            <>
              {views.length > 0 && <ViewCards views={views} sectionDocs={docs} provenance={provenance} />}
              {chartSections.map((section) => (
                <ChartSectionCard key={section.id} section={section} provenance={provenance} />
              ))}
            </>,
          ],
        ] as Group[])
      : []),
    ...groupSections(docs).map(
      ([name, sections]): Group => [
        name,
        <>
          {groupedCharts
            .filter((section) => section.group === name)
            .map((section) => (
              <ChartSectionCard key={section.id} section={section} provenance={provenance} />
            ))}
          {sections.map((doc) => (
            <SectionTable key={doc.id} doc={doc} provenance={provenance} periodLabels={manifest.period_labels} />
          ))}
        </>,
      ],
    ),
    // A grouped chart whose group has no (loaded) tables still needs a home:
    // give it its own group so it never silently disappears. Waits for the
    // docs to settle so the card doesn't paint alone and then jump into place.
    ...groupedCharts
      .filter((section) => !docsLoading && !groupSections(docs).some(([name]) => name === section.group))
      .map(
        (section): Group => [
          section.group ?? "",
          <ChartSectionCard key={section.id} section={section} provenance={provenance} />,
        ],
      ),
  ];

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
      <SectionGroups groups={groups} />
    </>
  );
}

export default function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [macro, setMacro] = useHashState("tab", "");
  const [org, setOrg] = useHashState("org", "");

  useEffect(() => {
    fetchManifest().then(setManifest).catch((cause: unknown) => setError(String(cause)));
  }, []);

  if (error) {
    return <p className="error">Failed to load the data API: {error}</p>;
  }
  if (!manifest) {
    return <p className="sub">Loading…</p>;
  }

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
  // The org tab bar appears only on macros where more than one org actually
  // has content (e.g. only Contributors for hiero-hackers).
  const orgsForMacro = orgs.filter((name) => {
    const entry = manifest.orgs[name];
    return (
      (entry.sections ?? []).some((section) => section.macro === activeMacro) ||
      (entry.chart_sections ?? []).some((section) => section.macro === activeMacro) ||
      (entry.views ?? []).some((view) => view.macro === activeMacro)
    );
  });
  const shownOrg = orgsForMacro.includes(org) ? org : (orgsForMacro[0] ?? orgs[0]);
  const glossary = manifest.macro_glossaries?.[activeMacro];

  return (
    <div className="wrap">
      <h1>Hiero — analytics dashboard</h1>
      <p className="sub">
        Generated {stamp(manifest.generated_at)} UTC · every table filters and sorts · click a chart to enlarge.
      </p>
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
      {orgsForMacro.length > 1 && <TabBar items={orgsForMacro} active={shownOrg} onSelect={setOrg} kind="tab" />}
      <OrgPanel org={shownOrg} manifest={manifest} macro={activeMacro} />
      {/* One footer bar: WIP notice left, provenance right — same rule, same baseline. */}
      <div className="footrow">
        {manifest.wip !== false && <WipFooter issuesUrl={manifest.issues_url} />}
        <ProvenanceFooter provenance={manifest.provenance} />
      </div>
    </div>
  );
}
