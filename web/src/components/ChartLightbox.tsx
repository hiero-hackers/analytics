/**
 * The chart lightbox, replicating the legacy dashboard exactly: a dark
 * full-screen overlay (click outside or press Esc to close), the image capped
 * at 66vh, and the `.lbcap` caption block beneath it carrying the note and
 * step-by-step methodology on the dark background.
 */

import { useEffect } from 'react';
import { ChartInfo, type ChartInfoProps } from './ChartInfo';

export interface LightboxContent extends ChartInfoProps {
  /** Absent for text-only content (a KPI tile's explanation). */
  src?: string;
  alt: string;
  /** Heading shown above text-only content. */
  title?: string;
}

export function ChartLightbox({
  content,
  onClose,
}: {
  content: LightboxContent;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="lightbox"
      style={{ display: 'flex' }}
      onClick={onClose}
      role="dialog"
      aria-label={content.alt}
    >
      <span className="hint">click outside or press Esc to close</span>
      <button type="button" className="lbclose" aria-label="Close" onClick={onClose}>
        ✕
      </button>
      {content.src ? (
        <img src={content.src} alt={content.alt} onClick={(event) => event.stopPropagation()} />
      ) : (
        <h3 className="lbtitle" onClick={(event) => event.stopPropagation()}>
          {content.title ?? content.alt}
        </h3>
      )}
      {(content.note || content.methodology) && (
        <div className="lbcap" onClick={(event) => event.stopPropagation()}>
          <ChartInfo note={content.note} methodology={content.methodology} />
        </div>
      )}
    </div>
  );
}
