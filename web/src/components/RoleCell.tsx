/** A governance role with its chart colour; the word carries the role, the dot only echoes it. */

const ROLE_COLORS: Record<string, string> = {
  maintainer: 'var(--chart-maintainer)',
  committer: 'var(--chart-committer)',
  triage: 'var(--chart-triage)',
};

export function RoleCell({ role }: { role: string }) {
  const color = ROLE_COLORS[role.toLowerCase()] ?? 'var(--chart-general)';
  return (
    <span className="inline-flex items-center gap-2">
      <span
        aria-hidden="true"
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      {role.replace(/_/g, ' ')}
    </span>
  );
}
