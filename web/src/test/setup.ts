import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom doesn't implement scrollIntoView; the table of contents calls it on click.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom has no matchMedia; the sidebar's useIsMobile needs one. Width queries
// answer from window.innerWidth (jsdom: 1024, i.e. desktop) so a test can go
// "mobile" by setting innerWidth before rendering; anything else is false.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query);
    return {
      matches: max ? window.innerWidth <= Number(max[1]) : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    };
  };
}

const DEFAULT_WIDTH = window.innerWidth;

afterEach(() => {
  cleanup();
  window.location.hash = '';
  window.innerWidth = DEFAULT_WIDTH;
});
