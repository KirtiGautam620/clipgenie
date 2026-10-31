import { useState } from 'react';
import { getJSON } from '../api.js';
import './MusicLibraryPanel.css';

export default function MusicLibraryPanel({ library, onChanged }) {
  const [file, setFile]           = useState(null);
  const [title, setTitle]         = useState('');
  const [mood, setMood]           = useState('other');
  const [license, setLicense]     = useState('cc0');
  const [attribution, setAttrib]  = useState('');
  const [source, setSource]       = useState('');
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');
  const [showAdd, setShowAdd]     = useState(false);

  async function add(e) {
    e.preventDefault();
    if (!file) return;
    setError('');
    setSaving(true);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('title', title);
      form.append('moods', mood);
      form.append('license', license);
      form.append('attribution', attribution);
      form.append('source', source);
      await getJSON('/api/music', { method: 'POST', body: form });
      setFile(null);
      setTitle('');
      setAttrib('');
      setSource('');
      setShowAdd(false);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  return (
    <div className="cg-music-panel">
      <p className="cg-text-xs cg-text-muted">
        Only music in this library is used. Add tracks you made, bought, or that are free to use.
      </p>

      {/* Track list */}
      {library.tracks?.length === 0 && (
        <p className="cg-text-sm cg-text-muted">No tracks yet. Add some below.</p>
      )}
      <div className="cg-music-panel-tracks">
        {library.tracks?.map((t) => (
          <div key={t.id} className="cg-music-panel-track">
            <div className="cg-music-panel-track-info">
              <span className="cg-text-sm" style={{ fontWeight: 600 }}>{t.title}</span>
              <div className="cg-music-panel-track-meta">
                <span className="cg-badge cg-badge--muted">{t.moods[0]}</span>
                <span className="cg-text-xs cg-text-muted">{t.license_label}</span>
              </div>
              {t.attribution && <p className="cg-text-xs cg-text-muted">Credit: {t.attribution}</p>}
              {t.warning && (
                <div className="cg-alert cg-alert--warn" style={{ fontSize: 'var(--cg-text-xs)', padding: '4px 8px' }}>
                  <span>⚠️</span><span>{t.warning}</span>
                </div>
              )}
            </div>
            <audio controls preload="none" src={`/api/music/${t.id}/preview`}
              style={{ width: '100%', height: 32 }} aria-label={`Preview ${t.title}`} />
          </div>
        ))}
      </div>

      {/* Add track */}
      <button
        className="cg-btn cg-btn--ghost cg-btn--sm"
        onClick={() => setShowAdd(!showAdd)}
        style={{ alignSelf: 'flex-start' }}
      >
        {showAdd ? '▾ Hide' : '▸ Add your own music'}
      </button>

      {showAdd && (
        <form onSubmit={add} className="cg-music-add-form">
          <div className="cg-field">
            <label className="cg-label" htmlFor="add-file">Audio file (MP3, WAV, M4A, FLAC, OGG)</label>
            <input id="add-file" type="file" accept="audio/*" className="cg-input"
              style={{ padding: '8px' }}
              onChange={(e) => setFile(e.target.files[0] || null)} />
          </div>
          <div className="cg-field">
            <label className="cg-label" htmlFor="add-title">Title</label>
            <input id="add-title" className="cg-input" placeholder="Track title"
              value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="cg-music-add-row">
            <div className="cg-field" style={{ flex: 1 }}>
              <label className="cg-label" htmlFor="add-mood">Mood</label>
              <select id="add-mood" className="cg-select" value={mood}
                onChange={(e) => setMood(e.target.value)}>
                {library.moods?.map((m) => <option key={m}>{m}</option>)}
              </select>
            </div>
            <div className="cg-field" style={{ flex: 1 }}>
              <label className="cg-label" htmlFor="add-lic">Licence</label>
              <select id="add-lic" className="cg-select" value={license}
                onChange={(e) => setLicense(e.target.value)}>
                {Object.entries(library.licenses || {}).map(([k, v]) =>
                  <option key={k} value={k}>{v}</option>
                )}
              </select>
            </div>
          </div>
          {license === 'cc-by' && (
            <div className="cg-field">
              <label className="cg-label" htmlFor="add-attr">Credit text (required for CC BY)</label>
              <input id="add-attr" className="cg-input" placeholder="Artist name / URL"
                value={attribution} onChange={(e) => setAttrib(e.target.value)} />
            </div>
          )}
          <div className="cg-field">
            <label className="cg-label" htmlFor="add-src">Where it came from</label>
            <input id="add-src" className="cg-input" placeholder="Website or download link"
              value={source} onChange={(e) => setSource(e.target.value)} />
          </div>
          {license === 'unknown' && (
            <div className="cg-alert cg-alert--warn">
              <span className="cg-alert-icon">⚠️</span>
              <span>Unknown licence — clips using this track will carry a warning.</span>
            </div>
          )}
          {error && (
            <div className="cg-alert cg-alert--error" role="alert">
              <span className="cg-alert-icon">⚠️</span>
              <span>{error}</span>
            </div>
          )}
          <button className="cg-btn cg-btn--secondary cg-btn--sm" type="submit"
            disabled={!file || saving}>
            {saving ? <><span className="cg-spinner" aria-hidden="true" /> Adding…</> : '+ Add track'}
          </button>
        </form>
      )}
    </div>
  );
}

