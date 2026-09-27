import { createContext, type ReactNode } from 'react';

/**
 * Controls the chart's container owns but that belong in the chart's toolbar
 * (a card's period tabs: "All time / 1 year / …"). Provided by InteractiveChart,
 * so every view gets them without threading a prop through each one.
 */
export const ChartLeading = createContext<ReactNode>(null);
