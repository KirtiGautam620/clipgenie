import React, { useEffect, useState, useRef } from 'react';
import Icon from './Icon.jsx';
import { getJSON } from '../api.js';
import { Panda } from './Botanicals.jsx';
import './CreateShortWizard.css';

const RIGHTS_OPTIONS = [
  { value: 'own', label: 'I made this / I own it', urlOk: true },
  { value: 'permission', label: "I have the owner's permission to edit & publish", urlOk: true },
  { value: 'licensed', label: 'Public domain or licensed for reuse (e.g. CC BY)', urlOk: true },
  { value: 'unsure', label: "I'm not sure (clips only — cannot import from URL)", urlOk: false },
];

const EDIT_MODES = [
  { id: 'auto', title: 'Auto Edit', text: 'CocoGenie makes every editing decision and finishes the videos.' },
  { id: 'assist', title: 'AI + Manual', text: 'CocoGenie edits first, then opens the editor so you can change any decision.' },
  { id: 'custom', title: 'Custom Style', text: 'You choose an editing style and CocoGenie applies it to every video.' },
];

// How the picture is framed. These are the two real choices the backend understands.
const FRAMING_OPTIONS = [
  { id: 'crop', title: 'Follow the speaker',
    desc: 'Crops to a vertical frame and follows the speaker\'s face. Best for talks and interviews.' },
  { id: 'blur', title: 'Whole picture',
    desc: 'Keeps the entire frame, centred over a soft blurred copy of itself.' },
];

