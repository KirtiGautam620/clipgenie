import { useState, useRef } from 'react';
import './ImportScreen.css';

const RIGHTS = [
  { value: 'own',        icon: '✎', label: 'I made this / I own it',                        urlOk: true },
  { value: 'permission', icon: '🤝', label: "I have the owner's permission to edit & publish", urlOk: true },
  { value: 'licensed',   icon: '📜', label: 'Public domain or licensed for reuse (e.g. CC BY)', urlOk: true },
  { value: 'unsure',     icon: '❓', label: "I'm not sure (clips only — cannot use YouTube link)", urlOk: false },
];

const LANGUAGES = [
  { value: 'auto', label: 'Detect automatically' },
  { value: 'en',   label: 'English' },
  { value: 'hi',   label: 'Hindi / Hinglish' },
];

export default function ImportScreen({ busy, onSubmit, onBack }) {
  const [source, setSource]     = useState('file');
  const [file, setFile]         = useState(null);
  const [url, setUrl]           = useState('');
  const [rights, setRights]     = useState('');
  const [language, setLanguage] = useState('auto');
  const [showAdv, setShowAdv]   = useState(false);
  const [minLen, setMinLen]     = useState(30);
  const [maxLen, setMaxLen]     = useState(60);
  const [count, setCount]       = useState(5);
  const [useAi, setUseAi]       = useState(true);
  const [framing, setFraming]   = useState('crop');
  const [musicOn, setMusicOn]   = useState(true);
  const [musicVol, setMusicVol] = useState(0.6);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef(null);

  const rightsOptions = source === 'url'
    ? RIGHTS.filter((r) => r.urlOk)
    : RIGHTS;

  const ready = rights && (source === 'file' ? file : url.trim());

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type === 'video/mp4') {
      setFile(f);
      setSource('file');
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!ready || busy) return;
    onSubmit({
      source, file, url, rights, language,
      minLen, maxLen, count, useAi, framing, musicOn, musicVol,
    });
  }

  function switchSource(s) {
    setSource(s);
    setRights('');
    if (s === 'url') setFile(null);
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  return (
    <main className="cg-main cg-import">
      {/* Back */}
      <button className="cg-back-btn" onClick={onBack} disabled={busy}>
        ← Back
      </button>

      <div className="cg-import-layout">
        {/* Left column — form */}
        <form className="cg-import-form" onSubmit={handleSubmit}>
          <h1 className="cg-heading-md cg-import-title">Import Video</h1>

          {/* Source tab toggle */}
          <div className="cg-tabs">
            <button type="button" className={`cg-tab ${source === 'file' ? 'cg-tab--active' : ''}`}
              onClick={() => switchSource('file')} disabled={busy}>
              📁 Upload MP4
            </button>
            <button type="button" className={`cg-tab ${source === 'url' ? 'cg-tab--active' : ''}`}
              onClick={() => switchSource('url')} disabled={busy}>
              🔗 YouTube Link
            </button>
          </div>

          {/* File drop zone */}
          {source === 'file' && (
            <div
              className={`cg-dropzone ${dragging ? 'cg-dropzone--drag' : ''} ${file ? 'cg-dropzone--filled' : ''}`}
              onClick={() => !busy && fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              role="button"
              tabIndex={busy ? -1 : 0}
              aria-label="Drop MP4 file here or click to browse"
              onKeyDown={(e) => e.key === 'Enter' && !busy && fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept="video/mp4"
                className="cg-dropzone-input"
                disabled={busy}
                onChange={(e) => setFile(e.target.files[0] || null)}
                aria-label="Choose MP4 file"
              />
              {file ? (
                <div className="cg-dropzone-filled">
                  <span className="cg-dropzone-filled-icon">🎬</span>
                  <div>
                    <p className="cg-dropzone-filename">{file.name}</p>
                    <p className="cg-text-sm cg-text-muted">
                      {(file.size / 1024 / 1024).toFixed(1)} MB — click to change
                    </p>
                  </div>
                </div>
              ) : (
                <div className="cg-dropzone-empty">
                  <span className="cg-dropzone-icon">⬆</span>
                  <p className="cg-dropzone-label">Drop your MP4 here</p>
                  <p className="cg-text-sm cg-text-muted">or click to browse</p>
                </div>
              )}
            </div>
          )}

          {/* URL input */}
          {source === 'url' && (
            <div className="cg-field">
              <label className="cg-label" htmlFor="url-input">YouTube URL</label>
              <input
                id="url-input"
                className="cg-input"
                type="url"
                placeholder="https://www.youtube.com/watch?v=…"
                value={url}
                disabled={busy}
                onChange={(e) => setUrl(e.target.value)}
                autoFocus
              />
              <p className="cg-text-sm cg-text-muted">
                Only for videos you own or have permission to use. If download fails, upload the MP4 directly.
              </p>
            </div>
          )}

          {/* Rights cards */}
          <fieldset className="cg-rights-fieldset" disabled={busy}>
            <legend className="cg-label">Who owns this video? <span className="cg-required">*</span></legend>
            <div className="cg-rights-grid">
              {rightsOptions.map((r) => (
                <label
                  key={r.value}
                  className={`cg-rights-card ${rights === r.value ? 'cg-rights-card--selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="rights"
                    value={r.value}
                    checked={rights === r.value}
                    onChange={() => setRights(r.value)}
                    className="cg-rights-radio"
                  />
                  <span className="cg-rights-icon">{r.icon}</span>
                  <span className="cg-rights-text">{r.label}</span>
                </label>
              ))}
            </div>
            {rights === 'unsure' && (
              <div className="cg-alert cg-alert--warn" role="alert">
                <span className="cg-alert-icon">⚠️</span>
                <span>You can still make clips to preview, but don't publish them until you've confirmed your rights.</span>
              </div>
            )}
          </fieldset>

          {/* Language */}
          <div className="cg-field">
            <label className="cg-label" htmlFor="lang-select">Spoken language</label>
            <select
              id="lang-select"
              className="cg-select"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              disabled={busy}
              style={{ maxWidth: 240 }}
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
          </div>

          {/* Advanced toggle */}
          <button
            type="button"
            className="cg-btn cg-btn--ghost cg-adv-toggle"
            onClick={() => setShowAdv(!showAdv)}
          >
            {showAdv ? '▾ Hide advanced options' : '▸ Advanced options'}
          </button>

          {showAdv && (
            <div className="cg-advanced">
              <div className="cg-advanced-row">
                <div className="cg-field cg-field--inline">
                  <label className="cg-label">Clip length (seconds)</label>
                  <div className="cg-range-row">
                    <span className="cg-text-sm cg-text-secondary">Min</span>
                    <input className="cg-range" type="range" min="5" max="120" step="5"
                      value={minLen} disabled={busy}
                      onChange={(e) => { const v = +e.target.value; setMinLen(v); if (v > maxLen) setMaxLen(v); }}
                    />
                    <span className="cg-adv-value">{minLen}s</span>
                    <span className="cg-text-sm cg-text-secondary">Max</span>
                    <input className="cg-range" type="range" min="5" max="180" step="5"
                      value={maxLen} disabled={busy}
                      onChange={(e) => { const v = +e.target.value; setMaxLen(v); if (v < minLen) setMinLen(v); }}
                    />
                    <span className="cg-adv-value">{maxLen}s</span>
                  </div>
                </div>

                <div className="cg-field cg-field--inline">
                  <label className="cg-label">Number of clips</label>
                  <div className="cg-number-input">
                    <button type="button" onClick={() => setCount(clamp(count - 1, 1, 10))} disabled={busy || count <= 1}>−</button>
                    <span>{count}</span>
                    <button type="button" onClick={() => setCount(clamp(count + 1, 1, 10))} disabled={busy || count >= 10}>+</button>
                  </div>
                </div>
              </div>

              <div className="cg-field">
                <label className="cg-label" htmlFor="framing-select">Vertical framing</label>
                <select id="framing-select" className="cg-select" value={framing}
                  onChange={(e) => setFraming(e.target.value)} disabled={busy} style={{ maxWidth: 320 }}>
                  <option value="crop">Fill the screen — crops sides (fast)</option>
                  <option value="blur">Full picture over blurred background (slower)</option>
                </select>
              </div>

              <div className="cg-adv-toggles">
                <label className="cg-toggle">
                  <input type="checkbox" checked={useAi} disabled={busy}
                    onChange={(e) => setUseAi(e.target.checked)} />
                  <span className="cg-toggle-track" />
                  <span className="cg-toggle-label">Use AI to select the best moments</span>
                </label>

                <label className="cg-toggle">
                  <input type="checkbox" checked={musicOn} disabled={busy}
                    onChange={(e) => setMusicOn(e.target.checked)} />
                  <span className="cg-toggle-track" />
                  <span className="cg-toggle-label">Add background music matched to each clip's mood</span>
                </label>

                {musicOn && (
                  <div className="cg-field cg-adv-vol">
                    <label className="cg-label">Music volume — {Math.round(musicVol * 100)}%</label>
                    <input className="cg-range" type="range" min="0" max="1" step="0.05"
                      value={musicVol} disabled={busy}
                      onChange={(e) => setMusicVol(+e.target.value)}
                      style={{ maxWidth: 240 }}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          <button
            type="submit"
            className="cg-btn cg-btn--primary cg-import-submit"
            disabled={!ready || busy}
          >
            {busy ? (
              <><span className="cg-spinner" aria-hidden="true" /> Processing…</>
            ) : (
              <><span>Create my clips</span><span>✨</span></>
            )}
          </button>
        </form>

        {/* Right — illustration / hint panel */}
        <aside className="cg-import-aside" aria-hidden="true">
          <div className="cg-import-preview">
            <div className="cg-import-phone">
              <div className="cg-import-phone-screen">
                <div className="cg-import-phone-caption">WORD BY</div>
                <div className="cg-import-phone-caption cg-import-phone-caption--highlight">WORD</div>
                <div className="cg-import-phone-caption">CAPTIONS</div>
              </div>
            </div>
          </div>
          <div className="cg-import-steps">
            {[
              ['🎙', 'AI listens to your video'],
              ['✨', 'Picks the best moments'],
              ['📱', 'Exports vertical Shorts'],
              ['🎵', 'Adds mood-matched music'],
            ].map(([icon, text]) => (
              <div key={text} className="cg-import-step">
                <span className="cg-import-step-icon">{icon}</span>
                <span className="cg-text-sm cg-text-secondary">{text}</span>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </main>
  );
}

