/**
 * System / light / dark switch; theme.ts applies and persists the choice. A
 * ToggleGroup rather than a dropdown, which would add about 10 kB gzipped.
 */

import { useState } from 'react';
import { MonitorIcon, MoonIcon, SunIcon } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { applyTheme, readTheme, type ThemeChoice } from '../theme';

const OPTIONS = [
  { value: 'system', label: 'System', Icon: MonitorIcon },
  { value: 'light', label: 'Light', Icon: SunIcon },
  { value: 'dark', label: 'Dark', Icon: MoonIcon },
] as const;

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(readTheme);

  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      spacing={0}
      aria-label="Theme"
      className="rounded-lg border bg-background p-1"
      value={choice}
      onValueChange={(value) => {
        // Radix reports "" when the active item is clicked again; keep the choice.
        if (!value) return;
        applyTheme(value as ThemeChoice);
        setChoice(value as ThemeChoice);
      }}
    >
      {OPTIONS.map(({ value, label, Icon }) => (
        <ToggleGroupItem
          key={value}
          value={value}
          aria-label={label}
          title={`${label} theme`}
          className="size-7 rounded-md border-0 bg-transparent text-muted-foreground data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-sm"
        >
          <Icon />
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
