/**
 * The theme switch: follow the OS (the default), or force light or dark. One
 * click, current state always visible. The choice is applied and persisted by
 * theme.ts; the pre-paint script in public/ restores it on the next visit.
 *
 * A segmented ToggleGroup rather than a dropdown menu: the menu's popup
 * machinery (Floating UI, Popper, Menu) cost about 10 kB gzipped for three
 * options, and ToggleGroup already ships for the dashboard's other switches.
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
      value={choice}
      onValueChange={(value) => {
        // Radix reports "" when the active item is clicked again; a theme is
        // always chosen, so that click changes nothing.
        if (!value) return;
        applyTheme(value as ThemeChoice);
        setChoice(value as ThemeChoice);
      }}
    >
      {OPTIONS.map(({ value, label, Icon }) => (
        <ToggleGroupItem key={value} value={value} aria-label={label} title={`${label} theme`}>
          <Icon />
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
