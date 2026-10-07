import { createContext, useContext } from 'react';

/** A readable, bounded document; every application of this limit is labelled. */
export const PRINT_ROW_LIMIT = 500;

export const PrintContext = createContext({ printing: false, begin: () => {}, finish: () => {} });
export const usePrintMode = () => useContext(PrintContext).printing;

/**
 * Set inside one chart's printed sheet (`ChartPrintDialog`): its switches print
 * as "Label: value" filters, named without the chart title they repeat.
 */
export const PrintSheetContext = createContext<{ title: string } | null>(null);
