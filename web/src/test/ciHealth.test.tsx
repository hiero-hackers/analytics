import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CIHealthMatrixView } from '../api';
import { CIHealthMatrix } from '../components/CIHealthMatrix';
import { ViewCards } from '../components/ViewCards';
import { downloadCsv } from '../csv';

vi.mock('../csv', () => ({ downloadCsv: vi.fn() }));

function makeView(withBands = true): CIHealthMatrixView {
  return {
    id: 'ci-health-matrix',
    kind: 'ci_health_matrix',
    macro: 'Security & scorecards',
    title: 'CI health matrix',
    description: 'CI health checks.',
    badge: '3 repositories',
    source: 'ci_health_checks.csv',
    row_header: 'Repository',
    ...(withBands && {
      bands: [
        { label: 'Actions', span: 1 },
        { label: 'Permissions', span: 1 },
        { label: 'Repository', span: 1 },
      ],
    }),
    columns: [
      { key: 'actions_sha_pinned', label: 'Actions SHA Pinned', band: 'actions' },
      { key: 'explicit_permissions', label: 'Explicit Permissions', band: 'permissions' },
      { key: 'repository_security_configuration', label: 'Security Config', band: 'repository' },
    ],
    rows: [
      {
        key: 'repo-zeta',
        label: 'repo-zeta',
        cells: [
          {
            key: 'actions_sha_pinned',
            label: 'Actions SHA Pinned',
            status: 'fail',
            evidence: 'Workflow reference is not pinned.',
            location: '.github/workflows/ci.yml:12;CODEOWNERS',
          },
          {
            key: 'explicit_permissions',
            label: 'Explicit Permissions',
            status: 'pass',
            evidence: 'Permissions are explicit.',
            location: '',
          },
          {
            key: 'repository_security_configuration',
            label: 'Security Config',
            status: 'na',
            evidence: 'No applicable repository setting.',
            location: '',
          },
        ],
      },
      {
        key: 'repo-alpha',
        label: 'repo-alpha',
        cells: [
          {
            key: 'actions_sha_pinned',
            label: 'Actions SHA Pinned',
            status: 'review',
            evidence: 'Could not verify the workflow.',
            location: '.github/workflows/test.yml',
          },
          {
            key: 'explicit_permissions',
            label: 'Explicit Permissions',
            status: 'fail',
            evidence: 'Permissions are missing.',
            location: 'ci.yml:7',
          },
          {
            key: 'repository_security_configuration',
            label: 'Security Config',
            status: 'pass',
            evidence: 'Security settings are enabled.',
            location: '',
          },
        ],
      },
      {
        key: 'repo-beta',
        label: 'repo-beta',
        cells: [
          {
            key: 'actions_sha_pinned',
            label: 'Actions SHA Pinned',
            status: 'pass',
            evidence: 'Workflow references are pinned.',
            location: '',
          },
          {
            key: 'explicit_permissions',
            label: 'Explicit Permissions',
            status: 'review',
            evidence: 'Permissions need review.',
            location: '',
          },
          {
            key: 'repository_security_configuration',
            label: 'Security Config',
            status: 'na',
            evidence: 'No applicable repository setting.',
            location: '',
          },
        ],
      },
    ],
    filters: ['pass', 'fail', 'review', 'na'],
  };
}

function bodyRowLabels(): string[] {
  return Array.from(
    document.querySelector<HTMLTableSectionElement>('.cimx tbody')!.rows,
    (row) => row.cells[0].textContent ?? '',
  );
}

