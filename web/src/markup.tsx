/**
 * The one inline-markup convention the API's prose uses.
 *
 * Every human-readable string the Python side ships — glossary definitions,
 * chart notes, methodology steps, KPI tile explanations — is plain text except
 * for `*asterisks*`, which mark emphasis. Rendering happens here so the
 * convention holds everywhere the prose surfaces, rather than in whichever
 * component happened to need it first.
 */

import { Fragment, type ReactNode } from 'react';

export function emphasized(text: string): ReactNode[] {
  return text
    .split(/(\*[^*]+\*)/)
    .map((part, index) =>
      part.startsWith('*') && part.endsWith('*') ? (
        <em key={index}>{part.slice(1, -1)}</em>
      ) : (
        <Fragment key={index}>{part}</Fragment>
      ),
    );
}
