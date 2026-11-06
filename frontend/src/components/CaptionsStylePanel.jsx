import React, { useEffect, useMemo, useState } from 'react';
import { getJSON } from '../api.js';
import TextChoicePanel from './TextChoicePanel.jsx';
import './CaptionsStylePanel.css';

// The looks and limits come from the backend, so the page can never offer something it can't draw.
let optionsPromise = null;
function loadOptions() {
  if (!optionsPromise) {
    optionsPromise = getJSON('/api/caption-presets').catch((e) => {
      optionsPromise = null;
      throw e;
    });
  }
  return optionsPromise;
}

const STYLE_KEYS = ['weight', 'size', 'text_color', 'highlight_color', 'position', 'animation',
  'uppercase', 'words_per_line', 'box', 'outline', 'shadow', 'script'];

const LABELS = {
  weight: { semibold: 'Semibold', bold: 'Bold', extrabold: 'Extra bold' },
  animation: { none: 'None (steady line)', highlight: 'Highlight spoken word', pop: 'Highlight + pop' },
  box: { none: 'No box', pill: 'Pill behind spoken word', bar: 'Bar behind the line' },
};

// Clips made before the script choice existed show Hindi words as heard ("original").
const styleOf = (s) => ({ ...Object.fromEntries(['preset', ...STYLE_KEYS].map((k) => [k, s[k]])),
  script: s.script || 'original' });
const wordsOf = (c) => (c?.words || []).map((w) => w.text);
const DEVANAGARI = /[\u0900-\u097F]/;
const isHindi = (c) => (c?.words || []).some((w) => w.orig || DEVANAGARI.test(w.text));

