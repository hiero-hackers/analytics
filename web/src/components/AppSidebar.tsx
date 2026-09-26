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
import { ThemeToggle } from './ThemeToggle';

function TabsGroup({ nav, onTab }: { nav: NavModel | null; onTab: (macro: string) => void }) {
  const { isMobile, setOpenMobile } = useSidebar();
  const select = (macro: string) => {
    onTab(macro);
    if (isMobile) setOpenMobile(false);
  };
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Sections</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {nav
            ? nav.topTabs.map((tab) => (
                <SidebarMenuItem key={tab}>
                  <SidebarMenuButton
                    isActive={tab === nav.activeTop}
                    aria-current={tab === nav.activeTop ? 'page' : undefined}
                    // An umbrella opens on its first member.
                    onClick={() => select(nav.macros.find((m) => nav.topOf(m) === tab) ?? tab)}
                  >
                    <span>{tab}</span>
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
      <SidebarGroupLabel>On this page</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {entries.map((entry) => (
            <SidebarMenuItem key={entry.id}>
              <SidebarMenuButton
                size="sm"
                isActive={entry.id === active}
                aria-current={entry.id === active ? 'location' : undefined}
                onClick={() => scrollToGroup(entry.id)}
              >
                <span>{entry.name}</span>
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
  const { isMobile } = useSidebar();
  return (
    // Below the sticky header on wide screens, rather than the default full
    // viewport height from the top edge.
    <Sidebar className="md:top-13 md:h-[calc(100svh-3.25rem)]">
      <SidebarContent className="py-2">
        <nav aria-label="Dashboard" className="flex flex-col">
          <TabsGroup nav={nav} onTab={onTab} />
          {!isMobile && toc.length > 0 && <OnThisPage entries={toc} />}
        </nav>
      </SidebarContent>
      {isMobile && (
        // The header has no room for it on a phone (see AppHeader).
        <SidebarFooter className="flex-row items-center justify-between border-t px-4 py-3">
          <span className="text-xs text-muted-foreground">Theme</span>
          <ThemeToggle />
        </SidebarFooter>
      )}
    </Sidebar>
  );
}
