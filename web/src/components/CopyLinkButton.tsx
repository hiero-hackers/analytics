/**
 * "Copy link" builds a URL for the current tab/org with this section as `widget`,
 * then copies it. Label flips to "Copied!" or "Couldn't copy" and reverts on its own,
 * so the click always shows feedback whether successful or not.
 */
import { useEffect, useRef, useState } from 'react';
import { copyText, shareUrl } from '../share';

const TRANSIENT_MS = 1600;

type CopyStatus = 'idle' | 'copied' | 'failed';

const LABELS: Record<CopyStatus, string> = {
  idle: 'Copy link',
  copied: 'Copied!',
  failed: "Couldn't copy",
};

export function CopyLinkButton({ sectionId }: { sectionId: string }) {
  const [status, setStatus] = useState<CopyStatus>('idle');
  const timer = useRef<number | undefined>(undefined);
  const clickId = useRef(0);

  // A pending revert must not fire after the button unmounts.
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const onCopy = async () => {
    const id = ++clickId.current;
    const ok = await copyText(shareUrl(sectionId));
    if (id !== clickId.current) return;

    window.clearTimeout(timer.current);
    setStatus(ok ? 'copied' : 'failed');
    timer.current = window.setTimeout(() => setStatus('idle'), TRANSIENT_MS);
  };

  return (
    <button type="button" className="dl" onClick={onCopy}>
      <svg
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path
          d="M6.2 9.8 4.5 11.5a2.1 2.1 0 0 1-3-3L4.2 5.8a2.1 2.1 0 0 1 3 0"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M9.8 6.2 11.5 4.5a2.1 2.1 0 0 1 3 3L11.8 10.2a2.1 2.1 0 0 1-3 0"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {LABELS[status]}
    </button>
  );
}
