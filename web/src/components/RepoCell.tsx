/**
 * A repository name linked to GitHub, owner muted. Bare names resolve against the
 * dashboard's organisation; anything not shaped like a repository stays plain text.
 */

import { useContext } from 'react';
import { OrgContext } from '../orgContext';

const NAME = /^[A-Za-z0-9_.-]+$/;

export function RepoCell({ name }: { name: string }) {
  const org = useContext(OrgContext);
  const [owner, repo] = name.includes('/') ? name.split('/', 2) : [null, name];
  if (!NAME.test(repo) || (owner !== null && !NAME.test(owner))) return <>{name}</>;
  const home = owner ?? org;
  const label = (
    <>
      {owner && <span className="font-normal text-muted-foreground">{owner}/</span>}
      {repo}
    </>
  );
  if (!home) return <span className="font-medium">{label}</span>;
  return (
    <a
      href={`https://github.com/${encodeURIComponent(home)}/${encodeURIComponent(repo)}`}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-sm font-medium outline-none underline-offset-4 hover:text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label}
    </a>
  );
}
