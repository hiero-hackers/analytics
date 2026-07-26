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
    return iso.slice(0, 16).replace("T", " "); // unparseable: show it raw
  }
  return date.toISOString().slice(0, 16).replace("T", " ");
}
