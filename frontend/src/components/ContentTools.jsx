import { useEffect, useState } from 'react';
import { getJSON } from '../api.js';
import './ContentTools.css';

// Publishing tools for one clip: its title / description / hashtags, and a thumbnail.
// AI text is only ever a draft in the boxes: what gets copied is what YOU saved.

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const tagsToText = (tags) => (tags || []).join(' ');
const textToTags = (text) => text.split(/[\s,]+/).filter(Boolean);

export function CopyEditor({ jobId, clipId, compact = false }) {
  const base = `/api/jobs/${jobId}/clips/${clipId}`;
  const [view, setView] = useState(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  function load(v) {
    setView(v);
    setTitle(v.copy?.title || '');
    setDescription(v.copy?.description || '');
    setTags(tagsToText(v.copy?.hashtags || ['#shorts']));
  }

  useEffect(() => {
    getJSON(`${base}/copy`).then(load).catch((e) => setError(e.message));
  }, [base]);

  if (!view) return error ? <p className="cg-text-xs cg-text-error">{error}</p> : null;

  const saved = view.copy?.approved ? view.copy : null;
  const changed = !saved || saved.title !== title.trim() || (saved.description || '') !== description.trim()
    || tagsToText(saved.hashtags) !== tagsToText(textToTags(tags));
  const isDraft = view.copy?.source === 'ai' && !view.copy?.approved;

  async function act(kind) {
    setBusy(kind);
    setError('');
    try {
      load(kind === 'draft'
        ? await getJSON(`${base}/copy/draft`, { method: 'POST' })
        : await getJSON(`${base}/copy`, json('PUT', { title, description, hashtags: textToTags(tags) })));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  async function copyAll() {
    const parts = [saved.title, saved.description, tagsToText(saved.hashtags), view.credits].filter(Boolean);
    try {
      await navigator.clipboard.writeText(parts.join('\n\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Your browser didn't allow copying. Select the text and copy it yourself.");
    }
  }

  return (
    <div className={`cg-ct ${compact ? 'cg-ct--compact' : ''}`}>
      {isDraft && <p className="cg-ct-draft">AI draft from what is said in this clip. Check it, change anything, then Save.</p>}
      <label className="cg-ct-field">
        <span className="cg-label">Title</span>
        <input className="cg-input" value={title} maxLength={view.limits.title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Write a title" />
      </label>
      <label className="cg-ct-field">
        <span className="cg-label">Description</span>
        <textarea className="cg-input cg-ct-textarea" value={description} maxLength={view.limits.description} rows={3}
          onChange={(e) => setDescription(e.target.value)} placeholder="What will viewers hear?" />
      </label>
      <label className="cg-ct-field">
        <span className="cg-label">Hashtags <span className="cg-text-muted">(up to {view.limits.hashtags})</span></span>
        <input className="cg-input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="#shorts #cooking" />
      </label>
      {view.credits && <p className="cg-ct-credits"><strong>Attribution (always added):</strong> {view.credits}</p>}
      {error && <p className="cg-text-xs cg-text-error">{error}</p>}
      <div className="cg-ct-actions">
        {view.can_draft ? (
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={!!busy} onClick={() => act('draft')}>
            {busy === 'draft' ? <><span className="cg-spinner" /> Writing…</> : 'Suggest with AI'}
          </button>
        ) : (
          <span className="cg-text-xs cg-text-muted">The speech in this clip couldn't be trusted, so there are no AI suggestions. Write your own.</span>
        )}
        <div style={{ flex: 1 }} />
        <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={!!busy || !title.trim() || !changed}
          onClick={() => act('save')}>{busy === 'save' ? 'Saving…' : saved && !changed ? 'Saved' : 'Save'}</button>
        <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={!saved || changed}
          title={!saved || changed ? 'Save your text first' : 'Copy title, description, hashtags and attribution'}
          onClick={copyAll}>{copied ? '✓ Copied' : 'Copy all'}</button>
      </div>
    </div>
  );
}

export function ThumbnailMaker({ jobId, clipId, confirmed }) {
  const base = `/api/jobs/${jobId}/clips/${clipId}`;
  const [view, setView] = useState(null);
  const [frame, setFrame] = useState(null);
  const [text, setText] = useState('');
  const [preset, setPreset] = useState('poster');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  function load(v, first = false) {
    setView(v);
    if (first) {
      setFrame(v.chosen?.frame ?? v.frames[0]?.index ?? null);
      setText(v.chosen?.text ?? v.suggested_text ?? '');
      setPreset(v.chosen?.preset || 'poster');
    } else if (frame === null || !v.frames.some((f) => f.index === frame)) {
      setFrame(v.frames[0]?.index ?? null);
    }
  }

  useEffect(() => {
    getJSON(`${base}/thumbnails`).then((v) => load(v, true)).catch((e) => setError(e.message));
  }, [base]);          // eslint-disable-line react-hooks/exhaustive-deps

  if (!view) return error ? <p className="cg-text-xs cg-text-error">{error}</p> : null;

  async function act(kind) {
    setBusy(kind);
    setError('');
    try {
      load(kind === 'frames'
        ? await getJSON(`${base}/thumbnails/frames`, { method: 'POST' })
        : await getJSON(`${base}/thumbnails`, json('POST', { frame, text, preset })));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  const canDownload = confirmed ?? view.confirmed;
  const made = view.made['9x16'] && view.made['16x9'];
  const stamp = `?t=${view.stamp}`;

  return (
    <div className="cg-ct">
      {view.frames.length === 0 ? (
        <div className="cg-ct-empty">
          <p className="cg-text-sm">CocoGenie looks through this clip for its sharpest, best-lit frames, with a face if there is one.</p>
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={!!busy} onClick={() => act('frames')}>
            {busy === 'frames' ? <><span className="cg-spinner" /> Looking…</> : 'Find the best frames'}
          </button>
        </div>
      ) : (
        <>
          <span className="cg-label">1. Choose a frame</span>
          <div className="cg-ct-frames" role="radiogroup" aria-label="Frames">
            {view.frames.map((f) => (
              <button key={f.index} type="button" role="radio" aria-checked={frame === f.index}
                className={`cg-ct-frame ${frame === f.index ? 'is-on' : ''}`} onClick={() => setFrame(f.index)}
                title={`At ${f.t}s${f.faces ? ' · face' : ''}`}>
                <img src={`${base}/thumbnails/frames/${f.index}.jpg?v=${view.frames.length}-${f.t}`} alt={`Frame at ${f.t} seconds`} />
              </button>
            ))}
          </div>
          <label className="cg-ct-field">
            <span className="cg-label">2. Text on the thumbnail <span className="cg-text-muted">(optional)</span></span>
            <input className="cg-input" value={text} maxLength={view.max_chars} onChange={(e) => setText(e.target.value)}
              placeholder="A few words, or leave empty" />
          </label>
          <div className="cg-ct-presets">
            {view.presets.map((p) => (
              <button key={p.id} type="button" className={`cg-ct-preset ${preset === p.id ? 'is-on' : ''}`} onClick={() => setPreset(p.id)}>
                {p.label}
              </button>
            ))}
          </div>
          {error && <p className="cg-text-xs cg-text-error">{error}</p>}
          <div className="cg-ct-actions">
            <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={!!busy} onClick={() => act('frames')}>
              {busy === 'frames' ? 'Looking…' : 'Find frames again'}
            </button>
            <div style={{ flex: 1 }} />
            <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={!!busy || frame === null} onClick={() => act('make')}>
              {busy === 'make' ? <><span className="cg-spinner" /> Making…</> : made ? 'Make again' : 'Make thumbnail'}
            </button>
          </div>
        </>
      )}
      {view.frames.length === 0 && error && <p className="cg-text-xs cg-text-error">{error}</p>}

      {made && (
        <div className="cg-ct-results">
          {view.outdated && <p className="cg-text-xs cg-text-muted">The clip was edited after this thumbnail was made. Make it again to match.</p>}
          <div className="cg-ct-previews">
            {[['9x16', 'Shorts / Reels · 1080 × 1920'], ['16x9', 'YouTube · 1280 × 720']].map(([size, label]) => (
              <figure key={size} className={`cg-ct-preview cg-ct-preview--${size}`}>
                <img src={`${base}/thumbnails/${size}.png${stamp}`} alt={`Thumbnail ${label}`} />
                <figcaption className="cg-text-xs">
                  {label}
                  {canDownload
                    ? <a className="cg-btn cg-btn--secondary cg-btn--sm" href={`${base}/thumbnails/${size}/download`} download>↓ PNG</a>
                    : null}
                </figcaption>
              </figure>
            ))}
          </div>
          {!canDownload && <p className="cg-text-xs cg-text-muted">Downloads unlock once the copyright checklist for this clip is complete (in Export).</p>}
        </div>
      )}
    </div>
  );
}
