import React, { useState, useRef, useEffect } from 'react';
import Timeline from './Timeline.jsx';
import CaptionsStylePanel from './CaptionsStylePanel.jsx';
import ExportStudioModal from './ExportStudioModal.jsx';
import { getJSON } from '../api.js';
import { buildTracks, FRAMING_LABELS } from '../studioTracks.js';
import './StudioEditor.css';

// Everything in this screen does what it says: what is shown comes from the clip's own data, and
// every control changes the real video (captions, headline, music, zoom and pan). AI visuals and an
// AI assistant are not here because they are not built yet.

function describeVoice(audio) {
  if (!audio?.applied) return 'As recorded';
  if (typeof audio.loudness === 'string' && audio.loudness.startsWith('skipped')) {
    return 'As recorded (too quiet to level)';
  }
  return `Levelled to ${audio.target_lufs} LUFS${audio.denoised ? ', background noise reduced' : ''}`;
}

function describeZoom(effects) {
  const zoom = effects?.zoom ?? 1;
  const pan = effects?.pan || 'none';
  if (zoom <= 1 && pan === 'none') return 'None';
  const parts = [];
  if (zoom > 1) parts.push(`slow zoom to ${zoom.toFixed(2)}×`);
  if (pan !== 'none') parts.push(pan === 'left' ? 'slides left to right' : 'slides right to left');
  return parts.join(', ');
}

function describeText(text) {
  if (text?.mode === 'headline') return 'Your headline';
  if (text?.mode === 'none') return 'No text';
  if (text?.mode === 'pending') return 'Waiting for your choice';
  return 'Word-by-word captions';
}

