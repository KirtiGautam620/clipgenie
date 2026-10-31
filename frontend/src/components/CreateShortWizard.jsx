import React, { useState, useRef } from 'react';
import './CreateShortWizard.css';

const RIGHTS_OPTIONS = [
  { value: 'own', icon: '✎', label: 'I made this / I own it', urlOk: true },
  { value: 'permission', icon: '🤝', label: "I have the owner's permission to edit & publish", urlOk: true },
  { value: 'licensed', icon: '📜', label: 'Public domain or licensed for reuse (e.g. CC BY)', urlOk: true },
  { value: 'unsure', icon: '❓', label: "I'm not sure (clips only — cannot import from URL)", urlOk: false },
];

const ASPECT_RATIOS = [
  { id: '9-16', label: 'Vertical (9:16)', sub: 'Shorts, Reels, TikTok', icon: '📱', default: true },
  { id: '1-1', label: 'Square (1:1)', sub: 'Instagram Feed', icon: '🔲' },
  { id: '16-9', label: 'Widescreen (16:9)', sub: 'YouTube / Web', icon: '🖥️' },
];

const STYLE_PRESETS = [
  { id: 'cinematic', title: 'Cinematic Warm', icon: '🎬', desc: 'Warm studio grading & kinetic bold captions', framing: 'crop' },
  { id: 'vibrant', title: 'Vibrant Tech', icon: '⚡', desc: 'Punchy saturation with neon subtitles', framing: 'crop' },
  { id: 'blur-bg', title: 'Blurred Horizon', icon: '🌫️', desc: 'Full-frame over blurred background fit', framing: 'blur' },
  { id: 'minimal', title: 'Minimalist Clean', icon: '✨', desc: 'Subtle lower-third subtitles', framing: 'crop' },
];

export default function CreateShortWizard({ busy, onSubmit, onCancel }) {
  const [source, setSource] = useState('file'); // 'file' | 'url'
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState('');
  const [rights, setRights] = useState('own');
  const [aspectRatio, setAspectRatio] = useState('9-16');
  const [selectedStyle, setSelectedStyle] = useState(STYLE_PRESETS[0]);
  const [language, setLanguage] = useState('auto');
  const [minLen, setMinLen] = useState(30);
  const [maxLen, setMaxLen] = useState(60);
  const [count, setCount] = useState(5);
  const [useAi, setUseAi] = useState(true);
  const [framing, setFraming] = useState('crop');
  const [musicOn, setMusicOn] = useState(true);
  const [musicVol, setMusicVol] = useState(0.6);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

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
      minLen,
      maxLen,
      count,
      useAi,
      framing: selectedStyle.framing || framing,
      musicOn,
      musicVol,
    });
  };

  const handleSelectStyle = (preset) => {
    setSelectedStyle(preset);
    if (preset.framing) setFraming(preset.framing);
  };

  return (
    <div className="cg-wizard-page">
      <div className="cg-wizard-container">
        {/* Wizard Header */}
        <div className="cg-wizard-header">
          <div>
            <h1 className="cg-heading-lg">Create New Short</h1>
            <p className="cg-text-secondary cg-text-sm" style={{ marginTop: 4 }}>
              Select your source video, target aspect ratio, and editing style. AI handles the rest.
            </p>
          </div>
          {onCancel && (
            <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={onCancel}>
              ✕ Cancel
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} className="cg-wizard-form">
          {/* ── STEP 1: Video Sourcing ─────────────────────────────────── */}
          <section className="cg-wizard-card">
            <h2 className="cg-wizard-step-title">
              <span className="cg-wizard-step-num">1</span>
              <span>Video Source</span>
            </h2>

            <div className="cg-tabs" style={{ maxWidth: 360, marginBottom: 16 }}>
              <button
                type="button"
                className={`cg-tab ${source === 'file' ? 'cg-tab--active' : ''}`}
                onClick={() => setSource('file')}
                disabled={busy}
              >
                📁 Upload Video File
              </button>
              <button
                type="button"
                className={`cg-tab ${source === 'url' ? 'cg-tab--active' : ''}`}
                onClick={() => setSource('url')}
                disabled={busy}
              >
                🔗 YouTube Link
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
                    <span className="cg-file-icon">🎬</span>
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
                    <span className="cg-dropzone-icon">⬆</span>
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

          {/* ── STEP 2: Target Aspect Ratio ───────────────────────────── */}
          <section className="cg-wizard-card">
            <h2 className="cg-wizard-step-title">
              <span className="cg-wizard-step-num">2</span>
              <span>Target Aspect Ratio</span>
            </h2>

            <div className="cg-aspect-grid">
              {ASPECT_RATIOS.map((ar) => (
                <div
                  key={ar.id}
                  className={`cg-aspect-card ${aspectRatio === ar.id ? 'active' : ''}`}
                  onClick={() => setAspectRatio(ar.id)}
                >
                  <span className="cg-aspect-icon">{ar.icon}</span>
                  <div className="cg-aspect-info">
                    <p className="cg-aspect-name">{ar.label}</p>
                    <span className="cg-text-xs cg-text-muted">{ar.sub}</span>
                  </div>
                  {ar.default && <span className="cg-badge cg-badge--accent cg-text-xs">Revid Style</span>}
                </div>
              ))}
            </div>
          </section>

          {/* ── STEP 3: Aesthetic Presets ─────────────────────────────── */}
          <section className="cg-wizard-card">
            <h2 className="cg-wizard-step-title">
              <span className="cg-wizard-step-num">3</span>
              <span>Visual Style & Mood</span>
            </h2>

            <div className="cg-styles-grid">
              {STYLE_PRESETS.map((preset) => (
                <div
                  key={preset.id}
                  className={`cg-style-card ${selectedStyle.id === preset.id ? 'active' : ''}`}
                  onClick={() => handleSelectStyle(preset)}
                >
                  <span className="cg-style-icon">{preset.icon}</span>
                  <p className="cg-style-title">{preset.title}</p>
                  <p className="cg-text-xs cg-text-muted">{preset.desc}</p>
                  {selectedStyle.id === preset.id && (
                    <span className="cg-style-check">✓</span>
                  )}
                </div>
              ))}
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
                  <span className="cg-rights-icon">{opt.icon}</span>
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
                <><span className="cg-spinner" /> Analyzing Video…</>
              ) : (
                <><span>✨ Generate AI Shorts</span><span>→</span></>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

