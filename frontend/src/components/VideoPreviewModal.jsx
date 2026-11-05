import { useEffect, useRef } from 'react';

/** A large preview of one finished video, played from the real file at full resolution. */
export default function VideoPreviewModal({ jobId, clip, onClose, onEdit }) {
  const closeRef = useRef(null);
  const title = clip.title || `Clip ${clip.id}`;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="cg-preview-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="cg-preview" role="dialog" aria-modal="true" aria-label={`Preview of ${title}`}>
        <header className="cg-preview-head">
          <h2 className="cg-preview-title">{title}</h2>
          <button ref={closeRef} type="button" className="cg-preview-close" onClick={onClose} aria-label="Close preview">✕</button>
        </header>
        <video
          className="cg-preview-video"
          src={`/api/jobs/${jobId}/clips/${clip.id}.mp4?v=${clip.version || 0}`}
          controls
          autoPlay
          playsInline
        />
        <footer className="cg-preview-foot">
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={() => onEdit(clip)}>Edit this video</button>
        </footer>
      </div>
    </div>
  );
}
