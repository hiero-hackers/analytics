/** Shared display formatting. */

/**
 * An ISO timestamp as the dashboard's "YYYY-MM-DD HH:MM" stamp, in UTC.
 *
 * Every timestamp is labelled UTC where it is shown, so an offset-bearing
 * value has to be converted rather than truncated — slicing
 * "2026-07-25T10:00:00-04:00" would misreport it by four hours. A value with
 * no offset at all is assumed to be UTC (which is what the emitter writes),
 * because JavaScript would otherwise read it as local time.
 */
export function stamp(iso: string): string {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const date = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) {
    return iso.slice(0, 16).replace('T', ' '); // unparseable: show it raw
  }
  return date.toISOString().slice(0, 16).replace('T', ' ');
}

/**
 * Just the UTC date, "YYYY-MM-DD" — the table-cell form of `stamp`.
 *
 * Same conversion rules: an offset-bearing value is converted, not sliced
 * (truncating "2026-07-26T01:20:25+03:00" would report the 26th for an
 * instant that falls on the 25th UTC), and a zoneless value is read as UTC.
 */
export function dateStamp(iso: string): string {
  return stamp(iso).slice(0, 10);
}
