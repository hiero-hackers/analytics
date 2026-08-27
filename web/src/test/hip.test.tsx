/**
 * The HIPs tab: the governance board and coverage matrix views, their
 * interactions (filters, pills, cell evidence, board-to-matrix jump), and the
 * tab's own explainer replacing the shared column glossary.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { stubApi } from './fixtures';

beforeEach(() => {
  vi.unstubAllGlobals();
  stubApi();
  // jsdom performs no layout and ships no scrollIntoView.
  Element.prototype.scrollIntoView = vi.fn();
});

const openHips = async () => {
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'HIPs' }));
  return await screen.findByText('Implementation coverage matrix');
};

const matrixCard = () =>
  screen.getByText('Implementation coverage matrix').closest('.tsec') as HTMLElement;
const boardCard = () =>
  screen.getByText('Where specs sit in governance').closest('.tsec') as HTMLElement;

describe('HIPs tab', () => {
  it('renders the board and matrix as cards, board first, with badges', async () => {
    await openHips();

    const titles = screen
      .getAllByRole('heading', { level: 2 })
      .map((heading) => heading.textContent);
    expect(titles.indexOf('Where specs sit in governance')).toBeLessThan(
      titles.indexOf('Implementation coverage matrix'),
    );
    expect(screen.getByText('3 specs')).toBeInTheDocument();
    expect(screen.getByText('3 HIPs')).toBeInTheDocument();
  });

  it("shows the tab's own explainer instead of the shared glossary", async () => {
    await openHips();

    expect(screen.getByText('How to read this tab — what the numbers mean')).toBeInTheDocument();
    expect(screen.getByText('What is measured.')).toBeInTheDocument();
    expect(screen.getByText('evidence')).toBeInTheDocument(); // *emphasis* rendered as <em>
    // The Governance tab's column glossary must not leak onto this tab.
    expect(screen.queryByText('How to read this — what each column means')).not.toBeInTheDocument();
  });

  it('renders bands, heat cells, open-only markers, and every gap state', async () => {
    await openHips();
    const matrix = matrixCard();

    expect(within(matrix).getByText('Services')).toBeInTheDocument();
    expect(within(matrix).getByText('SDKs')).toBeInTheDocument();
    // 3 merged -> m2 bucket (ceilings 2,5,15,40); 44 merged -> m5.
    expect(within(matrix).getByText('3').className).toContain('m2');
    expect(within(matrix).getByText('44').className).toContain('m5');
    expect(within(matrix).getAllByText('○').length).toBeGreaterThan(0);
    expect(within(matrix).getByText('✓ all SDKs')).toBeInTheDocument();
    expect(within(matrix).getByText('no activity found')).toBeInTheDocument();
    expect(within(matrix).getByText('java · go')).toBeInTheDocument();
    expect(within(matrix).getByText('3 rows')).toBeInTheDocument();
  });

  it('filters by text and by governance pill, and pills toggle off', async () => {
    await openHips();
    const matrix = matrixCard();

    await userEvent.type(
      within(matrix).getByPlaceholderText('Filter by HIP number or title…'),
      'airdrops',
    );
    expect(within(matrix).getByText('1 rows')).toBeInTheDocument();
    await userEvent.clear(within(matrix).getByPlaceholderText('Filter by HIP number or title…'));

    await userEvent.click(within(matrix).getByRole('button', { name: 'Deferred' }));
    expect(within(matrix).getByText('1 rows')).toBeInTheDocument();
    expect(within(matrix).queryByText('HIP-1200')).not.toBeInTheDocument();

    await userEvent.click(within(matrix).getByRole('button', { name: 'Deferred' }));
    expect(within(matrix).getByText('3 rows')).toBeInTheDocument();
  });

  it('opens the evidence panel from a cell, flags uncounted references, toggles closed', async () => {
    await openHips();
    const matrix = matrixCard();

    const cell = within(matrix).getByText('3');
    await userEvent.click(cell);

    expect(within(matrix).getByText('HIP-1200 · hiero-ledger/consensus')).toBeInTheDocument();
    expect(within(matrix).getByText('2 referencing PRs')).toBeInTheDocument();
    expect(within(matrix).getByText('merged 2026-06-02')).toBeInTheDocument();
    expect(within(matrix).getByText('matched in: title, branch')).toBeInTheDocument();
    expect(within(matrix).getByText('not counted — “prepares for”')).toBeInTheDocument();
    const link = within(matrix).getByRole('link', { name: '#88' });
    expect(link).toHaveAttribute('href', 'https://github.com/hiero-ledger/consensus/pull/88');

    await userEvent.click(cell); // same cell toggles closed
    expect(within(matrix).queryByText('2 referencing PRs')).not.toBeInTheDocument();
  });

  it('cells without evidence do not open a panel', async () => {
    await openHips();
    const matrix = matrixCard();

    await userEvent.click(within(matrix).getByText('44'));
    expect(within(matrix).queryByText(/referencing PR/)).not.toBeInTheDocument();
  });

  it('board chip shows the info bar; the jump clears filters and flashes the row', async () => {
    await openHips();
    const board = boardCard();
    const matrix = matrixCard();

    // Filter the target row out first, so the jump has to restore it.
    await userEvent.click(within(matrix).getByRole('button', { name: 'Deferred' }));
    expect(within(matrix).queryByText('HIP-1200')).not.toBeInTheDocument();

    await userEvent.click(within(board).getByRole('button', { name: 'HIP-1200' }));
    expect(within(board).getByText('Throughput')).toBeInTheDocument();
    await userEvent.click(within(board).getByRole('button', { name: 'Show in coverage matrix ↓' }));

    expect(within(matrix).getByText('3 rows')).toBeInTheDocument(); // filters cleared
    const row = matrix.querySelector('#hipmx-row-1200');
    expect(row?.className).toContain('flash');
  });

  it('the evidence table itself still renders as a section with hip formatting', async () => {
    await openHips();

    const evidenceCard = screen.getByText('Evidence (per PR)').closest('.tsec') as HTMLElement;
    expect(within(evidenceCard).getAllByText('HIP-1200').length).toBeGreaterThan(0);
  });
});

describe('HIPs tab ordering', () => {
  it('puts the views ahead of the chart galleries, then the tables', async () => {
    await openHips();

    // Legacy order (pipelines/dashboard.py): custom sections + charts + tables.
    const titles = screen
      .getAllByRole('heading', { level: 2 })
      .map((heading) => heading.textContent);
    expect(titles).toEqual([
      'Where specs sit in governance',
      'Implementation coverage matrix',
      'Evidence (per PR)',
    ]);
  });
});
