import { createContext, useContext } from 'react';

/** A readable, bounded document; every application of this limit is labelled. */
export const PRINT_ROW_LIMIT = 500;

export const PrintContext = createContext({ printing: false, begin: () => {}, finish: () => {} });
export const usePrintMode = () => useContext(PrintContext).printing;
