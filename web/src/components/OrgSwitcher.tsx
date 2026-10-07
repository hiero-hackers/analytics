/**
 * The organisation switcher: avatar and name over an invisible native <select>,
 * which keeps the platform's keyboard handling and phone picker.
 */

import { useState } from 'react';
import { ChevronsUpDownIcon } from 'lucide-react';
import { cn } from 'cn';

/**
 * Loaded from `github.com/<org>.png`: the login-based avatars.githubusercontent.com
 * URL returns a generic placeholder for organisations. Both hosts are in the CSP's
 * img-src. On failure it falls back to a monogram past the `hiero-` prefix.
 */
const HUES = ['var(--brand)', 'var(--link)', 'var(--chart-committer)', 'var(--chart-3)'];

export function OrgAvatar({ org, className }: { org: string; className?: string }) {
  // Keyed by org, so switching organisation retries the avatar.
  const [failed, setFailed] = useState<string | null>(null);
  const box = cn('size-6 shrink-0 rounded-md border', className);
  if (failed !== org) {
    return (
      <img
        src={`https://github.com/${encodeURIComponent(org)}.png?size=64`}
        alt=""
        width={24}
        height={24}
        referrerPolicy="no-referrer"
        className={cn(box, 'bg-card object-cover')}
        onError={() => setFailed(org)}
      />
    );
  }
  const name = org.replace(/^hiero-/, '') || org;
  const hue = HUES[[...org].reduce((sum, char) => sum + char.charCodeAt(0), 0) % HUES.length];
  return (
    <span
      aria-hidden="true"
      className={cn(box, 'grid place-items-center text-xs font-bold')}
      style={{
        color: hue,
        backgroundColor: `color-mix(in oklab, ${hue} 14%, transparent)`,
        borderColor: `color-mix(in oklab, ${hue} 30%, transparent)`,
      }}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

export function OrgSwitcher({
  orgs,
  value,
  onChange,
  className,
}: {
  orgs: string[];
  value: string;
  onChange: (org: string) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'relative inline-flex h-9 min-w-0 items-center gap-2 rounded-lg border border-transparent pr-2 pl-1.5 transition-colors hover:border-edge hover:bg-muted/60 has-[select:focus-visible]:ring-2 has-[select:focus-visible]:ring-ring',
        className,
      )}
    >
      <OrgAvatar org={value} />
      <span className="truncate text-sm font-semibold">{value}</span>
      <ChevronsUpDownIcon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
      <select
        aria-label="Organisation"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="absolute inset-0 size-full cursor-pointer appearance-none opacity-0"
      >
        {orgs.map((org) => (
          <option key={org} value={org}>
            {org}
          </option>
        ))}
      </select>
    </div>
  );
}
