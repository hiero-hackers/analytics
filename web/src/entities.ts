/**
 * The repository and contributor detail views: their place in the URL, and which
 * names have one.
 *
 * `entity=repo:<id>` or `entity=contributor:<id>` in the hash opens a detail view
 * over the current tab; every other key (tab, org, focus) is kept, so closing it
 * returns to exactly where the reader was. Links are ordinary hash hrefs: a click
 * adds a history entry (Back and Forward step through views), and "open in new
 * tab" or a copied link reopens the same view.
 *
 * Names become links only when the org's entity index lists them, so a link never
 * leads to a missing document. The indexes are fetched once per org, after the
 * manifest; each detail document is fetched only when opened.
 */

import { createContext, useContext, useEffect, useState } from 'react';
import {
  fetchEntityDocument,
  fetchEntityIndex,
  type EntityDocument,
  type EntityIndex,
  type EntityIndexRow,
  type EntityRefs,
} from './api';
import { useUrlParam, writeParams } from './urlState';

export type EntityKind = 'repo' | 'contributor';

export interface EntityRef {
  kind: EntityKind;
  id: string;
}

export const ENTITY_KEY = 'entity';
const KINDS: EntityKind[] = ['repo', 'contributor'];

export function parseEntity(raw: string): EntityRef | null {
  const at = raw.indexOf(':');
  const kind = raw.slice(0, at) as EntityKind;
  const id = raw.slice(at + 1);
  return at > 0 && KINDS.includes(kind) && id ? { kind, id } : null;
}

export const formatEntity = (ref: EntityRef) => `${ref.kind}:${ref.id}`;

/** The detail view the URL opens, if any. */
export function useEntity(): EntityRef | null {
  const [raw] = useUrlParam(ENTITY_KEY);
  return parseEntity(raw);
}

/**
 * The hash that opens `ref` (or, for null, closes the open view), keeping the
 * tab, org and focus. A section jump (`widget`) belongs to the page being left.
 */
export function entityHash(ref: EntityRef | null): string {
  const params = new URLSearchParams(window.location.hash.slice(1));
  params.delete('widget');
  if (ref) params.set(ENTITY_KEY, formatEntity(ref));
  else params.delete(ENTITY_KEY);
  return `#${params.toString()}`;
}

/**
 * The hash that leaves the detail view for a dashboard section: its tab, with
 * `widget` naming the section so the tab scrolls to and highlights it, as a
 * shared section link does. Org and focus are kept.
 */
export function sectionHash(macro: string, sectionId: string): string {
  const params = new URLSearchParams(window.location.hash.slice(1));
  params.delete(ENTITY_KEY);
  params.set('tab', macro);
  params.set('widget', sectionId);
  return `#${params.toString()}`;
}

/** Open (or close, for null) a detail view as a new history entry. */
export function openEntity(ref: EntityRef | null) {
  writeParams({ [ENTITY_KEY]: ref ? formatEntity(ref) : null, widget: null }, { push: true });
}

/** An org's two indexes, keyed for lookup by any spelling a table or chart uses. */
export interface EntityDirectory {
  org: string;
  repositories: EntityIndex | null;
  contributors: EntityIndex | null;
  byName: Record<EntityKind, Map<string, EntityIndexRow>>;
}

export const EntityDirectoryContext = createContext<EntityDirectory | null>(null);

// Fetched once per page load; a failed fetch is forgotten, so the next visit retries it.
const indexes = new Map<string, Promise<EntityIndex>>();
const documents = new Map<string, Promise<EntityDocument>>();

function cached<T>(
  cache: Map<string, Promise<T>>,
  path: string,
  load: () => Promise<T>,
): Promise<T> {
  let pending = cache.get(path);
  if (!pending) {
    pending = load();
    pending.catch(() => cache.delete(path));
    cache.set(path, pending);
  }
  return pending;
}

const loadIndex = (path: string) => cached(indexes, path, () => fetchEntityIndex(path));

/** An entity's detail document, checked to be one before it is rendered. */
export const loadEntityDocument = (path: string) =>
  cached(documents, path, () =>
    fetchEntityDocument(path).then((document) => {
      if (!document || typeof document.summary !== 'object' || !document.window) {
        throw new Error(`${path}: not an entity document`);
      }
      return document;
    }),
  );

