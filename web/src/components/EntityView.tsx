/**
 * One repository's or contributor's detail view, in place of the tab while the
 * URL names it (see entities.ts). Everything shown comes from the entity's own
 * document, counted from the underlying events by the pipeline; nothing here
 * aggregates org-wide rows. Loaded lazily with its chart code.
 */

import { useEffect, useState, type ReactNode } from 'react';
import {
  ArrowLeftIcon,
  CircleAlertIcon,
  CrosshairIcon,
  ExternalLinkIcon,
  InfoIcon,
  GitBranchIcon,
  RotateCwIcon,
  UserRoundIcon,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  type EntityCounts,
  type EntityDocument,
  type Manifest,
  type RelatedSection,
  type TimeseriesDocument,
  type WorkFamily,
} from '../api';
import { validateChartDocument } from '../chartData';
import {
  detailPath,
  entityHash,
  loadEntityDocument,
  sectionHash,
  lookupEntity,
  type EntityDirectory,
  type EntityRef,
} from '../entities';
import { dateStamp, stamp } from '../format';
import { PAGE_TITLE_ID } from '../hooks/use-header-scroll';
import { writeParams } from '../urlState';
import { PrintControls } from '../printing';
import { usePrintMode } from '../printContext';
import { tocEntries, type Group, type TocEntry } from '../toc';
import { SeriesView } from './charts/SeriesView';
import { ContributorCell } from './ContributorCell';
import { FormattedCell } from './FormattedCell';
import { OrgAvatar } from './OrgSwitcher';
import { SectionCard } from './SectionCard';
import { SectionGroups } from './SectionGroups';
import { SectionTable } from './SectionTable';
import { Skeleton } from './Skeleton';

const COUNTS: { key: keyof EntityCounts; label: string }[] = [
  { key: 'prs_opened', label: 'PRs opened' },
  { key: 'reviews_given', label: 'Reviews' },
  { key: 'merges_done', label: 'Merges' },
  { key: 'issues_opened', label: 'Issues opened' },
  { key: 'labels_applied', label: 'Labels applied' },
];

const FAMILIES: { key: WorkFamily; label: string; counts: string }[] = [
  { key: 'building_and_fixing', label: 'Building & fixing', counts: 'PRs opened' },
  { key: 'reviewing_and_guiding', label: 'Reviewing & guiding', counts: 'reviews and merges' },
  { key: 'organizing_and_answering', label: 'Organizing & answering', counts: 'issues and labels' },
];

/** List columns holding GitHub logins: shown as people, like every other table's. */
const PERSON_KEYS = new Set(['user', 'login', 'contributor']);

type State =
  | { status: 'loading'; path: string }
  | { status: 'ready'; path: string; document: EntityDocument }
  | { status: 'error'; path: string };

function useEntityDocument(path: string | null, attempt: number): State | null {
  const [state, setState] = useState<State | null>(null);
  useEffect(() => {
    if (!path) return;
    let active = true;
    loadEntityDocument(path)
      .then((document) => active && setState({ status: 'ready', path, document }))
      .catch(() => active && setState({ status: 'error', path }));
    return () => {
      active = false;
    };
  }, [path, attempt]);
  if (!path) return null;
  return state?.path === path ? state : { status: 'loading', path };
}

/** The trend chart document, or null when absent or not one the chart views accept. */
function validTrend(trend: TimeseriesDocument | null): TimeseriesDocument | null {
  if (!trend) return null;
  try {
    return validateChartDocument(trend) as TimeseriesDocument;
  } catch {
    return null;
  }
}

