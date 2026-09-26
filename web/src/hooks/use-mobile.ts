import * as React from 'react';

const MOBILE_BREAKPOINT = 768;
const QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`;

export function useIsMobile() {
  // Local change: shadcn starts at `undefined` (read as false) and corrects
  // itself in an effect, which suits server rendering. This app renders only
  // in the browser, so read the query up front: phones get their layout on
  // the first render instead of flashing the desktop one first.
  const [isMobile, setIsMobile] = React.useState(() => window.matchMedia(QUERY).matches);

  React.useEffect(() => {
    const mql = window.matchMedia(QUERY);
    const onChange = () => setIsMobile(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}