/** Forget every fetched index and document (tests start from a cold page). */
export function resetEntityCaches() {
  indexes.clear();
  documents.clear();
}

/** Repositories match by bare or `owner/repo` name, people by login; both case-insensitively. */
const repoKey = (name: string) => name.trim().toLowerCase().split('/').pop() ?? '';
const personKey = (login: string) => login.trim().toLowerCase();

/** A directory over an org's two indexes (either may be absent). */
export function directoryOf(
  org: string,
  repositories: EntityIndex | null,
  contributors: EntityIndex | null,
): EntityDirectory {
  const repos = new Map<string, EntityIndexRow>();
  for (const row of repositories?.rows ?? []) {
    for (const name of [row.id, row.name, row.full_name]) if (name) repos.set(repoKey(name), row);
  }
  const people = new Map<string, EntityIndexRow>();
  for (const row of contributors?.rows ?? []) {
    for (const name of [row.id, row.login]) if (name) people.set(personKey(name), row);
  }
  return { org, repositories, contributors, byName: { repo: repos, contributor: people } };
}

/**
 * The shown org's entity directory, once its indexes arrive. Until then (or when
 * the org publishes none, or a fetch fails) names render as they always have.
 */
export function useEntityDirectory(
  org: string,
  refs: EntityRefs | undefined,
): EntityDirectory | null {
  const repositoriesPath = refs?.repositories?.path;
  const contributorsPath = refs?.contributors?.path;
  const [directory, setDirectory] = useState<EntityDirectory | null>(null);
  useEffect(() => {
    let active = true;
    const settle = (path: string | undefined) =>
      path ? loadIndex(path).catch(() => null) : Promise.resolve(null);
    void Promise.all([settle(repositoriesPath), settle(contributorsPath)]).then(
      ([repos, people]) => {
        if (active) setDirectory(repos || people ? directoryOf(org, repos, people) : null);
      },
    );
    return () => {
      active = false;
    };
  }, [org, repositoriesPath, contributorsPath]);
  return directory?.org === org ? directory : null;
}

export function lookupEntity(
  directory: EntityDirectory | null,
  kind: EntityKind,
  name: string,
): EntityIndexRow | null {
  if (!directory) return null;
  return directory.byName[kind].get(kind === 'repo' ? repoKey(name) : personKey(name)) ?? null;
}

/** The API path of an entity's detail document, from its index's template. */
export function detailPath(directory: EntityDirectory, ref: EntityRef): string | null {
  const index = ref.kind === 'repo' ? directory.repositories : directory.contributors;
  return index ? index.detail_path.replace('{id}', encodeURIComponent(ref.id)) : null;
}

/** The detail-view kind a chart or table dimension names, if it has one. */
export function entityKindOf(dimension: string | null | undefined): EntityKind | null {
  return dimension === 'repo' || dimension === 'contributor' ? dimension : null;
}

const REPO_NAME = /^[A-Za-z0-9_.-]+$/;
const LOGIN = /^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}$/;

/** The id a name opens when the index does not list it: the name itself, if it is well formed. */
function unlistedId(kind: EntityKind, name: string): string | null {
  const bare = kind === 'repo' ? (name.trim().split('/').pop() ?? '') : name.trim();
  return (kind === 'repo' ? REPO_NAME : LOGIN).test(bare) && bare !== '.' && bare !== '..'
    ? bare
    : null;
}

/**
 * The in-dashboard link for a repository or contributor name, or null when
 * `kind` is null, the org publishes no detail views, or the name is not shaped
 * like one. Every well-formed name links, so names behave the same everywhere:
 * one with no tracked activity opens a view that says so (and links to GitHub).
 * `row` is its index entry, when it has one. Re-renders with the hash, so the
 * href always keeps the current tab, org and focus.
 */
export function useEntityLink(
  kind: EntityKind | null,
  name: string,
): { href: string; row: EntityIndexRow | null } | null {
  useUrlParam(ENTITY_KEY);
  const directory = useContext(EntityDirectoryContext);
  if (!kind || !directory) return null;
  const row = lookupEntity(directory, kind, name);
  const id = row?.id ?? unlistedId(kind, name);
  return id ? { href: entityHash({ kind, id }), row } : null;
}
