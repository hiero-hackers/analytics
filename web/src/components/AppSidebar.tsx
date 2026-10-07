import {
  UsersIcon,
  ShieldCheckIcon,
  GitPullRequestIcon,
  LandmarkIcon,
  CircleHelpIcon,
  MessagesSquareIcon,
  PackageIcon,
  LayoutDashboardIcon,
  ArrowUpRightIcon,
  Code2Icon,
  XIcon,
} from 'lucide-react';
/**
 * Tab navigation and the active tab's "On this page" list; on phones a Sheet
 * with the tabs only (SectionGroups' strip covers the groups there). Tabs are
 * buttons, not links: the URL hash is the app's state store.
 */

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from '@/components/ui/sidebar';
import { cn } from 'cn';
import type { NavModel } from '../nav';
import { useActiveSection } from '../useActiveSection';
import { scrollToGroup, type TocEntry } from '../toc';
import { Button } from '@/components/ui/button';
import { HieroBrand } from './HieroBrand';
import { ThemeToggle } from './ThemeToggle';

const navigationIcons: Record<string, typeof UsersIcon> = {
  Contributors: UsersIcon,
  Governance: LandmarkIcon,
  HIPs: GitPullRequestIcon,
  'Security & scorecards': ShieldCheckIcon,
  'Issues & onboarding': CircleHelpIcon,
  Community: MessagesSquareIcon,
  Releases: PackageIcon,
};

function NavigationIcon({ name }: { name: string }) {
  const Icon = navigationIcons[name] ?? LayoutDashboardIcon;
  return <Icon aria-hidden="true" className="size-4 shrink-0" />;
}

function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <SidebarGroupLabel className="mb-1 h-7 px-3 font-display text-[13px] font-semibold text-foreground/70">
      {children}
    </SidebarGroupLabel>
  );
}

