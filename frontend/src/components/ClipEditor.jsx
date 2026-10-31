import { useState } from 'react';
import { getJSON } from '../api.js';
import ExportModal from './ExportModal.jsx';
import './ClipEditor.css';

function moodClass(mood) {
  const m = (mood || 'other').toLowerCase();
  const valid = ['motivational','emotional','funny','educational','spiritual','other'];
  return valid.includes(m) ? m : 'other';
}

export default function ClipEditor({ jobId, clip: initialClip, tracks, onBack, onClipUpdated }) {
  const [clip, setClip]       = useState(initialClip);
  const [trackId, setTrackId] = useState(initialClip.music?.track_id || '');
  const [volume, setVolume]   = useState(initialClip.music?.volume ?? 0.6);
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState('');
  const [copied, setCopied]   = useState(false);
  const [showExport, setShowExport] = useState(false);

  const base = `/api/jobs/${jobId}/clips/${clip.id}`;
  const mc = moodClass(clip.mood);

  const musicChanged =
    (clip.music?.track_id || '') !== trackId ||
    (trackId && Math.abs((clip.music?.volume ?? 0) - volume) > 0.001);

  async function applyMusic() {
    setBusy(true);
    setError('');
    try {
      const updated = await getJSON(`${base}/music`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: trackId || null, volume }),
      });
      setClip(updated);
      onClipUpdated(updated);
      setTrackId(updated.music?.track_id || '');
      setVolume(updated.music?.volume ?? 0.6);
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  async function copyCredits() {
    try {
      await navigator.clipboard.writeText(clip.credits);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch { /* fallback: text is selectable */ }
  }

  function handleExportDone(updatedClip) {
    setClip(updatedClip);
    onClipUpdated(updatedClip);
    setShowExport(false);
  }

  const selectedTrack = tracks.find((t) => t.id === trackId);

  return (
    <main className="cg-main cg-editor-page">
      {/* Top bar */}
      <div className="cg-editor-topbar">
        <button className="cg-back-btn" onClick={onBack}>← Back to Gallery</button>
        {clip.confirmed && (
          <span className="cg-badge cg-badge--success">✓ Confirmed & downloaded</span>
        )}
      </div>

      <div className="cg-editor-layout">
        {/* Left — video player */}
        <div className="cg-editor-player-col">
          <div className="cg-editor-video-wrap">
            <video
              className="cg-editor-video"
              src={`${base}.mp4?v=${clip.version || 0}`}
              controls
              preload="metadata"
              aria-label={`Preview: ${clip.title || `Clip ${clip.id}`}`}
            />
          </div>
        </div>

        {/* Right — controls */}
        <div className="cg-editor-controls">
          {/* Clip info */}
          <div className="cg-card cg-editor-section">
            <h1 className="cg-heading-sm cg-editor-clip-title">
              {clip.title || `Clip ${clip.id}`}
            </h1>
            <div className="cg-editor-chips">
              <span className="cg-badge cg-badge--muted">{clip.duration}s</span>
              {clip.mood && clip.mood !== 'other' && (
                <span className={`cg-badge cg-badge--${mc}`}>{clip.mood}</span>
              )}
              {clip.score && (
                <span className="cg-badge cg-badge--score">★ {clip.score}/10</span>
              )}
            </div>
            {clip.reason && (
              <p className="cg-editor-reason cg-text-sm cg-text-secondary">
                "{clip.reason}"
              </p>
            )}
          </div>

          {/* Music */}
          <div className="cg-card cg-editor-section">
            <h2 className="cg-heading-sm">🎵 Background Music</h2>

            {/* No music option */}
            <label className={`cg-music-track-card ${trackId === '' ? 'cg-music-track-card--selected' : ''}`}>
              <input type="radio" name="track" value="" checked={trackId === ''}
                onChange={() => setTrackId('')} disabled={busy} className="cg-music-track-radio" />
              <span className="cg-music-track-icon">🚫</span>
              <span className="cg-music-track-name">No music</span>
            </label>

            {/* Track cards */}
            {tracks.length === 0 && (
              <p className="cg-text-sm cg-text-muted">No music tracks in library. Add some in the music library panel.</p>
            )}
            <div className="cg-music-tracks-grid">
              {tracks.map((t) => (
                <label
                  key={t.id}
                  className={`cg-music-track-card ${trackId === t.id ? 'cg-music-track-card--selected' : ''}`}
                  title={t.warning || t.license_label}
                >
                  <input type="radio" name="track" value={t.id} checked={trackId === t.id}
                    onChange={() => setTrackId(t.id)} disabled={busy} className="cg-music-track-radio" />
                  <div className="cg-music-track-info">
                    <span className="cg-music-track-icon">🎵</span>
                    <div>
                      <p className="cg-music-track-name">{t.title}</p>
                      <div className="cg-music-track-chips">
                        {t.moods.map((m) => (
                          <span key={m} className={`cg-badge cg-badge--${moodClass(m)}`}>{m}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                  {t.warning && <span className="cg-music-warn-dot" aria-label="Licence warning">⚠</span>}
                </label>
              ))}
            </div>

            {/* Preview selected track */}
            {trackId && selectedTrack && (
              <div className="cg-music-preview">
                <p className="cg-text-xs cg-text-muted">Preview: {selectedTrack.title}</p>
                <audio controls preload="none" src={`/api/music/${trackId}/preview`}
                  style={{ width: '100%', height: 36 }} aria-label={`Preview ${selectedTrack.title}`} />
                <p className="cg-text-xs cg-text-muted">Licence: {selectedTrack.license_label}</p>
              </div>
            )}

            {/* Volume */}
            {trackId && (
              <div className="cg-field">
                <label className="cg-label" htmlFor="vol-slider">
                  Volume — {Math.round(volume * 100)}%
                </label>
                <input id="vol-slider" className="cg-range" type="range" min="0" max="1" step="0.05"
                  value={volume} disabled={busy}
                  onChange={(e) => setVolume(+e.target.value)}
                />
              </div>
            )}

            {/* Apply */}
            {musicChanged && (
              <button className="cg-btn cg-btn--secondary cg-btn--sm" onClick={applyMusic} disabled={busy}>
                {busy ? <><span className="cg-spinner" aria-hidden="true" /> Mixing…</> : '✓ Apply music'}
              </button>
            )}

            {error && (
              <div className="cg-alert cg-alert--error" role="alert">
                <span className="cg-alert-icon">⚠️</span>
                <span>{error}</span>
              </div>
            )}
          </div>

          {/* Warnings */}
          {clip.warnings?.length > 0 && (
            <div className="cg-editor-section">
              {clip.warnings.map((w) => (
                <div key={w} className="cg-alert cg-alert--warn">
                  <span className="cg-alert-icon">⚠️</span>
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          {/* Credits (post-confirmation) */}
          {clip.confirmed && clip.credits && (
            <div className="cg-card cg-editor-section">
              <h2 className="cg-heading-sm">📋 Credits</h2>
              <p className="cg-text-sm cg-text-secondary">Paste this into your video description where required.</p>
              <textarea
                className="cg-input cg-editor-credits"
                readOnly
                rows={3}
                value={clip.credits}
                aria-label="Credits text"
              />
              <button className="cg-btn cg-btn--secondary cg-btn--sm" onClick={copyCredits}>
                {copied ? '✓ Copied!' : '📋 Copy credits'}
              </button>
            </div>
          )}

          {/* Export / Download actions */}
          <div className="cg-editor-actions">
            {clip.confirmed ? (
              <>
                <a
                  className="cg-btn cg-btn--primary"
                  href={`${base}/download`}
                >
                  ↓ Download MP4
                </a>
                <a
                  className="cg-btn cg-btn--secondary cg-btn--sm"
                  href={`${base}/report`}
                  download
                >
                  🗒 Rights report
                </a>
              </>
            ) : (
              <button
                className="cg-btn cg-btn--primary"
                onClick={() => setShowExport(true)}
                disabled={busy}
              >
                ↓ Download…
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Export / Checklist modal */}
      {showExport && (
        <ExportModal
          jobId={jobId}
          clip={clip}
          onClose={() => setShowExport(false)}
          onConfirmed={handleExportDone}
        />
      )}
    </main>
  );
}

