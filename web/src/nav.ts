/**
 * The dashboard's navigation, derived purely from the manifest and hash state,
 * so header, sidebar and content all read one answer.
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
  /** Whether the shown org has anything for a tab (an umbrella: for any of its members). */
  hasData: (tab: string) => boolean;
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
  // The manifest's family order wins; macros it doesn't list keep their derived position.
  const declared = (manifest.macro_order ?? []).filter((name) => derived.includes(name));
  const macros = [...declared, ...derived.filter((name) => !declared.includes(name))];
  const activeMacro = macros.includes(macro) ? macro : macros[0];
  // A macro with a parent renders as its sub-tab; the hash still stores the macro itself.
  const parents = manifest.macro_parents ?? {};
  const topOf = (name: string) => parents[name] ?? name;
  const activeTop = topOf(activeMacro);
  // The org selection is global and sticks across tabs, even ones it has no data for.
  const shownOrg = orgs.includes(org) ? org : orgs[0];
  const entry = manifest.orgs[shownOrg];
  const present = new Set([
    ...(entry.sections ?? []).map((section) => section.macro),
    ...(entry.chart_sections ?? []).map((section) => section.macro),
    ...(entry.views ?? []).map((view) => view.macro),
  ]);
  const orgHasMacro = present.has(activeMacro);
  const hasData = (tab: string) => macros.some((name) => topOf(name) === tab && present.has(name));
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
    hasData,
  };
}
