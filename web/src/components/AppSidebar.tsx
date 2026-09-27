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
  ChevronRightIcon,
  Code2Icon,
  XIcon,
} from 'lucide-react';
/**
 * Section navigation. "Sections" lists the manifest's tabs (an umbrella tab's
 * members nest under it); "On this page" is the active tab's table of
 * contents, highlighting the group the reader is in. On phones the sidebar is
 * a Sheet opened from the header, carrying the tabs only — the page's own
 * sticky strip (SectionGroups) covers its groups there.
 *
 * Tabs are buttons, not links: the URL hash is the app's state store, and a
 * click always writes it, even on the tab already active.
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

function TabsGroup({ nav, onTab }: { nav: NavModel | null; onTab: (macro: string) => void }) {
  const { isMobile, setOpenMobile } = useSidebar();
  const select = (macro: string) => {
    onTab(macro);
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (isMobile) setOpenMobile(false);
  };
  return (
    <SidebarGroup>
      <SidebarGroupLabel className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em]">
        Workspace
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {nav
            ? nav.topTabs.map((tab) => (
                <SidebarMenuItem key={tab}>
                  <SidebarMenuButton
                    className="relative h-11 gap-3 rounded-xl px-3 text-[13px] text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground data-[active=true]:bg-brand-soft data-[active=true]:text-brand data-[active=true]:font-semibold data-[active=true]:shadow-xs"
                    isActive={tab === nav.activeTop}
                    aria-current={tab === nav.activeTop ? 'page' : undefined}
                    // An umbrella opens on its first member.
                    onClick={() => select(nav.macros.find((m) => nav.topOf(m) === tab) ?? tab)}
                  >
                    <NavigationIcon name={tab} />
                    <span className="flex-1">{tab}</span>
                    {tab === nav.activeTop && (
                      <ChevronRightIcon
                        aria-hidden="true"
                        className="ml-auto size-3.5 opacity-60"
                      />
                    )}
                  </SidebarMenuButton>
                  {tab === nav.activeTop && nav.subTabs.length > 0 && (
                    <SidebarMenuSub>
                      {nav.subTabs.map((sub) => (
                        <SidebarMenuSubItem key={sub}>
                          <SidebarMenuSubButton asChild isActive={sub === nav.activeMacro}>
                            <button
                              type="button"
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
              ))
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

function OnThisPage({ entries }: { entries: TocEntry[] }) {
  const active = useActiveSection(entries.map((entry) => entry.id));
  return (
    <SidebarGroup>
      <SidebarGroupLabel className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em]">
        On this page{' '}
        <span
          aria-hidden="true"
          className="ml-auto rounded-md bg-muted px-1.5 py-0.5 text-[9px] tracking-normal"
        >
          {entries.length}
        </span>
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {entries.map((entry, index) => (
            <SidebarMenuItem key={entry.id}>
              <SidebarMenuButton
                size="sm"
                className="h-auto min-h-9 gap-3 rounded-lg px-3 py-2 text-xs text-muted-foreground data-[active=true]:bg-transparent data-[active=true]:text-foreground"
                isActive={entry.id === active}
                aria-current={entry.id === active ? 'location' : undefined}
                onClick={() => scrollToGroup(entry.id)}
              >
                <span
                  aria-hidden="true"
                  className={`flex size-5 shrink-0 items-center justify-center rounded-full border text-[9px] tabular-nums ${entry.id === active ? 'border-brand/30 bg-brand-soft text-brand' : 'border-border text-muted-foreground'}`}
                >
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="whitespace-normal leading-snug">{entry.name}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
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
    // Below the sticky header on wide screens, rather than the default full
    // viewport height from the top edge.
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
      <div className="mx-4 mb-2 mt-6 rounded-xl border bg-card p-3.5 shadow-xs">
        <div className="flex items-center gap-3">
          <img
            src={`${import.meta.env.BASE_URL}brand/hiero-mark.svg`}
            alt=""
            width={36}
            height={36}
            className="size-9 rounded-lg bg-brand-soft p-1"
          />
          <div>
            <p className="text-xs font-semibold">Ecosystem insights</p>
            <p className="mt-0.5 text-[10px] text-muted-foreground">Built in the open</p>
          </div>
        </div>
      </div>
      <SidebarContent className="gap-0 px-2 py-2">
        <nav aria-label="Dashboard" className="flex flex-col gap-5">
          <TabsGroup nav={nav} onTab={onTab} />
          {!isMobile && toc.length > 0 && <OnThisPage entries={toc} />}
        </nav>
      </SidebarContent>
      <SidebarFooter className="gap-3 border-t p-4">
        <a
          href="https://github.com/hiero-hackers/analytics"
          target="_blank"
          rel="noopener noreferrer"
          className="group flex items-center gap-2.5 rounded-lg p-2 text-xs text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Code2Icon className="size-4" />
          <span className="flex-1">Contribute on GitHub</span>
          <ArrowUpRightIcon className="size-3.5" />
        </a>
        {isMobile ? (
          <div className="flex items-center justify-between px-2">
            <span className="text-xs text-muted-foreground">Appearance</span>
            <ThemeToggle />
          </div>
        ) : (
          <p className="px-2 text-[10px] leading-relaxed text-muted-foreground">
            Hiero · A Linux Foundation
            <br />
            Decentralized Trust project
          </p>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}
