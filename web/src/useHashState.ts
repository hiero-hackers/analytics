/**
 * One `key=value` pair of state held in the URL hash — the app's only router.
 * Hash state survives reloads, makes every view linkable, and needs no server
 * routing on static Pages hosting. Future URL-held state (filters, search)
 * goes through this same hook.
 */

import { useEffect, useState } from "react";

export function useHashState(key: string, fallback: string): [string, (value: string) => void] {
  const read = () => new URLSearchParams(window.location.hash.slice(1)).get(key) ?? fallback;
  const [value, setValue] = useState(read);
  useEffect(() => {
    const onHash = () => setValue(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- read is stable per key/fallback
  }, [key, fallback]);
  const update = (next: string) => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    params.set(key, next);
    window.location.hash = params.toString();
  };
  return [value, update];
}
