/** Shared display formatting. */

/** An ISO timestamp as the dashboard's "YYYY-MM-DD HH:MM" stamp. */
export const stamp = (iso: string): string => iso.slice(0, 16).replace("T", " ");
