import { createContext, type ReactNode } from 'react';

/** The container's own switches (a card's period tabs), placed first in every view's toolbar. */
export const ChartLeading = createContext<ReactNode>(null);

/** The chart card's own title, which a printed chart names above its heading. */
export const ChartSectionTitle = createContext<string | null>(null);
