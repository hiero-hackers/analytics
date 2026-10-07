/**
 * Repository and contributor names that open their detail view in the dashboard,
 * with GitHub one small, separate link away. A name the org's entity index does
 * not list renders as plain text (or its caller's existing GitHub link).
 */

import type { ReactNode } from 'react';
import { ExternalLinkIcon } from 'lucide-react';
import { cn } from 'cn';
import { useEntityLink, type EntityKind } from '../entities';

const NOUN: Record<EntityKind, string> = { repo: 'repository', contributor: 'contributor' };

/** `name` as a link to its detail view; `children` replaces the visible text. */
export function EntityLink({
  kind,
  name,
  children,
  className,
}: {
  kind: EntityKind | null;
  name: string;
  children?: ReactNode;
  className?: string;
}) {
  const link = useEntityLink(kind, name);
  if (!link) return <>{children ?? name}</>;
  return (
    <a
      href={link.href}
      title={`Open the ${NOUN[kind!]} details for ${name}`}
      className={cn(
        'rounded-sm font-medium outline-none underline-offset-4 hover:text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
    >
      {children ?? name}
    </a>
  );
}

/** A compact "on GitHub" link beside an in-dashboard name. */
export function GitHubLink({ href, name }: { href: string; name: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${name} on GitHub`}
      title="Open on GitHub"
      data-print-hide
      className="inline-flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground outline-none hover:text-link focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ExternalLinkIcon className="size-3.5" aria-hidden="true" />
    </a>
  );
}