export default function CreateShortWizard({ busy, onSubmit, onCancel, initialSource = 'file', initialUrl = '' }) {
  const [source, setSource] = useState(initialSource); // 'file' | 'url'
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState(initialUrl);
  const [rights, setRights] = useState('own');
  const [language, setLanguage] = useState('auto');
  const [captionScript, setCaptionScript] = useState('hinglish');
  const [minLen, setMinLen] = useState(30);
  const [maxLen, setMaxLen] = useState(60);
  const [count, setCount] = useState(5);
  const [useAi, setUseAi] = useState(true);
  const [framing, setFraming] = useState('crop');
  const [musicOn, setMusicOn] = useState(true);
  const [editMode, setEditMode] = useState('auto');        // auto | assist | custom
  const [styleId, setStyleId] = useState('punchy');
  const [styleList, setStyleList] = useState([]);
  const [removePauses, setRemovePauses] = useState(true);
  const [suggestHook, setSuggestHook] = useState(true);
  const [musicVol, setMusicVol] = useState(0.6);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  // the editing styles on offer (built in, plus any the user saved)
  useEffect(() => {
    getJSON('/api/styles').then((d) => setStyleList(d.styles.filter((s) => s.id !== d.default))).catch(() => {});
  }, []);

  const ready = rights && (source === 'file' ? file : url.trim());

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) {
      setFile(f);
      setSource('file');
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!ready || busy) return;
    onSubmit({
      source,
      file,
      url,
      rights,
      language,
      captionScript,
      minLen,
      maxLen,
      count,
      useAi,
      framing,
      musicOn,
      musicVol,
      removePauses,
      suggestHook,
      editMode,
      styleId: editMode === 'custom' ? styleId : 'natural',
    });
  };

  return (
    <div className="cg-wizard-page">
      <div className="cg-wizard-container">
        {/* Wizard Header */}
        <div className="cg-wizard-header">
          <div>
            <h1 className="cg-heading-lg">Create a new video</h1>
            <p className="cg-text-secondary cg-text-sm" style={{ marginTop: 4 }}>
              Choose where your video comes from and how it should be framed. CocoGenie does the rest.
            </p>
          </div>
          <Panda width={64} className="cg-page-panda" pose="waving" />
          {onCancel && (
            <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={onCancel}>
              Cancel
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} className="cg-wizard-form">
          {/* ── STEP 1: Video Sourcing ─────────────────────────────────── */}
          <section className="cg-wizard-card">
            <h2 className="cg-wizard-step-title">
              <span className="cg-wizard-step-num">1</span>
              <span>Where is your video?</span>
            </h2>

            <div className="cg-tabs" style={{ maxWidth: 440, marginBottom: 16 }}>
              <button
                type="button"
                className={`cg-tab ${source === 'file' ? 'cg-tab--active' : ''}`}
                onClick={() => setSource('file')}
                disabled={busy}
              >
                Upload a video
              </button>
              <button
                type="button"
                className={`cg-tab ${source === 'url' ? 'cg-tab--active' : ''}`}
                onClick={() => setSource('url')}
                disabled={busy}
              >
                YouTube link
              </button>
              <button type="button" className="cg-tab cg-tab--soon" disabled
                title="Photos to video is not available yet">
                Photos · soon
              </button>
            </div>

            {source === 'file' ? (
              <div
                className={`cg-wizard-dropzone ${dragging ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
                onClick={() => !busy && fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                tabIndex={0}
                role="button"
                aria-label="Upload MP4 or MOV video file"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/mp4,video/quicktime"
                  style={{ display: 'none' }}
                  disabled={busy}
                  onChange={(e) => setFile(e.target.files[0] || null)}
                />
                {file ? (
                  <div className="cg-wizard-file-info">
                    <span className="cg-file-icon"><Icon name="videos" size={24} /></span>
                    <div>
                      <p className="cg-file-name">{file.name}</p>
                      <p className="cg-text-xs cg-text-muted">
                        {(file.size / (1024 * 1024)).toFixed(1)} MB · Ready to analyze
                      </p>
                    </div>
                    <span className="cg-badge cg-badge--success" style={{ marginLeft: 'auto' }}>Selected ✓</span>
                  </div>
                ) : (
                  <div className="cg-dropzone-empty">
                    <span className="cg-dropzone-icon"><Icon name="upload" size={22} /></span>
                    <p className="cg-dropzone-label">Drop your MP4 or MOV video here</p>
                    <p className="cg-text-xs cg-text-muted">or click to browse from your Mac</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="cg-field">
                <input
                  type="url"
                  className="cg-input"
                  placeholder="https://www.youtube.com/watch?v=..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={busy}
                  autoFocus
                />
                <p className="cg-text-xs cg-text-muted">
                  Import long-form talks or podcasts you own or have permission to use.
                </p>
              </div>
            )}
          </section>

          {/* ── STEP 2: Picture framing ───────────────────────────────── */}
          <section className="cg-wizard-card">
            <h2 className="cg-wizard-step-title">
              <span className="cg-wizard-step-num">2</span>
              <span>How should the picture be framed?</span>
            </h2>

            <div className="cg-aspect-grid">
              {FRAMING_OPTIONS.map((opt) => (
                <div
                  key={opt.id}
                  role="radio"
                  aria-checked={framing === opt.id}
                  tabIndex={0}
                  className={`cg-aspect-card ${framing === opt.id ? 'active' : ''}`}
                  onClick={() => setFraming(opt.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setFraming(opt.id); } }}
                >
                  <div className="cg-aspect-info">
                    <p className="cg-aspect-name">{opt.title}</p>
                    <span className="cg-text-xs cg-text-muted">{opt.desc}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="cg-text-xs cg-text-muted">Output is vertical 9:16, made for Shorts, Reels and TikTok.</p>
          </section>

          {/* ── Auto Edit: what CocoGenie does for you ──────────────────── */}
          <section className="cg-wizard-card">
            <h2 className="cg-wizard-step-title">
              <span className="cg-wizard-step-num">3</span>
              <span>How should CocoGenie edit?</span>
            </h2>
            <div className="cg-mode-grid" role="radiogroup" aria-label="Editing mode">
              {EDIT_MODES.map((m) => (
                <div key={m.id} role="radio" aria-checked={editMode === m.id} tabIndex={0}
                  className={`cg-aspect-card ${editMode === m.id ? 'active' : ''}`}
                  onClick={() => setEditMode(m.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setEditMode(m.id); } }}>
                  <div className="cg-aspect-info">
                    <p className="cg-aspect-name">{m.title}</p>
                    <span className="cg-text-xs cg-text-muted">{m.text}</span>
                  </div>
                </div>
              ))}
            </div>
            {editMode === 'custom' && (
              <div className="cg-style-grid" role="radiogroup" aria-label="Editing style">
                {styleList.length === 0 && <p className="cg-text-xs cg-text-muted">Loading styles…</p>}
                {styleList.map((st) => (
                  <div key={st.id} role="radio" aria-checked={styleId === st.id} tabIndex={0}
                    className={`cg-aspect-card ${styleId === st.id ? 'active' : ''}`}
                    onClick={() => setStyleId(st.id)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setStyleId(st.id); } }}>
                    <div className="cg-aspect-info">
                      <p className="cg-aspect-name">{st.name}{st.builtin ? '' : ' (yours)'}</p>
                      <span className="cg-text-xs cg-text-muted">{st.description}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="cg-autoedit-list">
              <label className="cg-toggle">
                <input type="checkbox" checked={removePauses} onChange={(e) => setRemovePauses(e.target.checked)} />
                <span className="cg-toggle-track" />
                <span className="cg-toggle-label">
                  <strong>Tighten long pauses</strong>: shorten silences over a second to a short beat
                </span>
              </label>
              <label className="cg-toggle">
                <input type="checkbox" checked={suggestHook} onChange={(e) => setSuggestHook(e.target.checked)} />
                <span className="cg-toggle-track" />
                <span className="cg-toggle-label">
                  <strong>Suggest a hook line</strong>: a title for the first seconds. You approve it before it is used
                </span>
              </label>
            </div>
          </section>

          {/* ── STEP 4: Rights Declaration ────────────────────────────── */}
          <section className="cg-wizard-card">
            <h2 className="cg-wizard-step-title">
              <span className="cg-wizard-step-num">4</span>
              <span>Who owns this video? <span className="cg-required">*</span></span>
            </h2>

            <div className="cg-rights-grid">
              {RIGHTS_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`cg-rights-card ${rights === opt.value ? 'cg-rights-card--selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="rights"
                    value={opt.value}
                    checked={rights === opt.value}
                    onChange={() => setRights(opt.value)}
                    className="cg-rights-radio"
                  />
                  <span className="cg-rights-text">{opt.label}</span>
                </label>
              ))}
            </div>
          </section>

          {/* ── Advanced Options Accordion ────────────────────────────── */}
          <div className="cg-wizard-card">
            <button
              type="button"
              className="cg-btn cg-btn--ghost cg-btn--sm"
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{ alignSelf: 'flex-start' }}
            >
              {showAdvanced ? '▾ Hide Advanced Pipeline Settings' : '▸ Advanced Pipeline Settings (Duration, Count, Framing)'}
            </button>

            {showAdvanced && (
              <div className="cg-wizard-advanced-body">
                <div className="cg-advanced-row">
                  <div className="cg-field" style={{ flex: 1 }}>
                    <label className="cg-label">Clip Duration Range: {minLen}s – {maxLen}s</label>
                    <div className="cg-range-row">
                      <input
                        type="range"
                        min="10"
                        max="120"
                        step="5"
                        value={minLen}
                        onChange={(e) => {
                          const v = parseInt(e.target.value, 10);
                          setMinLen(v);
                          if (v > maxLen) setMaxLen(v);
                        }}
                        className="cg-range"
                      />
                      <input
                        type="range"
                        min="10"
                        max="180"
                        step="5"
                        value={maxLen}
                        onChange={(e) => {
                          const v = parseInt(e.target.value, 10);
                          setMaxLen(v);
                          if (v < minLen) setMinLen(v);
                        }}
                        className="cg-range"
                      />
                    </div>
                  </div>

                  <div className="cg-field" style={{ width: 140 }}>
                    <label className="cg-label">Clip Count</label>
                    <div className="cg-number-input">
                      <button type="button" onClick={() => setCount(Math.max(1, count - 1))}>−</button>
                      <span>{count}</span>
                      <button type="button" onClick={() => setCount(Math.min(10, count + 1))}>+</button>
                    </div>
                  </div>
                </div>

                <div className="cg-field" style={{ marginTop: 12 }}>
                  <label className="cg-label" htmlFor="caption-script">Hindi captions written in</label>
                  <select
                    id="caption-script"
                    className="cg-select"
                    value={captionScript}
                    onChange={(e) => setCaptionScript(e.target.value)}
                    style={{ maxWidth: 320 }}
                  >
                    <option value="hinglish">Hinglish (Roman letters: "aaj ki baat")</option>
                    <option value="original">Hindi (Devanagari: "आज की बात")</option>
                  </select>
                </div>

                <div className="cg-advanced-row" style={{ marginTop: 12 }}>
                  <label className="cg-toggle">
                    <input
                      type="checkbox"
                      checked={useAi}
                      onChange={(e) => setUseAi(e.target.checked)}
                    />
                    <span className="cg-toggle-track" />
                    <span className="cg-toggle-label">Use Local Ollama AI Highlight Selector</span>
                  </label>

                  <label className="cg-toggle">
                    <input
                      type="checkbox"
                      checked={musicOn}
                      onChange={(e) => setMusicOn(e.target.checked)}
                    />
                    <span className="cg-toggle-track" />
                    <span className="cg-toggle-label">Add Background Music Bed</span>
                  </label>
                </div>
              </div>
            )}
          </div>

          {/* ── Submit Action ─────────────────────────────────────────── */}
          <div className="cg-wizard-actions">
            <button
              type="submit"
              className="cg-btn cg-btn--primary cg-btn--lg"
              disabled={!ready || busy}
            >
              {busy ? (
                <><span className="cg-spinner" /> Analyzing video…</>
              ) : (
                <><span>Create Shorts</span><span>→</span></>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

