/**
 * URL-state hooks: hand-edited indexes, and the buffered writer a brush drag uses
 * so it cannot exhaust Safari's `replaceState` budget mid-drag.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseIndex, useBufferedUrlParam } from '../urlState';

afterEach(() => vi.useRealTimers());

describe('parseIndex', () => {
  it.each([
    ['2', 2],
    ['0', 0],
    ['-1', 0],
    ['x', 0],
    ['', 0],
    [undefined, 0],
    ['1e999', 1],
  ])('reads %s as %i', (raw, index) => {
    expect(parseIndex(raw)).toBe(index);
  });
});

describe('useBufferedUrlParam', () => {
  it('previews every move but writes the URL once, after the moves stop', () => {
    vi.useFakeTimers();
    const replace = vi.spyOn(window.history, 'replaceState');
    const { result } = renderHook(() => useBufferedUrlParam('chart.range', 'all'));

    for (let end = 1; end <= 150; end += 1) act(() => result.current[1](`2020-01~2020-${end}`));

    expect(result.current[0]).toBe('2020-01~2020-150');
    expect(replace).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(300));
    expect(replace).toHaveBeenCalledTimes(1);
    expect(window.location.hash).toBe('#chart.range=2020-01%7E2020-150');
  });

  it('writes at once on set, dropping a pending preview', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useBufferedUrlParam('chart.range', 'all'));

    act(() => result.current[1]('2020-01~2020-06'));
    act(() => result.current[2]('12'));
    expect(window.location.hash).toBe('#chart.range=12');
    act(() => void vi.advanceTimersByTime(300));
    expect(window.location.hash).toBe('#chart.range=12');

    act(() => result.current[2]('all'));
    expect(window.location.hash).toBe('');
  });

  it('writes a preview still pending when the chart unmounts', () => {
    vi.useFakeTimers();
    const { result, unmount } = renderHook(() => useBufferedUrlParam('chart.range', 'all'));
    act(() => result.current[1]('2020-01~2020-06'));
    unmount();
    expect(window.location.hash).toBe('#chart.range=2020-01%7E2020-06');
  });
});
