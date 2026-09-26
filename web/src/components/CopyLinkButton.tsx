/**
 * "Copy link" builds a URL for the current tab/org with this section as `widget`,
 * then copies it. Label flips to "Copied!" or "Couldn't copy" and reverts on its own,
 * so the click always shows feedback whether successful or not.
 */
import { useEffect, useRef, useState } from 'react';
import { CheckIcon, LinkIcon, XIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { copyText, shareUrl } from '../share';

const TRANSIENT_MS = 1600;

type CopyStatus = 'idle' | 'copied' | 'failed';

const LABELS: Record<CopyStatus, string> = {
  idle: 'Copy link',
  copied: 'Copied!',
  failed: "Couldn't copy",
};

const ICONS = { idle: LinkIcon, copied: CheckIcon, failed: XIcon } as const;

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

  const Icon = ICONS[status];
  return (
    <Button type="button" variant="outline" size="sm" onClick={onCopy}>
      <Icon data-icon="inline-start" />
      {/* Announced when it flips, so the result isn't visual-only. */}
      <span aria-live="polite">{LABELS[status]}</span>
    </Button>
  );
}
