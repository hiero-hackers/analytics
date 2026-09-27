/** Global scope and navigation, kept visible while exploring the dashboard. */
import { Clock3Icon, ChevronRightIcon } from 'lucide-react';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { SidebarTrigger, useSidebar } from '@/components/ui/sidebar';
import { stamp } from '../format';
import type { NavModel } from '../nav';
import type { TocEntry } from '../toc';
import { ThemeToggle } from './ThemeToggle';
import { HieroBrand } from './HieroBrand';
import { NavigationSearch } from './NavigationSearch';

export function Freshness({ dataAsOf, className }: { dataAsOf: string; className?: string }) {
  return (
    <p className={className}>
      Data as of <time dateTime={dataAsOf}>{stamp(dataAsOf)} UTC</time>
    </p>
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
  return (
    <header className="sticky top-0 z-30 flex h-(--header-h) shrink-0 items-center border-b bg-card/95 px-3 backdrop-blur-xl md:px-0">
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
      <div className="flex min-w-0 flex-1 items-center gap-2 pl-3 md:gap-4 md:px-6">
        {nav && nav.orgs.length > 1 && (
          <div className="min-w-0">
            <span className="mb-0.5 hidden text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground md:block">
              Organization
            </span>
            <NativeSelect
              aria-label="Organisation"
              value={nav.shownOrg}
              onChange={(event) => onOrg(event.target.value)}
              className="h-8 max-w-[125px] rounded-lg border-transparent bg-transparent pl-0 text-xs font-semibold shadow-none hover:bg-muted md:max-w-none md:text-[13px]"
            >
              {nav.orgs.map((org) => (
                <NativeSelectOption key={org} value={org}>
                  {org}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
        )}
        {nav && (
          <div className="hidden min-w-0 items-center gap-3 text-xs text-muted-foreground min-[1200px]:flex">
            <ChevronRightIcon className="size-3.5" />
            <span className="truncate">{nav.activeMacro}</span>
          </div>
        )}
        <div className="ml-auto flex shrink-0 items-center gap-2 md:gap-3">
          {dataAsOf && !isMobile && (
            <div className="hidden items-center gap-2 border-r pr-4 text-muted-foreground min-[1280px]:flex">
              <Clock3Icon className="size-3.5" />
              <Freshness dataAsOf={dataAsOf} className="text-[10px]" />
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
