/**
 * A repository name, owner muted. With a detail view it opens that view, and a
 * separate icon links to GitHub; otherwise the name itself links to GitHub. Bare
 * names resolve against the dashboard's organisation; anything not shaped like a
 * repository stays plain text.
 */

import { useContext } from 'react';
import { useEntityLink } from '../entities';
import { OrgContext } from '../orgContext';
import { GitHubLink } from './EntityLink';

const NAME = /^[A-Za-z0-9_.-]+$/;

export function RepoCell({ name }: { name: string }) {
  const org = useContext(OrgContext);
  const detail = useEntityLink('repo', name);
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
  const github = `https://github.com/${encodeURIComponent(home)}/${encodeURIComponent(repo)}`;
  if (detail) {
    return (
      <span className="inline-flex items-center gap-1">
        <a
          href={detail.href}
          title={`Open the repository details for ${repo}`}
          className="rounded-sm font-medium outline-none underline-offset-4 hover:text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          {label}
        </a>
        <GitHubLink href={github} name={repo} />
      </span>
    );
  }
  return (
    <a
      href={github}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-sm font-medium outline-none underline-offset-4 hover:text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label}
    </a>
  );
}
