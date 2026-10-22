import { useState } from 'react';
import { brandLogo } from '../brand';

/**
 * The dashboard's mark, top left. Each organisation may carry a `brand` key in
 * the manifest (set on its profile in `config/orgs.py`); its logo set lives at
 * `public/brand/<key>/logo.svg` and `logo-dark.svg`, so adding one is files
 * only. No key, an unsafe key, or a logo that fails to load shows the Hiero
 * mark, from the official assets described in public/brand/README.md.
 */

export function Brand({
  compact = false,
  brand,
  label,
}: {
  compact?: boolean;
  /** The shown organisation's brand key; the Hiero mark when absent. */
  brand?: string;
  /** The shown organisation's name, used to label a custom brand. */
  label?: string;
}) {
  const base = import.meta.env.BASE_URL;
  // Keyed by brand, so switching organisation retries its logo.
  const [failed, setFailed] = useState<string | null>(null);
  const custom = failed === brand ? null : brandLogo(brand, base);
  const logo = custom ?? {
    light: `${base}brand/hiero-logo.svg`,
    dark: `${base}brand/hiero-logo-dark.svg`,
  };
  const name = custom && label ? `${label} analytics` : 'Hiero analytics';
  const onError = () => setFailed(brand ?? null);
  return (
    <div className="flex shrink-0 items-center gap-3" aria-label={name}>
      <span className="sr-only">{name}</span>
      <img
        key={`light-${logo.light}`}
        src={logo.light}
        alt=""
        width={112}
        height={35}
        onError={custom ? onError : undefined}
        className="h-auto max-h-9 w-[90px] object-contain object-left dark:hidden sm:w-28"
      />
      <img
        key={`dark-${logo.dark}`}
        src={logo.dark}
        alt=""
        width={112}
        height={35}
        onError={custom ? onError : undefined}
        className="hidden h-auto max-h-9 w-[90px] object-contain object-left dark:block sm:w-28"
      />
      {!compact && (
        <span
          aria-hidden="true"
          className="hidden border-l pl-3 text-sm font-medium text-muted-foreground min-[1100px]:block"
        >
          Analytics
        </span>
      )}
    </div>
  );
}
