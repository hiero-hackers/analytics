/**
 * The dashboard's navigation, derived from the manifest and the hash state:
 * which orgs and tabs exist, in what order, and which are active. Pure, so the
 * header (org switcher), the sidebar (tabs) and the content (the active panel)
 * all read one answer instead of each re-deriving it.
 */

import type { Manifest } from './api';

export interface NavModel {
  orgs: string[];
  /** The org actually shown: the hash's org when the manifest knows it, else the first. */
  shownOrg: string;
  /** Every macro, in the manifest's declared family order. */
  macros: string[];
  /** The macro actually shown: the hash's when known, else the first. */
  activeMacro: string;
  /** One entry per umbrella tab, in content order. */
  topTabs: string[];
  activeTop: string;
  /** The active umbrella's member macros (empty when it has none). */
  subTabs: string[];
  /** The umbrella a macro renders under (itself when it has no parent). */
  topOf: (macro: string) => string;
  /** Whether the shown org has anything for the active macro. */
  orgHasMacro: boolean;
}

export function navModel(manifest: Manifest, macro: string, org: string): NavModel {
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
  // The hash keeps storing the actual macro, so old links keep working.
  const parents = manifest.macro_parents ?? {};
  const topOf = (name: string) => parents[name] ?? name;
  const activeTop = topOf(activeMacro);
  // The org filter is global: it lists every org and the selection sticks as
  // tabs change. A tab the selected org has no content for renders a short
  // explanation instead of a blank page (see App).
  const shownOrg = orgs.includes(org) ? org : orgs[0];
  const entry = manifest.orgs[shownOrg];
  const orgHasMacro =
    (entry.sections ?? []).some((section) => section.macro === activeMacro) ||
    (entry.chart_sections ?? []).some((section) => section.macro === activeMacro) ||
    (entry.views ?? []).some((view) => view.macro === activeMacro);
  return {
    orgs,
    shownOrg,
    macros,
    activeMacro,
    topTabs: [...new Set(macros.map(topOf))],
    activeTop,
    subTabs: macros.filter((name) => parents[name] === activeTop),
    topOf,
    orgHasMacro,
  };
}
