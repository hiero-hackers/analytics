/**
 * The sticky app header: wordmark, the global org switcher, the data's
 * freshness, and the theme menu. It renders in every state — loading, error,
 * loaded — so the chrome never pops in after the fact; the parts that need a
 * manifest simply wait for one.
 */

import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { SidebarTrigger, useSidebar } from '@/components/ui/sidebar';
import { stamp } from '../format';
import type { NavModel } from '../nav';
import { ThemeToggle } from './ThemeToggle';

/** "Data as of …" — the manifest's data watermark, not the build time. */
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
}: {
  nav: NavModel | null;
  onOrg: (org: string) => void;
  dataAsOf?: string | null;
}) {
  const { isMobile } = useSidebar();
  return (
    <header className="sticky top-0 z-20 flex h-13 shrink-0 items-center gap-2 border-b bg-card px-3 md:px-4">
      <SidebarTrigger className="md:hidden" aria-label="Open sections" />
      {/* On wide screens the wordmark column is the sidebar's width, so the org
          switcher starts exactly where the content column does (16px header
          padding + sidebar + 8px gap = sidebar + the content's 24px padding). */}
      <div className="md:w-(--sidebar-width)">
        <div className="flex items-center gap-2 text-[15px] font-semibold tracking-tight whitespace-nowrap">
          <span
            aria-hidden="true"
            className="flex size-7 items-center justify-center rounded-lg bg-link text-sm font-bold text-white"
          >
            H
          </span>
          Hiero analytics
        </div>
      </div>
      {nav && nav.orgs.length > 1 && (
        // The org is the outermost scope — everything below is "this org's
        // view" — so it sits in the header, above the tabs it filters.
        <NativeSelect
          aria-label="Organisation"
          value={nav.shownOrg}
          onChange={(event) => onOrg(event.target.value)}
        >
          {nav.orgs.map((org) => (
            <NativeSelectOption key={org} value={org}>
              {org}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      )}
      <div className="ml-auto flex items-center gap-3">
        {dataAsOf && !isMobile && (
          <Freshness dataAsOf={dataAsOf} className="text-xs text-muted-foreground" />
        )}
        {/* No room beside the org switcher on a phone: there the theme
            switch sits at the foot of the navigation Sheet (AppSidebar). */}
        {!isMobile && <ThemeToggle />}
      </div>
    </header>
  );
}
