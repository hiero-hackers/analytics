import type { Manifest } from './api';
import { stamp } from './format';

export function provenanceLine(provenance: Manifest['provenance'], includeUnknown = false) {
  return [
    provenance.data_as_of
      ? `data ${stamp(provenance.data_as_of)} UTC`
      : includeUnknown && 'data as of unknown',
    provenance.git_sha ? `code ${provenance.git_sha}` : includeUnknown && 'code unknown',
  ]
    .filter(Boolean)
    .join(' · ');
}

/** Escape a CSS string token, including line breaks and control characters. */
export function cssString(value: string): string {
  return `"${Array.from(value, (character) => {
    const code = character.codePointAt(0)!;
    return character === '"' || character === '\\' || code < 32 || code === 127
      ? `\\${code.toString(16)} `
      : character;
  }).join('')}"`;
}

export function supportsPageMargins(): boolean {
  try {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync('@page { @bottom-left { content: "probe"; } }');
    const rule = sheet.cssRules[0] as CSSPageRule;
    return Array.from(rule.cssRules ?? []).some((child) =>
      child.cssText.startsWith('@bottom-left'),
    );
  } catch {
    return false;
  }
}
