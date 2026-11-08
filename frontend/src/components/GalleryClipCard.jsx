import { useState } from 'react';
import { getJSON } from '../api.js';
import './GalleryClipCard.css';

const TEXT_TAGS = { headline: 'Headline', none: 'No text' };

export default function GalleryClipCard({ jobId, clip, source, onPreview, onEdit, onExport, onUpdated }) {
  const base = `/api/jobs/${jobId}/clips/${clip.id}`;
  const title = clip.title || `Clip ${clip.id}`;
  const needsDecision = !!clip.text?.needs_decision;
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');
  // a suggested heading (hook) that is waiting to be put on the video
  const hook = clip.text?.hook;
  const hookWaiting = !!hook && !hook.approved && !!hook.text;

  // One click: approve the suggested heading. The server remakes the video, so the checklist
  // must be confirmed again (the returned clip says so).
  async function addHeading() {
    setAdding(true);
    setAddError('');
    try {
      const updated = await getJSON(`${base}/hook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // the suggested text, with the whole clip as its length (the editor can shorten it)
        body: JSON.stringify({ text: hook.text, approve: true, style: { seconds: 0 } }),
      });
      if (onUpdated) onUpdated(updated);
    } catch (e) {
      setAddError(e.message);
    } finally {
      setAdding(false);
    }
  }
  // the automatic checks of the finished video, in one quiet tag (details on hover)
  const checks = clip.checks;
  const checkTag = !checks || checks.status === 'unchecked' ? null
    : checks.status === 'ok'
      ? { label: 'Quality checked', className: 'cg-vc-tag--done', title: 'Size, length, sound and picture all look right.' }
      : { label: checks.status === 'problems' ? 'Needs a look' : `${checks.issues.length} note${checks.issues.length === 1 ? '' : 's'}`,
          className: checks.status === 'problems' ? 'cg-vc-tag--attention' : '',
          title: checks.issues.map((i) => i.message).join('\n') };
  const editTag = clip.edit?.mode === 'custom' ? clip.edit.style_name : clip.edit?.mode === 'assist' ? 'AI + Manual' : null;
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
          {checkTag && <li className={`cg-vc-tag ${checkTag.className}`} title={checkTag.title}>{checkTag.label}</li>}
          {editTag && <li className="cg-vc-tag">{editTag}</li>}
          {tags.map((t) => <li key={t} className="cg-vc-tag">{t}</li>)}
        </ul>

        {hookWaiting && (
          <div className="cg-vc-heading">
            <p className="cg-vc-desc">Suggested heading: “{hook.text}”</p>
            <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={addHeading}
              disabled={adding}>
              {adding ? 'Adding…' : 'Add heading to video'}
            </button>
            {addError && <p className="cg-text-xs cg-text-error">{addError}</p>}
          </div>
        )}

        {/* Every clip can get a heading: with no suggestion waiting, this opens the editor's Text tab */}
        {!hookWaiting && (
          <div className="cg-vc-heading">
            <p className="cg-vc-desc">
              {hook?.approved && hook.text ? `Heading on video: “${hook.text}”` : 'No heading yet.'}
            </p>
            <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={() => onEdit(clip)}>
              {hook?.approved ? 'Change heading' : 'Add heading'}
            </button>
          </div>
        )}

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
