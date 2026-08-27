/** The CSV export: provenance preamble, quoting, and the filtered-view note. */

import { describe, expect, it, vi } from 'vitest';
import { downloadCsv, type CsvExport } from '../csv';

const PAYLOAD: CsvExport = {
  name: 'roles',
  title: 'Role holders',
  columns: [
    { key: 'user', label: 'user' },
    { key: 'note', label: 'note' },
  ],
  rows: [{ user: 'alice', note: 'says "hi", loudly' }],
  total: 3,
  dataAsOf: '2026-07-25T10:00:00+00:00',
};

function captureDownload(): () => string {
  let content = '';
  vi.stubGlobal(
    'URL',
    Object.assign(Object.create(URL), {
      createObjectURL: (blob: Blob) => {
        void blob.text().then((text) => (content = text));
        return 'blob:test';
      },
      revokeObjectURL: () => {},
    }),
  );
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  return () => content;
}

describe('downloadCsv', () => {
  it('writes the provenance preamble, the filtered note, and quoted cells', async () => {
    const read = captureDownload();

    downloadCsv(PAYLOAD, { git_sha: 'abc1234', data_as_of: null });
    await vi.waitFor(() => expect(read()).not.toBe(''));

    const lines = read().split('\n');
    expect(lines[0]).toBe('# Hiero analytics — Role holders');
    expect(lines[1]).toBe('# data as of 2026-07-25 10:00 · code abc1234');
    expect(lines[2]).toBe('# 1 of 3 rows (filtered view)');
    expect(lines[3]).toBe('user,note');
    expect(lines[4]).toBe('alice,"says ""hi"", loudly"');
  });

  it('omits the filtered note when every row is exported', async () => {
    const read = captureDownload();

    downloadCsv({ ...PAYLOAD, total: 1 }, { git_sha: null, data_as_of: null });
    await vi.waitFor(() => expect(read()).not.toBe(''));

    const lines = read().split('\n');
    expect(lines[1]).toBe('# data as of 2026-07-25 10:00');
    expect(lines).not.toContain('# 1 of 3 rows (filtered view)');
  });
});
