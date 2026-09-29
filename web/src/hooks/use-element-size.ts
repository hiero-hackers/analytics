import { useCallback, useState } from 'react';

export interface ElementSize {
  width: number;
  height: number;
}

/**
 * An element's border-box size, kept current by a ResizeObserver; null until
 * first measured. Layout size, so an element inside a CSS-scaled preview
 * reports the size it prints at.
 */
export function useElementSize() {
  const [size, setSize] = useState<ElementSize | null>(null);
  const ref = useCallback((element: HTMLElement | null) => {
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const box = entry?.borderBoxSize?.[0];
      const next = {
        width: box ? box.inlineSize : element.offsetWidth,
        height: box ? box.blockSize : element.offsetHeight,
      };
      setSize((current) =>
        current?.width === next.width && current.height === next.height ? current : next,
      );
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, size] as const;
}
