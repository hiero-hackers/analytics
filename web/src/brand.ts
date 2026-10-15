/**
 * Where an organisation's logo set lives: `public/brand/<key>/logo.svg` and
 * `logo-dark.svg`, keyed by the `brand` its manifest entry carries. Returns
 * null for no key, the default Hiero key, or a key that is not a plain slug
 * (the key becomes a URL path, so nothing else is trusted).
 */

const SAFE_KEY = /^[a-z0-9][a-z0-9-]{0,63}$/;

export interface Logo {
  light: string;
  dark: string;
}

export function brandLogo(brand: string | undefined, base: string): Logo | null {
  if (!brand || brand === 'hiero' || !SAFE_KEY.test(brand)) return null;
  return { light: `${base}brand/${brand}/logo.svg`, dark: `${base}brand/${brand}/logo-dark.svg` };
}