function CaptionsEditor({ jobId, clip, onApplied, onOtherText }) {
  const caps = clip.captions;
  const [options, setOptions] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [draft, setDraft] = useState(caps ? styleOf(caps.style) : null);
  const [texts, setTexts] = useState(wordsOf(caps));
  const [previewQuery, setPreviewQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadOptions().then(setOptions).catch((e) => setLoadError(e.message));
  }, []);

  // A new version of the clip (after Apply) starts a fresh draft from what was really saved.
  useEffect(() => {
    if (caps) {
      setDraft(styleOf(caps.style));
      setTexts(wordsOf(caps));
    }
    setError('');
  }, [clip.id, clip.version]); // eslint-disable-line react-hooks/exhaustive-deps

  // The preview picture is drawn by the backend with the real caption code (after a short pause).
  useEffect(() => {
    if (!draft) return undefined;
    const query = new URLSearchParams(Object.entries(draft).map(([k, v]) => [k, String(v)])).toString();
    const timer = setTimeout(() => setPreviewQuery(query), 250);
    return () => clearTimeout(timer);
  }, [draft]);

  const savedWords = useMemo(() => wordsOf(caps), [caps]);
  const wordsChanged = texts.some((t, i) => t !== savedWords[i]);
  const styleChanged = draft && caps
    && STYLE_KEYS.concat('preset').some((k) => draft[k] !== styleOf(caps.style)[k]);
  const dirty = wordsChanged || styleChanged;

  if (!caps) {
    return (
      <div className="cg-panel-content">
        <h3 className="cg-heading-sm">Captions</h3>
        <p className="cg-text-xs cg-text-muted">
          This clip was made before captions could be changed. Make new clips from this video
          to edit their captions.
        </p>
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="cg-panel-content">
        <h3 className="cg-heading-sm">Captions</h3>
        <p className="cg-text-xs cg-caption-error">Could not load the caption looks: {loadError}</p>
      </div>
    );
  }
  if (!options || !draft) {
    return <div className="cg-panel-content"><p className="cg-text-xs cg-text-muted">Loading…</p></div>;
  }

  const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }));
  const [sizeLo, sizeHi] = options.limits.size;
  const [posLo, posHi] = options.limits.position;
  const [wplLo, wplHi] = options.limits.words_per_line;
  const [outLo, outHi] = options.limits.outline;

  async function apply() {
    setBusy(true);
    setError('');
    try {
      const { preset, ...style } = draft;
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/captions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset, style, words: wordsChanged ? texts : null }),
      });
      onApplied(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function revert() {
    setDraft(styleOf(caps.style));
    setTexts(savedWords);
    setError('');
  }

  return (
    <div className="cg-panel-content">
      <div className="cg-panel-header">
        <h3 className="cg-heading-sm">Captions</h3>
        {dirty && <span className="cg-badge cg-badge--muted">Not applied yet</span>}
      </div>

      <div className="cg-caption-preview">
        {previewQuery && <img src={`/api/caption-preview.png?${previewQuery}`} alt="Caption preview" />}
      </div>
      <p className="cg-text-xs cg-text-muted">
        Sample of the look. Press Apply to redraw the captions on this clip.
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
        <label className="cg-label" htmlFor="cap-weight">Font weight</label>
        <select id="cap-weight" className="cg-select" value={draft.weight}
          onChange={(e) => set('weight', e.target.value)}>
          {options.weights.map((w) => <option key={w} value={w}>{LABELS.weight[w] || w}</option>)}
        </select>
      </div>

      <div className="cg-field">
        <div className="cg-position-header">
          <label className="cg-label" htmlFor="cap-size">Size</label>
          <span className="cg-text-xs cg-text-secondary">{draft.size}</span>
        </div>
        <input id="cap-size" type="range" className="cg-range" min={sizeLo} max={sizeHi} step="2"
          value={draft.size} onChange={(e) => set('size', Number(e.target.value))} />
      </div>

      <div className="cg-caption-colors">
        <div className="cg-field">
          <label className="cg-label" htmlFor="cap-text-color">Text colour</label>
          <input id="cap-text-color" type="color" value={draft.text_color}
            onChange={(e) => set('text_color', e.target.value.toUpperCase())} />
        </div>
        <div className="cg-field">
          <label className="cg-label" htmlFor="cap-hi-color">Highlight colour</label>
          <input id="cap-hi-color" type="color" value={draft.highlight_color}
            onChange={(e) => set('highlight_color', e.target.value.toUpperCase())} />
        </div>
      </div>

      <div className="cg-field">
        <label className="cg-label" htmlFor="cap-anim">Animation</label>
        <select id="cap-anim" className="cg-select" value={draft.animation}
          onChange={(e) => set('animation', e.target.value)}>
          {options.animations.map((a) => <option key={a} value={a}>{LABELS.animation[a] || a}</option>)}
        </select>
      </div>

      <div className="cg-field">
        <label className="cg-label" htmlFor="cap-box">Box</label>
        <select id="cap-box" className="cg-select" value={draft.box}
          onChange={(e) => set('box', e.target.value)}>
          {options.boxes.map((b) => <option key={b} value={b}>{LABELS.box[b] || b}</option>)}
        </select>
      </div>

      <div className="cg-field">
        <div className="cg-position-header">
          <label className="cg-label" htmlFor="cap-pos">Position</label>
          <span className="cg-text-xs cg-text-secondary">{draft.position}% from top</span>
        </div>
        <input id="cap-pos" type="range" className="cg-range" min={posLo} max={posHi} step="1"
          value={draft.position} onChange={(e) => set('position', Number(e.target.value))} />
        <p className="cg-text-xs cg-text-muted">Kept clear of the Shorts buttons and description.</p>
      </div>

      <div className="cg-field">
        <div className="cg-position-header">
          <label className="cg-label" htmlFor="cap-wpl">Words shown together</label>
          <span className="cg-text-xs cg-text-secondary">{draft.words_per_line}</span>
        </div>
        <input id="cap-wpl" type="range" className="cg-range" min={wplLo} max={wplHi} step="1"
          value={draft.words_per_line} onChange={(e) => set('words_per_line', Number(e.target.value))} />
      </div>

      <div className="cg-field">
        <div className="cg-position-header">
          <label className="cg-label" htmlFor="cap-outline">Dark edge</label>
          <span className="cg-text-xs cg-text-secondary">{draft.outline}</span>
        </div>
        <input id="cap-outline" type="range" className="cg-range" min={outLo} max={outHi} step="1"
          value={draft.outline} onChange={(e) => set('outline', Number(e.target.value))} />
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

      {isHindi(caps) && (
        <div className="cg-field">
          <label className="cg-label" htmlFor="cap-script">Hindi words written in</label>
          <select id="cap-script" className="cg-select" value={draft.script}
            onChange={(e) => set('script', e.target.value)}>
            <option value="hinglish">Hinglish (Roman letters: "aaj ki baat")</option>
            <option value="original">Hindi (Devanagari: "आज की बात")</option>
          </select>
          {draft.script !== styleOf(caps.style).script && (
            <p className="cg-text-xs cg-text-muted">The words below change after you apply.</p>
          )}
        </div>
      )}

      <div className="cg-field">
        <label className="cg-label">Fix words</label>
        <p className="cg-text-xs cg-text-muted">
          Change the spelling of any word shown in the captions. Timing stays the same.
        </p>
        <div className="cg-caption-words">
          {texts.map((t, i) => (
            <input
              key={i}
              className={`cg-input cg-caption-word ${t !== savedWords[i] ? 'edited' : ''}`}
              style={{ width: `${Math.max(4, t.length + 2)}ch` }}
              value={t}
              maxLength={40}
              title={`${caps.words[i].start.toFixed(1)}s`}
              aria-label={`Caption word ${i + 1}`}
              onChange={(e) => setTexts((list) => list.map((x, j) => (j === i ? e.target.value : x)))}
            />
          ))}
        </div>
      </div>

      {error && <p className="cg-text-xs cg-caption-error" role="alert">{error}</p>}
      {busy && (
        <p className="cg-text-xs cg-text-muted" role="status">
          Redrawing captions on the video. This takes about half a minute…
        </p>
      )}

      <div className="cg-caption-actions">
        <button type="button" className="cg-btn cg-btn--primary cg-btn--sm"
          disabled={!dirty || busy || texts.some((t) => !t.trim())} onClick={apply}>
          {busy ? 'Applying…' : 'Apply to clip'}
        </button>
        <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm"
          disabled={!dirty || busy} onClick={revert}>
          Revert
        </button>
      </div>
      <p className="cg-text-xs cg-text-muted">
        Changing captions makes a new version of this clip, so its copyright checklist must be ticked again.
      </p>
      {onOtherText && (
        <div className="cg-caption-actions">
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={busy}
            onClick={onOtherText}>
            Use a headline or no text instead
          </button>
        </div>
      )}
    </div>
  );
}

// Captions are only shown for speech CocoGenie could trust. Otherwise the user chooses a headline
// of their own, or no text (see TextChoicePanel).
export default function CaptionsStylePanel(props) {
  const { clip } = props;
  const [chooseText, setChooseText] = useState(false);
  const text = clip.text;
  const untrusted = text && ['unreliable', 'unusable'].includes(text.verdict);
  const showChoices = untrusted || (text && text.mode !== 'captions') || chooseText;
  useEffect(() => { setChooseText(false); }, [clip.id]);
  if (showChoices) {
    return (
      <TextChoicePanel
        {...props}
        canUseCaptions={!untrusted && !!clip.captions}
        onBackToCaptions={text?.mode === 'captions' ? () => setChooseText(false) : undefined}
      />
    );
  }
  return <CaptionsEditor {...props} onOtherText={() => setChooseText(true)} />;
}
