import './GalleryClipCard.css';

const TEXT_TAGS = { headline: 'Headline', none: 'No text' };

export default function GalleryClipCard({ jobId, clip, source, onPreview, onEdit, onExport }) {
  const base = `/api/jobs/${jobId}/clips/${clip.id}`;
  const title = clip.title || `Clip ${clip.id}`;
  const needsDecision = !!clip.text?.needs_decision;
  const tags = [];
  if (clip.mood && clip.mood !== 'other') tags.push(clip.mood);
  if (TEXT_TAGS[clip.text?.mode]) tags.push(TEXT_TAGS[clip.text.mode]);

  return (
    <article className="cg-vc" aria-label={title}>
      {/* A still of the real clip (first frames only, nothing plays here). Click for a large preview. */}
      <div className="cg-vc-stage">
        <button type="button" className="cg-vc-thumb" onClick={() => onPreview(clip)}
          aria-label={`Preview ${title}`}>
          <video
            src={`${base}.mp4?v=${clip.version || 0}#t=0.5`}
            preload="metadata"
            muted
            playsInline
            tabIndex={-1}
          />
          <span className="cg-vc-duration">{Math.round(clip.duration)}s</span>
          <span className="cg-vc-preview">
            <svg width="11" height="11" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.5v11l9-5.5z" fill="currentColor" /></svg>
            Preview
          </span>
        </button>
      </div>

      <div className="cg-vc-body">
        <h3 className="cg-vc-title">{title}</h3>
        {needsDecision ? (
          <p className="cg-vc-desc">Choose a headline or export without text before downloading.</p>
        ) : clip.reason ? (
          <p className="cg-vc-desc">{clip.reason}</p>
        ) : null}

        <ul className="cg-vc-tags">
          {needsDecision && <li className="cg-vc-tag cg-vc-tag--attention">Needs your choice</li>}
          {clip.confirmed && <li className="cg-vc-tag cg-vc-tag--done">Confirmed</li>}
          {tags.map((t) => <li key={t} className="cg-vc-tag">{t}</li>)}
        </ul>

        {source && (
          <p className="cg-vc-source" title={source.host || undefined}>{source.label}</p>
        )}

        {clip.warnings?.length > 0 && (
          <ul className="cg-vc-warnings">
            {clip.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        )}
      </div>

      <div className="cg-vc-actions">
        <button type="button" className="cg-btn cg-btn--secondary" onClick={() => onEdit(clip)}
          title="Open in the editor">
          Edit
        </button>
        <button type="button" className="cg-btn cg-btn--primary"
          onClick={() => (needsDecision || !onExport ? onEdit(clip) : onExport(clip))}
          title={needsDecision ? 'Choose how text appears before exporting' : 'Export / Download'}>
          {needsDecision ? 'Choose text' : 'Export'}
        </button>
      </div>
    </article>
  );
}