/** Counts per window, Week first: the same five actions for every window. */
function PeriodSummary({ document }: { document: EntityDocument }) {
  const windows = document.window.periods;
  const extra =
    document.kind === 'repository'
      ? { key: 'active_contributors' as const, label: 'Active contributors' }
      : { key: 'repos_touched' as const, label: 'Repositories touched' };
  const cell = (period: string, key: keyof EntityCounts) => document.summary[period]?.[key] ?? 0;
  return (
    <Table className="min-w-[560px]" containerClassName="rounded-lg border">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead scope="col">Tracked activity</TableHead>
          {windows.map((window) => (
            <TableHead key={window.key} scope="col" className="text-right">
              <span title={window.start ? `From ${stamp(window.start)} UTC` : undefined}>
                {window.label}
              </span>
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {[...COUNTS, { key: 'total_actions' as const, label: 'All tracked actions' }, extra].map(
          (row) => (
            <TableRow
              key={row.key}
              className={row.key === 'total_actions' ? 'bg-muted/40 font-semibold' : undefined}
            >
              <TableHead scope="row" className="font-medium">
                {row.label}
              </TableHead>
              {windows.map((window) => (
                <TableCell key={window.key} className="text-right tabular-nums" data-numeric>
                  <FormattedCell value={cell(window.key, row.key)} format="number" />
                </TableCell>
              ))}
            </TableRow>
          ),
        )}
      </TableBody>
    </Table>
  );
}

/** The same actions split into the three neutral work families, per window. */
function WorkMix({ document }: { document: EntityDocument }) {
  const windows = document.window.periods;
  return (
    <Table className="min-w-[560px]" containerClassName="rounded-lg border">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead scope="col">Work mix</TableHead>
          {windows.map((window) => (
            <TableHead key={window.key} scope="col" className="text-right">
              {window.label}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {FAMILIES.map((family) => (
          <TableRow key={family.key}>
            <TableHead scope="row" className="font-medium">
              {family.label}
              <span className="block text-xs font-normal text-muted-foreground">
                {family.counts}
              </span>
            </TableHead>
            {windows.map((window) => {
              const entry = document.mix[window.key]?.[family.key];
              return (
                <TableCell key={window.key} className="text-right tabular-nums" data-numeric>
                  {entry ? (
                    <>
                      <FormattedCell value={entry.share} format="percent" />
                      <span className="block text-xs text-muted-foreground">
                        <FormattedCell value={entry.count} format="number" />{' '}
                        {entry.count === 1 ? 'action' : 'actions'}
                      </span>
                    </>
                  ) : (
                    <FormattedCell value={null} />
                  )}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function RelatedCard({ section }: { section: RelatedSection }) {
  const [showAll, setShowAll] = useState(false);
  const printing = usePrintMode();
  const listRows = section.list?.rows ?? [];
  const previewCount = printing ? 30 : 8;
  const visibleRows = showAll && !printing ? listRows : listRows.slice(0, previewCount);
  const descriptions: Record<string, string> = {
    releases: 'Release cadence and recent published versions.',
    governance: 'Role coverage and the people with repository permissions.',
    hips: 'Hiero Improvement Proposals this repository has merged work for.',
    onboarding: 'Open issues by onboarding difficulty.',
    security: 'Available scorecard checks and security signals.',
  };
  return (
    <SectionCard
      id={`related-${section.id}`}
      title={section.title}
      description={descriptions[section.id] ?? 'Repository context from the latest available data.'}
      generatedAt={section.generated_at}
      stale={section.stale}
    >
      {section.links && section.links.length > 0 && (
        // Every figure leads back to the evidence it summarises.
        <p className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>From</span>
          {section.links.map((link) => (
            <a
              key={link.id}
              href={sectionHash(link.macro, link.id)}
              className="inline-flex items-center gap-1 rounded-sm font-medium text-link-ink underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
            >
              {link.title}
              <span className="font-normal text-muted-foreground">({link.macro})</span>
            </a>
          ))}
        </p>
      )}
      {section.fields.length === 0 && !section.list ? (
        <p className="text-sm text-muted-foreground">
          No {section.title.toLowerCase()} data was recorded for this repository.
        </p>
      ) : (
        <div className="space-y-4">
          {section.fields.length > 0 && (
            <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
              {section.fields.map((field) => (
                <div key={field.key}>
                  <dt className="text-xs text-muted-foreground">{field.label}</dt>
                  <dd className="font-medium tabular-nums">
                    <FormattedCell value={field.value} format={field.format} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {section.list && (
            <div>
              <h3 className="mb-2 text-sm font-semibold">{section.list.title}</h3>
              <Table containerClassName="max-h-[420px] rounded-lg border overflow-auto print:max-h-none">
                <TableHeader className="bg-muted">
                  <TableRow>
                    {section.list.columns.map((column) => (
                      <TableHead key={column.key} scope="col">
                        {column.label}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleRows.map((row, index) => (
                    <TableRow key={index}>
                      {section.list!.columns.map((column) => (
                        <TableCell key={column.key}>
                          {PERSON_KEYS.has(column.key) &&
                          !column.format &&
                          typeof row[column.key] === 'string' ? (
                            <ContributorCell login={row[column.key] as string} />
                          ) : (
                            <FormattedCell value={row[column.key]} format={column.format} />
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {listRows.length > previewCount && (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    Showing {visibleRows.length} of {listRows.length}{' '}
                    {section.list.title.toLowerCase()}.
                  </span>
                  {printing ? (
                    <span>See the dashboard for the complete list.</span>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      aria-expanded={showAll}
                      onClick={() => setShowAll((value) => !value)}
                    >
                      {showAll ? 'Show fewer' : `Show all ${listRows.length}`}
                    </Button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}

function Method({ document }: { document: EntityDocument }) {
  return (
    <SectionCard
      id="entity-method"
      title="How this is counted"
      description={document.population}
      generatedAt={document.generated_at}
      stale={document.stale}
    >
      <div className="space-y-4 text-sm leading-relaxed">
        <ol className="list-decimal space-y-1 pl-5">
          {document.methodology.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        {document.limits.length > 0 && (
          <div>
            <h3 className="font-semibold">Limits of the source data</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
              {document.limits.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          Source tables: {document.source.join(', ')}.
        </p>
      </div>
    </SectionCard>
  );
}

/** A quick read before the detailed windows and tables. Values are taken from the document. */
function Overview({ document }: { document: EntityDocument }) {
  const month = document.summary['30d'];
  const all = document.summary.all;
  const isRepo = document.kind === 'repository';
  const items = [
    {
      label: 'Tracked actions · 30 days',
      value: month?.total_actions ?? 0,
      detail: 'Recent activity',
    },
    {
      label: isRepo ? 'Active contributors' : 'Repositories touched',
      value: isRepo ? (month?.active_contributors ?? 0) : (month?.repos_touched ?? 0),
      detail: 'Last 30 days',
    },
    {
      label: 'Tracked actions · all time',
      value: all?.total_actions ?? 0,
      detail: 'Since tracking began',
    },
  ];
  return (
    <section aria-label="At a glance" className="mb-6">
      <h2 className="mb-3 font-display text-lg font-semibold">At a glance</h2>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {items.map((item) => (
          <div
            key={item.detail + item.label}
            className="rounded-xl border bg-card px-4 py-4 shadow-xs"
          >
            <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
            <p className="mt-2 font-display text-2xl font-semibold tracking-tight tabular-nums sm:text-3xl">
              <FormattedCell value={item.value} format="number" />
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{item.detail}</p>
          </div>
        ))}
        <div className="rounded-xl border bg-card px-4 py-4 shadow-xs">
          <p className="text-xs font-medium text-muted-foreground">Last tracked action</p>
          <p className="mt-2 font-display text-base font-semibold tracking-tight tabular-nums sm:text-xl">
            {document.last_active ? dateStamp(document.last_active) : '—'}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">Across all recorded time</p>
        </div>
      </div>
    </section>
  );
}

function Header({
  entity,
  name,
  document,
  returnTo,
  org,
  actions,
}: {
  entity: EntityRef;
  name: string;
  document: EntityDocument | null;
  returnTo: string;
  org: string;
  actions?: ReactNode;
}) {
  const noun = entity.kind === 'repo' ? 'Repository' : 'Contributor';
  const Icon = entity.kind === 'repo' ? GitBranchIcon : UserRoundIcon;
  return (
    <div className="mb-6 border-b pb-6">
      <p className="mb-3 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <OrgAvatar org={org} className="size-5 rounded" />
        {org}
        <span aria-hidden="true">/</span>
        {noun}
      </p>
      <div className="flex min-w-0 items-center gap-3">
        <span
          className="flex size-11 shrink-0 items-center justify-center rounded-xl border bg-card text-link shadow-xs"
          aria-hidden="true"
        >
          <Icon className="size-5" />
        </span>
        <h1
          id={PAGE_TITLE_ID}
          className="min-w-0 font-display text-3xl font-bold tracking-tight sm:text-4xl [overflow-wrap:anywhere]"
        >
          {name}
        </h1>
      </div>
      {document && (
        <p className="mt-3 text-sm text-muted-foreground">
          {document.kind === 'repository' ? `${document.full_name} · ` : ''}
          Tracked since {document.first_active ? dateStamp(document.first_active) : '—'}
        </p>
      )}
      <div data-print-hide className="mt-4 flex flex-wrap items-center gap-2">
        <Button asChild variant="outline" size="sm">
          <a href={entityHash(null)}>
            <ArrowLeftIcon data-icon="inline-start" />
            Back to {returnTo}
          </a>
        </Button>
        {actions}
      </div>
    </div>
  );
}

export default function EntityView({
  entity,
  directory,
  manifest,
  returnTo,
  onToc,
}: {
  entity: EntityRef;
  directory: EntityDirectory | null;
  manifest: Manifest;
  /** The tab the reader came from, named on the way back. */
  returnTo: string;
  onToc: (entries: TocEntry[]) => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const row = directory ? lookupEntity(directory, entity.kind, entity.id) : null;
  const path = directory && row ? detailPath(directory, { kind: entity.kind, id: row.id }) : null;
  const state = useEntityDocument(path, attempt);
  const document = state?.status === 'ready' ? state.document : null;
  const name =
    document?.kind === 'repository'
      ? document.name
      : document?.kind === 'contributor'
        ? document.login
        : (row?.name ?? row?.login ?? entity.id);
  const org = directory?.org ?? '';

  // A new detail view opens at its top, like a new page.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [entity.kind, entity.id]);

  const groups: Group[] = document ? groupsOf(document, manifest) : [];
  const tocKey = JSON.stringify(tocEntries(groups));
  useEffect(() => {
    onToc(tocEntries(groups));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tocKey is the entries' identity
  }, [tocKey, onToc]);
  useEffect(() => () => onToc([]), [onToc]);

  if (!directory) {
    return (
      <>
        <Header entity={entity} name={entity.id} document={null} returnTo={returnTo} org={org} />
        <Skeleton label="Loading details" rows={4} />
      </>
    );
  }
  if (directory.status[entity.kind] !== 'loaded') {
    // Not knowing is not the same as knowing there is nothing: never say "no
    // tracked activity" without the index that would list it.
    const noun = entity.kind === 'repo' ? 'repository' : 'contributor';
    return (
      <>
        <Header entity={entity} name={entity.id} document={null} returnTo={returnTo} org={org} />
        {directory.status[entity.kind] === 'failed' ? (
          <Alert variant="destructive" className="my-6">
            <CircleAlertIcon />
            <AlertTitle>
              Could not load the {noun} details for {org}.
            </AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-3">
              <p>This is usually temporary — try again in a moment.</p>
              <Button variant="outline" size="sm" onClick={directory.retry}>
                <RotateCwIcon data-icon="inline-start" />
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        ) : (
          <Empty className="my-12">
            <EmptyHeader>
              <EmptyTitle>
                No {noun} detail views are published for {org}
              </EmptyTitle>
              <EmptyDescription>
                This organisation’s data does not include {noun} details yet; they appear after the
                next analytics refresh that produces them.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </>
    );
  }
  if (!row) {
    // A name with no tracked activity here: a permission-holder who never
    // acted, an archived repository. Worth saying, with GitHub one click away.
    const github =
      entity.kind === 'repo'
        ? `https://github.com/${encodeURIComponent(org)}/${encodeURIComponent(entity.id)}`
        : `https://github.com/${encodeURIComponent(entity.id)}`;
    return (
      <>
        <Header
          entity={entity}
          name={entity.id}
          document={null}
          returnTo={returnTo}
          org={org}
          actions={
            <Button asChild variant="outline" size="sm">
              <a href={github} target="_blank" rel="noopener noreferrer">
                <ExternalLinkIcon data-icon="inline-start" />
                View on GitHub
              </a>
            </Button>
          }
        />
        <Empty className="my-12">
          <EmptyHeader>
            <EmptyTitle>
              No tracked activity for {entity.id} in {org}
            </EmptyTitle>
            <EmptyDescription>
              {entity.kind === 'repo'
                ? 'No pull request, review, merge, issue or label in this repository'
                : 'No pull request, review, merge, issue or label by this person'}{' '}
              is recorded in this organisation’s data, so there are no counts to show. Tracked
              activity does not include commits, comments or reactions.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </>
    );
  }
  if (state?.status === 'error') {
    return (
      <>
        <Header entity={entity} name={name} document={null} returnTo={returnTo} org={org} />
        <Alert variant="destructive" className="my-6">
          <CircleAlertIcon />
          <AlertTitle>Could not load the details for {name}.</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <p>This is usually temporary — try again in a moment.</p>
            <Button variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>
              <RotateCwIcon data-icon="inline-start" />
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </>
    );
  }
  if (!document) {
    return (
      <>
        <Header entity={entity} name={name} document={null} returnTo={returnTo} org={org} />
        <p data-print-only>Incomplete document: these details are still loading.</p>
        <Skeleton label="Loading details" rows={6} />
      </>
    );
  }

  const focusDimension = entity.kind === 'repo' ? 'repo' : 'contributor';
  const focusValue = document.kind === 'repository' ? document.name : document.login;
  return (
    <>
      <Header
        entity={entity}
        name={name}
        document={document}
        returnTo={returnTo}
        org={org}
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <a href={document.github_url} target="_blank" rel="noopener noreferrer">
                <ExternalLinkIcon data-icon="inline-start" />
                View on GitHub
              </a>
            </Button>
            <Button
              variant="outline"
              size="sm"
              aria-label={`Focus the dashboard on ${focusValue}`}
              onClick={() =>
                // Back to the tab, narrowed to this entity: one history entry.
                writeParams(
                  { focus: `${focusDimension}:${focusValue.toLowerCase()}`, entity: null },
                  { push: true },
                )
              }
            >
              <CrosshairIcon data-icon="inline-start" />
              Focus in dashboard
            </Button>
          </>
        }
      />
      <PrintControls key={`${entity.kind}/${entity.id}`} label="Print page" />
      <Overview document={document} />
      <Scope document={document} />
      <SectionGroups groups={groups} />
    </>
  );
}

/** Milliseconds since the epoch for an ISO timestamp, with either a `T` or a space before the time. */
const instant = (iso: string) => Date.parse(iso.replace(' ', 'T'));

/** What the counts cover, how current they are, and when the data looks behind. */
function Scope({ document }: { document: EntityDocument }) {
  const { end, data_through: through } = document.window;
  const week = document.window.periods.find((period) => period.key === '7d');
  // No event anywhere in the org since the Week window began: a quiet week is
  // indistinguishable from datasets that were not refreshed, so say which.
  const behind = !!(through && week?.start && instant(through) < instant(week.start));
  return (
    <div className="mb-6 space-y-3">
      <Alert>
        <InfoIcon />
        <AlertTitle>What these numbers count</AlertTitle>
        <AlertDescription>{document.scope}</AlertDescription>
      </Alert>
      <p className="text-xs text-muted-foreground">
        Windows end {end ? `${stamp(end)} UTC` : 'when the analysis ran'}
        {through
          ? `; the latest tracked event in this organisation is from ${stamp(through)} UTC`
          : ''}
        .
      </p>
      {behind && (
        <Alert data-print-incomplete>
          <CircleAlertIcon />
          <AlertTitle>The recent windows may be incomplete.</AlertTitle>
          <AlertDescription>
            No activity was recorded anywhere in the organisation after {stamp(through!)} UTC, so
            the Week and 1 month counts can read low until the activity data is refreshed.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

function groupsOf(document: EntityDocument, manifest: Manifest): Group[] {
  const trend = validTrend(document.trend);
  const activity: Group = [
    'Activity',
    <>
      <SectionCard
        id="entity-trend"
        title="Activity over time"
        description="Tracked actions per calendar month (UTC), by type. The latest year opens first; choose All periods to see the full history."
        generatedAt={trend?.generated_at}
        stale={trend?.stale}
      >
        {trend ? (
          <SeriesView
            data={trend}
            title="Tracked actions per month"
            period="Tracked actions per month"
            provenance={manifest.provenance}
            defaultRange="12"
          />
        ) : (
          <p className="text-sm text-muted-foreground">No monthly activity was recorded.</p>
        )}
      </SectionCard>
      <SectionCard
        id="entity-periods"
        title="Activity by period"
        description="Exact counts and work mix for each window. Hover a window for the date it starts."
        generatedAt={document.generated_at}
        stale={document.stale}
      >
        <div className="space-y-5">
          <div>
            <h3 className="mb-2 text-sm font-semibold">Actions and reach</h3>
            <PeriodSummary document={document} />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Share of tracked actions</h3>
            <WorkMix document={document} />
          </div>
        </div>
      </SectionCard>
    </>,
  ];
  const table = document.kind === 'repository' ? document.contributors : document.repositories;
  const printColumns = [
    document.kind === 'repository' ? 'contributor' : 'repo',
    'prs_opened',
    'reviews_given',
    'merges_done',
    'total_actions',
    'last_active',
  ];
  const people: Group = [
    table.title,
    <SectionTable
      key={table.id}
      doc={table}
      provenance={manifest.provenance}
      periodLabels={manifest.period_labels}
      printColumns={printColumns}
      printRowLimit={24}
    />,
  ];
  const method: Group = ['Methodology', <Method key="method" document={document} />];
  if (document.kind === 'contributor') return [activity, people, method];
  const related: Group = [
    'Repository context',
    <>
      {document.related.map((section) => (
        <RelatedCard key={section.id} section={section} />
      ))}
      {document.unavailable.length > 0 && (
        <p
          role="note"
          className="mb-6 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground"
        >
          Not available in this data: {document.unavailable.join(', ')}. The pipelines that produce{' '}
          {document.unavailable.length === 1 ? 'it' : 'them'} did not run for this refresh.
        </p>
      )}
    </>,
  ];
  return [activity, people, related, method];
}