describe('CI health matrix', () => {
  it('renders band labels and spans, and supports older views without bands', () => {
    const { rerender } = render(<CIHealthMatrix view={makeView()} />);
    const bandRow = document.querySelector<HTMLTableRowElement>('.cimx-band')!;

    expect(within(bandRow).getByRole('columnheader', { name: 'Actions' })).toHaveAttribute(
      'colspan',
      '1',
    );
    expect(within(bandRow).getByRole('columnheader', { name: 'Permissions' })).toBeInTheDocument();
    expect(within(bandRow).getByRole('columnheader', { name: 'Repository' })).toBeInTheDocument();

    rerender(<CIHealthMatrix view={makeView(false)} />);
    expect(document.querySelector('.cimx-band')).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Security Config' })).toBeInTheDocument();
  });

  it('keeps exported row order through status and text filtering', () => {
    const onFilteredRows = vi.fn();
    render(<CIHealthMatrix view={makeView()} onFilteredRows={onFilteredRows} />);

    expect(bodyRowLabels()).toEqual(['repo-zeta', 'repo-alpha', 'repo-beta']);

    fireEvent.click(screen.getByRole('button', { name: 'review' }));
    expect(bodyRowLabels()).toEqual(['repo-alpha', 'repo-beta']);
    expect(screen.getByRole('button', { name: 'review' })).toHaveAttribute('aria-pressed', 'true');
    expect(onFilteredRows).toHaveBeenLastCalledWith('ci-health-matrix', [
      makeView().rows[1],
      makeView().rows[2],
    ]);

    fireEvent.change(
      screen.getByRole('textbox', { name: 'Filter CI health by repository or check' }),
      {
        target: { value: 'zeta' },
      },
    );
    expect(bodyRowLabels()).toEqual([]);
  });

  it('distinguishes all statuses accessibly and keeps pass and na inert', () => {
    render(<CIHealthMatrix view={makeView()} />);

    const fail = screen.getByRole('button', { name: 'repo-zeta — Actions SHA Pinned: fail' });
    expect(fail).toHaveClass('cimx-fail');
    expect(
      screen.getByRole('button', { name: 'repo-alpha — Actions SHA Pinned: review' }),
    ).toHaveClass('cimx-review');

    const pass = screen.getByRole('cell', { name: 'repo-zeta — Explicit Permissions: pass' });
    const notApplicable = screen.getByRole('cell', {
      name: 'repo-zeta — Security Config: not applicable',
    });
    expect(pass).toHaveClass('cimx-pass');
    expect(notApplicable).toHaveClass('cimx-na');
    expect(notApplicable).toHaveTextContent('—');
    expect(pass).not.toHaveAttribute('role', 'button');
    expect(notApplicable).not.toHaveAttribute('role', 'button');

    fireEvent.click(pass);
    fireEvent.click(notApplicable);
    expect(screen.queryByText('Locations')).not.toBeInTheDocument();
  });

  it('opens evidence by click or keyboard, lists file and line locations, and closes accessibly', () => {
    render(<CIHealthMatrix view={makeView()} />);
    const clickCell = screen.getByRole('button', { name: 'repo-zeta — Actions SHA Pinned: fail' });

    fireEvent.click(clickCell);
    expect(screen.getByText('Workflow reference is not pinned.')).toBeInTheDocument();
    expect(screen.getByText('.github/workflows/ci.yml:12')).toBeInTheDocument();
    expect(screen.getByText('CODEOWNERS')).toBeInTheDocument();

    fireEvent.click(clickCell);
    expect(screen.queryByText('Workflow reference is not pinned.')).not.toBeInTheDocument();

    const reviewCell = screen.getByRole('button', {
      name: 'repo-alpha — Actions SHA Pinned: review',
    });
    fireEvent.keyDown(reviewCell, { key: 'Enter' });
    expect(screen.getByText('Could not verify the workflow.')).toBeInTheDocument();
    expect(screen.getByText('.github/workflows/test.yml')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('Could not verify the workflow.')).not.toBeInTheDocument();

    fireEvent.keyDown(clickCell, { key: ' ' });
    expect(screen.getByText('Workflow reference is not pinned.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByText('Workflow reference is not pinned.')).not.toBeInTheDocument();
  });

  it('exports filtered repositories in the incoming order', () => {
    render(
      <ViewCards
        views={[makeView()]}
        sectionDocs={[]}
        provenance={{ git_sha: null, data_as_of: null }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'review' }));
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));

    const exportedRows = vi.mocked(downloadCsv).mock.calls[0][0].rows;
    expect(exportedRows.map((row) => row.repo)).toEqual(['repo-alpha', 'repo-beta']);
  });
});