function TabsGroup({ nav, onTab }: { nav: NavModel | null; onTab: (macro: string) => void }) {
  const { isMobile, setOpenMobile } = useSidebar();
  const select = (macro: string) => {
    onTab(macro);
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (isMobile) setOpenMobile(false);
  };
  return (
    <SidebarGroup>
      <GroupHeading>Pages</GroupHeading>
      <SidebarGroupContent>
        <SidebarMenu className="gap-0.5">
          {nav
            ? nav.topTabs.map((tab) => {
                const active = tab === nav.activeTop;
                const empty = !nav.hasData(tab);
                return (
                  <SidebarMenuItem key={tab}>
                    <SidebarMenuButton
                      className={cn(
                        'relative h-10 gap-3 rounded-lg px-3 font-display text-[14px] font-medium text-foreground/75 transition-colors',
                        'before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:bg-brand before:opacity-0 before:transition-opacity',
                        'hover:bg-sidebar-accent hover:text-foreground',
                        'data-[active=true]:bg-brand-soft/60 data-[active=true]:font-semibold data-[active=true]:text-brand data-[active=true]:before:opacity-100',
                        empty && !active && 'text-muted-foreground/70',
                      )}
                      isActive={active}
                      aria-current={active ? 'page' : undefined}
                      aria-description={empty ? `No data for ${nav.shownOrg}` : undefined}
                      // An umbrella opens on its first member.
                      onClick={() => select(nav.macros.find((m) => nav.topOf(m) === tab) ?? tab)}
                    >
                      <NavigationIcon name={tab} />
                      <span className="flex-1 truncate">{tab}</span>
                      {empty && (
                        <span
                          aria-hidden="true"
                          className="rounded-md border border-dashed px-1.5 py-px font-sans text-[10px] font-medium text-muted-foreground"
                        >
                          No data
                        </span>
                      )}
                    </SidebarMenuButton>
                    {active && nav.subTabs.length > 0 && (
                      <SidebarMenuSub>
                        {nav.subTabs.map((sub) => (
                          <SidebarMenuSubItem key={sub}>
                            <SidebarMenuSubButton asChild isActive={sub === nav.activeMacro}>
                              <button
                                type="button"
                                className="font-display"
                                aria-current={sub === nav.activeMacro ? 'page' : undefined}
                                onClick={() => select(sub)}
                              >
                                <span>{sub}</span>
                              </button>
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        ))}
                      </SidebarMenuSub>
                    )}
                  </SidebarMenuItem>
                );
              })
            : Array.from({ length: 6 }, (_, index) => (
                <SidebarMenuItem key={index}>
                  <SidebarMenuSkeleton />
                </SidebarMenuItem>
              ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

/** The page's groups on a progress rail filled up to the group the reader is in. */
function OnThisPage({ entries }: { entries: TocEntry[] }) {
  const active = useActiveSection(entries.map((entry) => entry.id));
  const current = Math.max(
    0,
    entries.findIndex((entry) => entry.id === active),
  );
  return (
    <SidebarGroup>
      <GroupHeading>On this page</GroupHeading>
      <SidebarGroupContent>
        <ol className="relative ml-3 pr-1">
          {entries.map((entry, index) => {
            const passed = index < current;
            const here = index === current;
            return (
              <li key={entry.id} className="relative">
                {index < entries.length - 1 && (
                  <span
                    aria-hidden="true"
                    className={cn(
                      'absolute top-[15px] bottom-[-15px] left-[4px] w-0.5 rounded-full transition-colors duration-300 motion-reduce:transition-none',
                      passed ? 'bg-brand' : 'bg-sidebar-border',
                    )}
                  />
                )}
                <button
                  type="button"
                  aria-current={here ? 'location' : undefined}
                  onClick={() => scrollToGroup(entry.id)}
                  className={cn(
                    'group/toc relative flex w-full items-start gap-3 rounded-md py-1.5 pr-2 pl-0 text-left text-[13px] leading-snug outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring',
                    here
                      ? 'font-medium text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      'relative z-10 mt-[5px] size-2.5 shrink-0 rounded-full border-2 transition-all duration-300 motion-reduce:transition-none',
                      here
                        ? 'border-brand bg-sidebar ring-4 ring-brand/15'
                        : passed
                          ? 'border-brand bg-brand'
                          : 'border-sidebar-border bg-sidebar group-hover/toc:border-foreground/40',
                    )}
                  />
                  <span>{entry.name}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

export function AppSidebar({
  nav,
  toc,
  onTab,
}: {
  nav: NavModel | null;
  toc: TocEntry[];
  onTab: (macro: string) => void;
}) {
  const { isMobile, setOpenMobile } = useSidebar();
  return (
    // Below the sticky header on wide screens.
    <Sidebar className="md:top-(--header-h) md:h-[calc(100svh-var(--header-h))]">
      {isMobile && (
        <SidebarHeader className="flex-row items-center justify-between border-b px-5 py-5">
          <HieroBrand compact />
          <Button
            variant="ghost"
            size="icon"
            aria-label="Close navigation"
            onClick={() => setOpenMobile(false)}
          >
            <XIcon />
          </Button>
        </SidebarHeader>
      )}
      <SidebarContent className="gap-0 px-2 pt-5 pb-2">
        <nav aria-label="Dashboard" className="flex flex-col gap-6">
          <TabsGroup nav={nav} onTab={onTab} />
          {!isMobile && toc.length > 0 && <OnThisPage entries={toc} />}
        </nav>
      </SidebarContent>
      <SidebarFooter className="gap-3 border-t p-4">
        <a
          href="https://github.com/hiero-hackers/analytics"
          target="_blank"
          rel="noopener noreferrer"
          className="group flex items-center gap-3 rounded-lg p-2 outline-none transition-colors hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-lg border bg-card text-muted-foreground transition-colors group-hover:text-foreground">
            <Code2Icon aria-hidden="true" className="size-4" />
          </span>
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block font-display text-[13px] font-semibold text-foreground">
              Contribute on GitHub
            </span>
            <span className="block truncate text-[11px] text-muted-foreground">
              hiero-hackers/analytics
            </span>
          </span>
          <ArrowUpRightIcon
            aria-hidden="true"
            className="size-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 motion-reduce:transition-none"
          />
        </a>
        {isMobile && (
          <div className="flex items-center justify-between px-2">
            <span className="text-xs text-muted-foreground">Appearance</span>
            <ThemeToggle />
          </div>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}
