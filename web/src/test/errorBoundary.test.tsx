/**
 * A section that throws while rendering is contained to that section, and its
 * reset drops only that section's view state from the URL.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SectionBoundary } from '../components/ErrorBoundary';
import { readParam } from '../urlState';

/** Throws while its section's URL state is set, as a stale share link would. */
function Fragile() {
  if (readParam('fragile.tab')) throw new TypeError('bad tab');
  return <p>Rendered fine</p>;
}

describe('SectionBoundary', () => {
  it('replaces only the failing section and recovers once its view state is dropped', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    window.location.hash = 'fragile.tab=-1&other.tab=2';
    render(
      <>
        <SectionBoundary id="fragile" title="Fragile section">
          <Fragile />
        </SectionBoundary>
        <p>Sibling section</p>
      </>,
    );

    expect(screen.getByText('Could not display Fragile section.')).toBeInTheDocument();
    expect(screen.getByText('Sibling section')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Reset this view' }));

    expect(screen.getByText('Rendered fine')).toBeInTheDocument();
    expect(window.location.hash).toBe('#other.tab=2');
  });
});
