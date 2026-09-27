import { createContext, type ReactNode } from 'react';

/** The container's own switches (a card's period tabs), placed first in every view's toolbar. */
export const ChartLeading = createContext<ReactNode>(null);
