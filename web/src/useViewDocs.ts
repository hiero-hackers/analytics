/**
 * Load the bespoke view documents behind a list of manifest refs.
 *
 * Same contract as `useSectionDocs`: a failed view degrades to a named gap
 * rather than blanking the tab around it.
 */

import { useEffect, useState } from 'react';
import { fetchView, type ViewDoc, type ViewRef } from './api';

export interface LoadedViews {
  views: ViewDoc[];
  /** Titles of the views that could not be loaded. */
  failed: string[];
  /**
   * Whether the fetches are still in flight.
   *
   * Chart sections come straight off the manifest and paint immediately, while
   * views arrive over the network. Without this flag the caller cannot tell
   * "no views on this tab" from "views not here yet", so it renders the charts
   * alone and then injects the views *above* them — the page reorders itself
   * under the reader. False when there is nothing to fetch.
   */
  loading: boolean;
}

export function useViewDocs(refs: ViewRef[]): LoadedViews {
  const [state, setState] = useState<LoadedViews>({
    views: [],
    failed: [],
    loading: refs.length > 0,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ views: [], failed: [], loading: refs.length > 0 });
    Promise.allSettled(refs.map((ref) => fetchView(ref))).then((results) => {
      if (cancelled) return;
      setState({
        views: results.flatMap((result) => (result.status === 'fulfilled' ? [result.value] : [])),
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
