import React, { useEffect, useState } from 'react';
import { getJSON } from '../api.js';
import './CaptionsStylePanel.css';
import './TextChoicePanel.css';

// Looks and limits come from the backend, so the page only offers what it can really draw.
let optionsPromise = null;
function loadOptions() {
  if (!optionsPromise) {
    optionsPromise = getJSON('/api/headline-presets').catch((e) => {
      optionsPromise = null;
      throw e;
    });
  }
  return optionsPromise;
}

const STYLE_KEYS = ['weight', 'size', 'text_color', 'accent_color', 'position', 'uppercase', 'seconds', 'box', 'shadow'];
const DURATIONS = [
  { value: 3, label: '3 seconds' },
  { value: 4, label: '4 seconds' },
  { value: 6, label: '6 seconds' },
  { value: 10, label: '10 seconds' },
  { value: 0, label: 'The whole clip' },
];

const styleOf = (s) => Object.fromEntries(['preset', ...STYLE_KEYS].map((k) => [k, s[k]]));

export default function TextChoicePanel({ jobId, clip, onApplied, canUseCaptions, onBackToCaptions }) {
  const state = clip.text || {};
  const saved = state.headline;
  const [options, setOptions] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [draft, setDraft] = useState(null);
  const [text, setText] = useState(saved?.text || '');
  const [previewQuery, setPreviewQuery] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    loadOptions().then(setOptions).catch((e) => setLoadError(e.message));
  }, []);

  // Start from the saved headline's look, or the default look, once the options are known.
  useEffect(() => {
    if (!options) return;
    const base = saved?.style || options.presets.find((p) => p.id === options.default).style;
    setDraft(styleOf(base));
    setText(saved?.text || '');
    setError('');
  }, [options, clip.id, clip.version]); // eslint-disable-line react-hooks/exhaustive-deps

  // The preview picture is drawn by the backend with the code that draws the real headline.
  useEffect(() => {
    if (!draft) return undefined;
    const params = new URLSearchParams(Object.entries(draft).map(([k, v]) => [k, String(v)]));
    if (text.trim()) params.set('text', text.trim());
    const timer = setTimeout(() => setPreviewQuery(params.toString()), 250);
    return () => clearTimeout(timer);
  }, [draft, text]);

  if (loadError) {
    return (
      <div className="cg-panel-content">
        <h3 className="cg-heading-sm">Text</h3>
        <p className="cg-text-xs cg-caption-error">Could not load the headline looks: {loadError}</p>
      </div>
    );
  }
  if (!options || !draft) {
    return <div className="cg-panel-content"><p className="cg-text-xs cg-text-muted">Loading…</p></div>;
  }

  const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }));
  const [sizeLo, sizeHi] = options.limits.size;
  const [posLo, posHi] = options.limits.position;
  const mode = state.mode;
  const unusable = state.verdict === 'unusable';
  const typed = text.trim().length > 0;

  async function send(body, label) {
    setBusy(label);
    setError('');
    try {
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      onApplied(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  const approve = () => {
    const { preset, ...style } = draft;
    send({ headline: { text: text.trim(), preset, style }, approve: true }, 'headline');
  };

  return (
    <div className="cg-panel-content">
      <div className="cg-panel-header">
        <h3 className="cg-heading-sm">Text</h3>
        {mode === 'pending' && <span className="cg-badge cg-badge--warning">Needs your decision</span>}
        {mode === 'headline' && <span className="cg-badge cg-badge--muted">Headline</span>}
        {mode === 'none' && <span className="cg-badge cg-badge--muted">No text</span>}
      </div>

      {(mode === 'pending' || state.verdict === 'unreliable' || unusable) && (
        <div className="cg-text-status" role="note">
          <p className="cg-text-status-title">
            {unusable
              ? "ClipGenie couldn't make out the speech in this clip."
              : "ClipGenie couldn't trust the speech in this clip."}
          </p>
          <p className="cg-text-xs cg-text-muted">
            It won't show words it isn't sure about, so this clip has no captions.
            {unusable
              ? ' Tell viewers what it is about with a headline of your own, or export without text.'
              : ' Add a headline of your own, or export without text.'}
          </p>
          {state.reasons?.length > 0 && (
            <ul className="cg-text-reasons">
              {state.reasons.map((r) => <li key={r} className="cg-text-xs">{r}</li>)}
            </ul>
          )}
        </div>
      )}
      {mode === 'headline' && saved?.text && (
        <p className="cg-text-xs cg-text-muted">
          This clip shows your headline: <strong>{saved.text}</strong>. Edit it below and approve to replace it.
        </p>
      )}
      {mode === 'none' && (
        <p className="cg-text-xs cg-text-muted">This clip will be exported without any text.</p>
      )}

      <div className="cg-field">
        <label className="cg-label" htmlFor="headline-text">Your headline</label>
        <textarea
          id="headline-text"
          className="cg-input cg-headline-input"
          rows={2}
          maxLength={options.max_chars}
          value={text}
          placeholder="e.g. the topic or hook of this clip"
          onChange={(e) => setText(e.target.value)}
        />
        <p className="cg-text-xs cg-text-muted">
          Type your own words ({text.length}/{options.max_chars}). ClipGenie doesn't write headlines
          from speech it can't trust.
        </p>
      </div>

      <div className="cg-caption-preview">
        {previewQuery && <img src={`/api/headline-preview.png?${previewQuery}`} alt="Headline preview" />}
      </div>
      <p className="cg-text-xs cg-text-muted">
        Preview of the look. Nothing is added to the video until you press Approve.
      </p>

      <div className="cg-field">
        <label className="cg-label">Look</label>
        <div className="cg-caption-themes-list">
          {options.presets.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`cg-theme-card ${draft.preset === p.id ? 'active' : ''}`}
              onClick={() => setDraft(styleOf(p.style))}
            >
              <p className="cg-theme-title">{p.label}</p>
              <p className="cg-text-xs cg-text-muted">{p.description}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="cg-field">
        <label className="cg-label" htmlFor="headline-seconds">How long it stays</label>
        <select id="headline-seconds" className="cg-select" value={draft.seconds}
          onChange={(e) => set('seconds', Number(e.target.value))}>
          {DURATIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          {!DURATIONS.some((d) => d.value === draft.seconds) && (
            <option value={draft.seconds}>{draft.seconds} seconds</option>
          )}
        </select>
      </div>

      <div className="cg-field">
        <div className="cg-position-header">
          <label className="cg-label" htmlFor="headline-size">Size</label>
          <span className="cg-text-xs cg-text-secondary">{draft.size}</span>
        </div>
        <input id="headline-size" type="range" className="cg-range" min={sizeLo} max={sizeHi} step="2"
          value={draft.size} onChange={(e) => set('size', Number(e.target.value))} />
      </div>

      <div className="cg-field">
        <div className="cg-position-header">
          <label className="cg-label" htmlFor="headline-pos">Position</label>
          <span className="cg-text-xs cg-text-secondary">{draft.position}% from top</span>
        </div>
        <input id="headline-pos" type="range" className="cg-range" min={posLo} max={posHi} step="1"
          value={draft.position} onChange={(e) => set('position', Number(e.target.value))} />
      </div>

      <div className="cg-caption-colors">
        <div className="cg-field">
          <label className="cg-label" htmlFor="headline-text-color">Text colour</label>
          <input id="headline-text-color" type="color" value={draft.text_color}
            onChange={(e) => set('text_color', e.target.value.toUpperCase())} />
        </div>
        <div className="cg-field">
          <label className="cg-label" htmlFor="headline-accent">Accent colour</label>
          <input id="headline-accent" type="color" value={draft.accent_color}
            onChange={(e) => set('accent_color', e.target.value.toUpperCase())} />
        </div>
      </div>

      <div className="cg-caption-checks">
        <label className="cg-text-xs">
          <input type="checkbox" checked={draft.uppercase}
            onChange={(e) => set('uppercase', e.target.checked)} /> Capital letters
        </label>
        <label className="cg-text-xs">
          <input type="checkbox" checked={draft.shadow}
            onChange={(e) => set('shadow', e.target.checked)} /> Soft shadow
        </label>
      </div>

      {error && <p className="cg-text-xs cg-caption-error" role="alert">{error}</p>}
      {busy && (
        <p className="cg-text-xs cg-text-muted" role="status">
          Redrawing the video. This takes about half a minute…
        </p>
      )}

      <div className="cg-caption-actions">
        <button type="button" className="cg-btn cg-btn--primary cg-btn--sm"
          disabled={!typed || !!busy} onClick={approve}>
          {busy === 'headline' ? 'Adding…' : 'Approve & add to video'}
        </button>
        {mode !== 'none' && (
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={!!busy}
            onClick={() => send({ mode: 'none' }, 'none')}>
            {busy === 'none' ? 'Working…' : 'Export without text'}
          </button>
        )}
      </div>
      {canUseCaptions && mode !== 'captions' && (
        <div className="cg-caption-actions">
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={!!busy}
            onClick={() => send({ mode: 'captions' }, 'captions')}>
            {busy === 'captions' ? 'Working…' : 'Use captions instead'}
          </button>
        </div>
      )}
      {canUseCaptions && mode === 'captions' && onBackToCaptions && (
        <div className="cg-caption-actions">
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={onBackToCaptions}>
            ← Back to captions
          </button>
        </div>
      )}
      <p className="cg-text-xs cg-text-muted">
        Changing the text makes a new version of this clip, so its copyright checklist must be ticked again.
      </p>
    </div>
  );
}
