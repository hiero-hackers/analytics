import { createContext } from 'react';

/** The organisation the dashboard is showing, for cells that link into it (repositories). */
export const OrgContext = createContext<string | null>(null);
