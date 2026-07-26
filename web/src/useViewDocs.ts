/**
 * Load the bespoke view documents behind a list of manifest refs.
 *
 * Same contract as `useSectionDocs`: a failed view degrades to a named gap
 * rather than blanking the tab around it.
 */

import { useEffect, useState } from "react";
import { fetchView, type ViewDoc, type ViewRef } from "./api";

export interface LoadedViews {
  views: ViewDoc[];
  /** Titles of the views that could not be loaded. */
  failed: string[];
}

export function useViewDocs(refs: ViewRef[]): LoadedViews {
  const [state, setState] = useState<LoadedViews>({ views: [], failed: [] });

  useEffect(() => {
    let cancelled = false;
    setState({ views: [], failed: [] });
    Promise.allSettled(refs.map((ref) => fetchView(ref))).then((results) => {
      if (cancelled) return;
      setState({
        views: results.flatMap((result) => (result.status === "fulfilled" ? [result.value] : [])),
        failed: refs.filter((_ref, index) => results[index].status === "rejected").map((ref) => ref.title),
      });
    });
    return () => {
      cancelled = true;
    };
  }, [refs]);

  return state;
}
