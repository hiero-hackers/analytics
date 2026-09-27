/**
 * A governance role (maintainer, committer, triage) with the colour the role
 * has in every chart, so a table row and the chart above it speak the same
 * visual language. The word always carries the role; the dot only echoes it.
 */

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
