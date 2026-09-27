/**
 * Global scope and navigation, kept visible while exploring the dashboard.
 *
 * Left to right: the brand, the scope (the organisation, and — once the page
 * title has scrolled under the header — the page), then how fresh the data
 * is, search, and the theme. The header lifts off the page with a shadow once
 * the page scrolls; nothing else in it moves.
 */
import { useState } from 'react';
import { ChevronRightIcon } from 'lucide-react';
import { cn } from 'cn';
import { SidebarTrigger, useSidebar } from '@/components/ui/sidebar';
import { stamp } from '../format';
import { useHeaderScroll } from '../hooks/use-header-scroll';
import { NARROW_HEADER, useMediaQuery } from '../hooks/use-media-query';
import type { NavModel } from '../nav';
import type { TocEntry } from '../toc';
import { ThemeToggle } from './ThemeToggle';
import { HieroBrand } from './HieroBrand';
import { NavigationSearch } from './NavigationSearch';
import { OrgAvatar, OrgSwitcher } from './OrgSwitcher';

export function Freshness({ dataAsOf, className }: { dataAsOf: string; className?: string }) {
  return (
    <p className={className}>
      Data as of <time dateTime={dataAsOf}>{stamp(dataAsOf)} UTC</time>
    </p>
  );
}

/** Mirrors STALE_AFTER in export/data_api.py: the weekly refresh plus a day and a half of slack. */
const STALE_AFTER_HOURS = 132;
const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

/**
 * How old the data is, in words, with the exact watermark beneath. Past the
 * refresh window it says so in the warning ink; the words carry the state, so
 * the dot is never the only signal.
 */
export function FreshnessStatus({ dataAsOf, now }: { dataAsOf: string; now?: number }) {
  // Read once when shown: the age is a summary, not a ticking clock.
  const [mounted] = useState(() => Date.now());
  const hours = Math.max(0, ((now ?? mounted) - Date.parse(dataAsOf)) / 3_600_000);
  const stale = hours > STALE_AFTER_HOURS;
  const days = Math.round(hours / 24);
  const summary = stale
    ? `${days} days old, refresh overdue`
    : `Updated ${hours < 36 ? relative.format(-Math.round(hours), 'hour') : relative.format(-days, 'day')}`;
  return (
    <div
      className="flex items-start gap-2"
      title={
        stale
          ? 'Older than the weekly analytics refresh: the next scheduled run has not published yet.'
          : 'Within the weekly analytics refresh.'
      }
    >
      <span
        aria-hidden="true"
        className={cn(
          'mt-1 size-2 shrink-0 rounded-full ring-3',
          stale ? 'bg-warn ring-warn/20' : 'bg-ok ring-ok/20',
        )}
      />
      <div className="leading-tight">
        <p className={cn('text-xs font-medium', stale ? 'text-warn-ink' : 'text-foreground')}>
          {summary}
        </p>
        <Freshness dataAsOf={dataAsOf} className="mt-0.5 text-[11px] text-muted-foreground" />
      </div>
    </div>
  );
}

export function AppHeader({
  nav,
  onOrg,
  dataAsOf,
  toc,
  onTab,
}: {
  nav: NavModel | null;
  onOrg: (org: string) => void;
  dataAsOf?: string | null;
  toc: TocEntry[];
  onTab: (tab: string) => void;
}) {
  const { isMobile, open } = useSidebar();
  const { scrolled, titleHidden } = useHeaderScroll();
  const narrow = useMediaQuery(NARROW_HEADER);
  const parent = nav ? nav.topOf(nav.activeMacro) : null;
  return (
    <header
      className={cn(
        'sticky top-0 z-30 flex h-(--header-h) shrink-0 items-center border-b bg-card/90 px-3 backdrop-blur-xl backdrop-saturate-150 transition-shadow duration-200 md:px-0',
        scrolled && 'shadow-[0_6px_20px_-12px_rgb(15_23_42/0.35)]',
      )}
    >
      <div className="flex shrink-0 items-center gap-2 md:w-(--sidebar-width) md:justify-between md:border-r md:px-5">
        {isMobile && <SidebarTrigger className="size-8" aria-label="Open sections" />}
        <HieroBrand />
        {!isMobile && (
          <SidebarTrigger
            className="size-8 shrink-0 text-muted-foreground"
            aria-label={open ? 'Collapse navigation' : 'Expand navigation'}
          />
        )}
      </div>
      <div className="flex min-w-0 flex-1 items-center gap-2 pl-2 md:gap-4 md:px-6">
        {nav && (
          <nav aria-label="Scope" className="flex min-w-0 items-center gap-1">
            {nav.orgs.length > 1 ? (
              <OrgSwitcher
                orgs={nav.orgs}
                value={nav.shownOrg}
                onChange={onOrg}
                className="max-w-37.5 md:max-w-none"
              />
            ) : (
              <span className="inline-flex min-w-0 items-center gap-2 pl-1.5 text-sm font-semibold">
                <OrgAvatar org={nav.shownOrg} />
                <span className="truncate">{nav.shownOrg}</span>
              </span>
            )}
            {/* The page, once its own title has scrolled away: the header then
                says where the reader is without repeating a visible heading. */}
            <span
              aria-hidden={!titleHidden}
              className={cn(
                'hidden min-w-0 items-center gap-1 text-sm transition-[opacity,translate] duration-200 motion-reduce:transition-none md:flex',
                titleHidden
                  ? 'translate-y-0 opacity-100'
                  : 'pointer-events-none translate-y-1 opacity-0',
              )}
            >
              <ChevronRightIcon
                aria-hidden="true"
                className="size-3.5 shrink-0 text-muted-foreground"
              />
              {parent && parent !== nav.activeMacro && (
                <>
                  <span className="truncate text-muted-foreground">{parent}</span>
                  <ChevronRightIcon
                    aria-hidden="true"
                    className="size-3.5 shrink-0 text-muted-foreground"
                  />
                </>
              )}
              <span className="truncate font-medium">{nav.activeMacro}</span>
            </span>
          </nav>
        )}
        <div className="ml-auto flex shrink-0 items-center gap-2 md:gap-3">
          {dataAsOf && !narrow && (
            <div className="border-r pr-4">
              <FreshnessStatus dataAsOf={dataAsOf} />
            </div>
          )}
          <NavigationSearch nav={nav} toc={toc} onTab={onTab} />
          {!isMobile && (
            <div className="border-l pl-3">
              <ThemeToggle />
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
