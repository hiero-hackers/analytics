/**
 * Load the section documents behind a list of manifest refs.
 *
 * Failures are per-document, never per-tab: one unreachable section (a network
 * blip, a half-deployed refresh, a renamed file) must not blank everything
 * else the reader came for. Whatever loaded renders; whatever did not is
 * reported by name, so the gap is visible rather than silent.
 */

import { useEffect, useState } from 'react';
import { fetchSection, type SectionDoc, type SectionRef } from './api';

export interface LoadedSections {
  docs: SectionDoc[];
  /** Titles of the sections that could not be loaded. */
  failed: string[];
  /** True until every ref has settled — lets layout wait rather than reshuffle. */
  loading: boolean;
}

export function useSectionDocs(refs: SectionRef[]): LoadedSections {
  const [state, setState] = useState<LoadedSections>({
    docs: [],
    failed: [],
    loading: refs.length > 0,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ docs: [], failed: [], loading: refs.length > 0 });
    Promise.allSettled(refs.map((ref) => fetchSection(ref))).then((results) => {
      if (cancelled) return;
      setState({
        docs: results.flatMap((result) => (result.status === 'fulfilled' ? [result.value] : [])),
        failed: refs
          .filter((_ref, index) => results[index].status === 'rejected')
          .map((ref) => ref.title),
        loading: false,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [refs]);

  return state;
}