function MusicPanel({ jobId, clip, tracks, onApplied }) {
  const [trackId, setTrackId] = useState(clip.music?.track_id || '');
  const [volume, setVolume] = useState(clip.music?.volume ?? 0.6);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setTrackId(clip.music?.track_id || '');
    setVolume(clip.music?.volume ?? 0.6);
    setError('');
  }, [clip.id, clip.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const changed = (clip.music?.track_id || '') !== trackId
    || (trackId && Math.abs((clip.music?.volume ?? 0) - volume) > 0.001);

  async function apply() {
    setBusy(true);
    setError('');
    try {
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/music`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: trackId || null, volume }),
      });
      onApplied(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cg-panel-content">
      <h3 className="cg-heading-sm">Music</h3>
      <p className="cg-text-xs cg-text-muted">
        The music is lowered automatically while someone is speaking. Your voice is levelled separately.
      </p>
      <div className="cg-field">
        <label className="cg-label" htmlFor="studio-music-track">Track</label>
        <select id="studio-music-track" className="cg-select" value={trackId} disabled={busy}
          onChange={(e) => setTrackId(e.target.value)}>
          <option value="">No music</option>
          {tracks.map((t) => (
            <option key={t.id} value={t.id}>{t.title}{t.moods?.[0] ? ` (${t.moods[0]})` : ''}</option>
          ))}
        </select>
      </div>
      {trackId && (
        <div className="cg-field">
          <div className="cg-position-header">
            <label className="cg-label" htmlFor="studio-music-volume">Volume</label>
            <span className="cg-text-xs cg-text-secondary">{Math.round(volume * 100)}%</span>
          </div>
          <input id="studio-music-volume" type="range" className="cg-range" min="0" max="1" step="0.05"
            value={volume} disabled={busy} onChange={(e) => setVolume(Number(e.target.value))} />
        </div>
      )}
      {clip.music?.license && trackId === clip.music.track_id && (
        <p className="cg-text-xs cg-text-muted">Licence: {clip.music.license}</p>
      )}
      {error && <p className="cg-text-xs cg-caption-error" role="alert">{error}</p>}
      {busy && <p className="cg-text-xs cg-text-muted" role="status">Mixing the music. This takes a few seconds…</p>}
      <div className="cg-caption-actions">
        <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={!changed || busy} onClick={apply}>
          {busy ? 'Applying…' : 'Apply to clip'}
        </button>
      </div>
      <p className="cg-text-xs cg-text-muted">
        Changing the music makes a new version of this clip, so its copyright checklist must be ticked again.
      </p>
    </div>
  );
}

const PAN_LABELS = {
  none: 'No pan',
  left: 'Slide left to right',
  right: 'Slide right to left',
};

function EffectsPanel({ jobId, clip, onApplied }) {
  const [zoom, setZoom] = useState(clip.effects?.zoom ?? 1);
  const [pan, setPan] = useState(clip.effects?.pan || 'none');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setZoom(clip.effects?.zoom ?? 1);
    setPan(clip.effects?.pan || 'none');
    setError('');
  }, [clip.id, clip.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const changed = Math.abs((clip.effects?.zoom ?? 1) - zoom) > 0.001
    || (clip.effects?.pan || 'none') !== pan;

  async function apply() {
    setBusy(true);
    setError('');
    try {
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/effects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zoom, pan }),
      });
      onApplied(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cg-panel-content">
      <div className="cg-panel-header">
        <h3 className="cg-heading-sm">Effects</h3>
      </div>
      <p className="cg-text-xs cg-text-muted">
        A slow zoom and a sideways slide, applied to the picture only. Captions stay sharp.
        Applying it makes the picture again, which takes a little while, and the clip needs its
        checklist confirmed again.
      </p>
      <label className="cg-field">
        <span className="cg-text-sm">Zoom: {zoom.toFixed(2)}×</span>
        <input className="cg-range" type="range" min="1" max="1.5" step="0.05" value={zoom} disabled={busy}
          onChange={(e) => setZoom(parseFloat(e.target.value))} />
      </label>
      <label className="cg-field">
        <span className="cg-text-sm">Pan</span>
        <select className="cg-select" value={pan} disabled={busy} onChange={(e) => setPan(e.target.value)}>
          {Object.entries(PAN_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      {error && <p className="cg-text-xs cg-text-error">{error}</p>}
      <button type="button" className="cg-btn cg-btn--primary cg-btn--sm"
        disabled={!changed || busy} onClick={apply}>
        {busy ? 'Making the picture…' : 'Apply picture effects'}
      </button>
    </div>
  );
}

export default function StudioEditor({
  jobId,
  clip: initialClip,
  tracks: musicTracks = [],
  onBack,
  onClipUpdated,
}) {
  const [clip, setClip] = useState(initialClip);
  const [leftTab, setLeftTab] = useState(initialClip.text?.needs_decision ? 'captions' : 'text'); // text | captions | audio
  const [showSafeZones, setShowSafeZones] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(initialClip.duration || 45);
  const [showExportModal, setShowExportModal] = useState(false);
  const videoRef = useRef(null);

  const base = `/api/jobs/${jobId}/clips/${clip.id}`;

  const applied = (updated) => {
    setClip(updated);
    if (onClipUpdated) onClipUpdated(updated);
  };

  const handleSeek = (t) => {
    setCurrentTime(t);
    if (videoRef.current) videoRef.current.currentTime = t;
  };

  const handleTogglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
    } else {
      videoRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const framingMode = clip.framing?.mode;
  const cutInPause = clip.cut?.start_snapped && clip.cut?.end_snapped;

  return (
    <div className="cg-studio-shell">
      <header className="cg-studio-topbar">
        <div className="cg-studio-topbar-left">
          <button className="cg-btn cg-btn--sm cg-btn--ghost" onClick={onBack}>← Gallery</button>
          <div className="cg-timeline-divider-v" />
          <span className="cg-studio-project-name"><strong>{clip.title || `Clip #${clip.id}`}</strong></span>
          <span className="cg-badge cg-badge--muted">{Math.round(duration * 10) / 10}s</span>
        </div>
        <div className="cg-studio-topbar-right">
          <button type="button" className={`cg-tool-pill ${showSafeZones ? 'active' : ''}`}
            onClick={() => setShowSafeZones(!showSafeZones)} title="Show where Shorts and Reels buttons cover the picture">
            Safe Zones
          </button>
          <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" onClick={() => setShowExportModal(true)}>
            Export Short ↓
          </button>
        </div>
      </header>

      <div className="cg-studio-stage">
        <aside className="cg-left-panel">
          <div className="cg-panel-tabs">
            {[['text', 'Text'], ['captions', 'Captions'], ['picture', 'Effects'], ['audio', 'Music']].map(([id, label]) => (
              <button key={id} type="button" className={`cg-panel-tab ${leftTab === id ? 'active' : ''}`}
                onClick={() => setLeftTab(id)}>
                {label}
              </button>
            ))}
          </div>

          <div className="cg-panel-body">
            {leftTab === 'text' && (
              <div className="cg-panel-content">
                <div className="cg-panel-header">
                  <h3 className="cg-heading-sm">Text on this clip</h3>
                </div>
                <p className="cg-text-sm">
                  {clip.text?.mode === 'headline' && clip.text.headline?.text
                    ? <>Your headline: <strong>{clip.text.headline.text}</strong></>
                    : clip.text?.mode === 'none' ? 'No text: this clip exports without text.'
                    : clip.text?.mode === 'pending' ? 'Waiting for your choice: no text is shown yet.'
                    : 'Word-by-word captions from the speech.'}
                </p>
                {clip.text?.reasons?.length > 0 && (
                  <ul className="cg-text-reasons">
                    {clip.text.reasons.map((r) => <li key={r} className="cg-text-xs">{r}</li>)}
                  </ul>
                )}
                <p className="cg-text-xs cg-text-muted">
                  ClipGenie keeps the transcript private. It only shows words it can trust, as
                  captions, or a headline you write and approve.
                </p>
                <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={() => setLeftTab('captions')}>
                  Change the text
                </button>
              </div>
            )}
            {leftTab === 'captions' && <CaptionsStylePanel jobId={jobId} clip={clip} onApplied={applied} />}
            {leftTab === 'picture' && <EffectsPanel jobId={jobId} clip={clip} onApplied={applied} />}
            {leftTab === 'audio' && <MusicPanel jobId={jobId} clip={clip} tracks={musicTracks} onApplied={applied} />}
          </div>
        </aside>

        <main className="cg-center-stage">
          <div className="cg-viewport-container">
            <video
              ref={videoRef}
              className="cg-viewport-screen"
              src={`${base}.mp4?v=${clip.version || 0}`}
              onTimeUpdate={() => videoRef.current && setCurrentTime(videoRef.current.currentTime)}
              onLoadedMetadata={(e) => setDuration(e.target.duration || initialClip.duration || 45)}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              playsInline
              preload="metadata"
            />
            {showSafeZones && (
              <div className="cg-safe-zones-overlay">
                <div className="cg-safe-zone-top">Top Profile Margin</div>
                <div className="cg-safe-zone-right">Like / Share Gutter</div>
                <div className="cg-safe-zone-bottom">Description & Sound Tag Zone (Do Not Obscure)</div>
              </div>
            )}
          </div>
          <div className="cg-transport-bar">
            <button type="button" className="cg-btn cg-btn--sm cg-btn--ghost" title="Back 1 second"
              onClick={() => handleSeek(Math.max(0, currentTime - 1))}>⏪</button>
            <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" onClick={handleTogglePlay}
              style={{ minWidth: 70 }}>{isPlaying ? '⏸' : '▶'}</button>
            <button type="button" className="cg-btn cg-btn--sm cg-btn--ghost" title="Forward 1 second"
              onClick={() => handleSeek(Math.min(duration, currentTime + 1))}>⏩</button>
          </div>
        </main>

        <aside className="cg-right-panel">
          <div className="cg-inspector-card">
            <div className="cg-inspector-header">
              <h4 className="cg-heading-sm">About this clip</h4>
            </div>
            <dl className="cg-detail-list">
              <dt>Length</dt>
              <dd>{Math.round(duration * 10) / 10} seconds</dd>
              <dt>Picture</dt>
              <dd>{FRAMING_LABELS[framingMode] || 'Vertical 9:16'}</dd>
              <dt>Cuts</dt>
              <dd>{cutInPause ? 'Start and end sit in natural pauses' : 'Short lead-in and tail around the speech'}</dd>
              <dt>Zoom</dt>
              <dd>{describeZoom(clip.effects)}</dd>
              <dt>Voice</dt>
              <dd>{describeVoice(clip.audio)}</dd>
              <dt>Text</dt>
              <dd>{describeText(clip.text)}</dd>
              <dt>Music</dt>
              <dd>{clip.music ? `${clip.music.title}, ${Math.round((clip.music.volume ?? 0.6) * 100)}%` : 'None'}</dd>
            </dl>
            <p className="cg-text-xs cg-text-muted">Coming to the editor:</p>
            <ul className="cg-soon-list">
              <li>Transitions <span>Soon</span></li>
              <li>AI visuals <span>Soon</span></li>
              <li>Editing assistant <span>Soon</span></li>
            </ul>
          </div>
        </aside>
      </div>

      <Timeline
        duration={duration}
        currentTime={currentTime}
        onSeek={handleSeek}
        tracks={buildTracks(clip, duration)}
        isPlaying={isPlaying}
        onTogglePlay={handleTogglePlay}
      />

      {showExportModal && (
        <ExportStudioModal
          jobId={jobId}
          clip={clip}
          onClose={() => setShowExportModal(false)}
          onChooseText={() => { setShowExportModal(false); setLeftTab('captions'); }}
          onConfirmed={applied}
        />
      )}
    </div>
  );
}
