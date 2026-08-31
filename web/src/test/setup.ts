import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom doesn't implement scrollIntoView; the jump bar calls it on click.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// Mock TanStack Table row model functions for testing
vi.mock('@tanstack/react-table', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-table')>();
  return {
    ...actual,
    getCoreRowModel: () => actual.getCoreRowModel(),
    getSortedRowModel: () => actual.getSortedRowModel(),
    getFilteredRowModel: () => actual.getFilteredRowModel(),
  };
});
afterEach(() => {
  cleanup();
  window.location.hash = '';
});
