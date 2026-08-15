/**
 * Shareable section links. The URL hash is the app's only router (see
 * useHashState), so a section link keeps every existing key — tab, org, … —
 * and adds `widget` naming the section to scroll to on load. The clipboard
 * helper is dependency-free and uses the (non-deprecated) async Clipboard API.
 */

/** This page's URL with `widget` set to the named section. */
export function shareUrl(sectionId: string): string {
  const params = new URLSearchParams(window.location.hash.slice(1));
  params.set("widget", sectionId);
  return `${window.location.origin}${window.location.pathname}#${params.toString()}`;
}

/**
 * Copy `text` to the clipboard via the async Clipboard API
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {

  }
  return false;
}
