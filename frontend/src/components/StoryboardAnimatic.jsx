import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getJSON } from '../api.js';
import { copyText } from '../copy.js';

// Makes and plays the animatic: a real video of the user's own photo moving through the scenes.
export default function StoryboardAnimatic({ storyboardId, blockers, ensureSaved, savedAt, music, onMusic }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [library, setLibrary] = useState(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);
  const base = `/api/storyboards/${storyboardId}/animatic`;

  const refresh = useCallback(async () => {
    try {
      setInfo(await getJSON(base));
    } catch (e) {
      setError(e.message);
    }
  }, [base]);

  // Look again whenever the storyboard is saved: the video may now be out of date.
  useEffect(() => { refresh(); }, [refresh, savedAt]);

  useEffect(() => {
    getJSON('/api/music').then((d) => setLibrary(d.tracks)).catch(() => setLibrary([]));
  }, []);

  // While it is being made, look in once a second.
  useEffect(() => {
    clearInterval(timer.current);
    if (info?.state === 'rendering') timer.current = setInterval(refresh, 1000);
    return () => clearInterval(timer.current);
  }, [info?.state, refresh]);

  async function start(quality) {
    setError('');
    setStarting(true);
    try {
      if (!(await ensureSaved())) return;                      // the video is made from the SAVED scenes
      setInfo(await getJSON(base, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quality }) }));
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

  async function cancel() {
    try {
      setInfo(await getJSON(`${base}/cancel`, { method: 'POST' }));
    } catch (e) {
      setError(e.message);
    }
  }

  async function download() {
    setError('');
    try {
      const res = await fetch(`${base}.mp4?download=1`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Request failed (${res.status})`);
      const link = document.createElement('a');
      link.href = URL.createObjectURL(await res.blob());
      link.download = `animatic_${storyboardId}.mp4`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      setError(e.message);
    }
  }

  async function copyCredits() {
    if (await copyText(info.music.credits)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } else {
      setError('The browser would not let ClipGenie copy. Select the credit text and copy it by hand.');
    }
  }

  const track = library?.find((t) => t.id === music.track_id);
  const missing = music.track_id && library && !track;
  const rendering = info?.state === 'rendering';
  const done = info?.state === 'done';
  const percent = Math.round((info?.progress || 0) * 100);
  const mb = info?.bytes ? (info.bytes / 1024 / 1024).toFixed(1) : null;

  return (
    <div className="cg-card cg-sb-animatic">
      <h2 className="cg-heading-sm">Animatic</h2>
      <p className="cg-text-xs cg-text-muted">
        A video of <strong>your own photo</strong> moving through the scenes above, with their transitions.
        It is not AI-generated and shows only zoom and movement. It follows the saved scenes.
      </p>

      <div className="cg-sb-music">
        <label className="cg-sb-ctl">Music (optional)
          <select className="cg-select" value={music.track_id || ''} disabled={rendering}
            onChange={(e) => onMusic({ ...music, track_id: e.target.value || null })}>
            <option value="">No music</option>
            {(library || []).map((t) => <option key={t.id} value={t.id}>{t.title}{t.moods?.[0] ? ` (${t.moods[0]})` : ''}</option>)}
          </select>
        </label>
        {library && library.length === 0 && (
          <p className="cg-text-xs cg-text-muted">There are no tracks yet. Add one on the Music screen.</p>
        )}
        {missing && <p className="cg-caption-error">This track is not in your library any more. Choose another.</p>}
        {track && (
          <>
            <label className="cg-sb-ctl">Volume {Math.round(music.volume * 100)}%
              <input type="range" className="cg-range" min="0" max="1" step="0.05" value={music.volume} disabled={rendering}
                onChange={(e) => onMusic({ ...music, volume: Number(e.target.value) })} />
            </label>
            <p className="cg-text-xs cg-text-muted">Licence: {track.license_label}</p>
            {track.warning && <p className="cg-sb-stale" role="note">{track.warning}</p>}
            <audio controls preload="none" src={`/api/music/${track.id}/preview`} aria-label={`Hear ${track.title}`} />
          </>
        )}
        <p className="cg-text-xs cg-text-muted">Music changes are saved with the storyboard, then used in the next video you make.</p>
      </div>

      {rendering ? (
        <>
          <progress className="cg-sb-progress" value={info.progress || 0} max="1" aria-label="Making the animatic" />
          <p className="cg-text-xs cg-text-muted" role="status">
            {info.phase === 'music' ? 'Adding the music…'
              : `Making the ${info.quality === 'full' ? 'full-quality video' : 'preview'}… ${percent}%`}
          </p>
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={cancel}>Stop</button>
        </>
      ) : (
        <div className="cg-caption-actions">
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={starting} onClick={() => start('preview')}>
            {done ? 'Make a new preview' : 'Make a preview'}
          </button>
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={starting} onClick={() => start('full')}
            title="Full size takes longer and uses more of your computer">
            Full quality
          </button>
        </div>
      )}

      {done && (
        <>
          <video className="cg-sb-video" controls preload="metadata" src={`${base}.mp4?v=${info.finished}`}
            aria-label="The animatic" />
          <p className="cg-text-xs cg-text-muted">
            {info.quality === 'full' ? 'Full quality' : 'Preview quality'} · {info.seconds} s{mb ? ` · ${mb} MB` : ''}
          </p>
          {info.music && (
            <div className="cg-sb-credits">
              <p className="cg-text-xs cg-text-muted">Music in this video: {info.music.title} ({info.music.license})</p>
              {info.music.warnings?.map((w) => <p key={w} className="cg-sb-stale" role="note">{w}</p>)}
              {info.music.credits && (
                <>
                  <pre className="cg-sb-credit-text">{info.music.credits}</pre>
                  <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={copyCredits}>
                    {copied ? '✓ Copied' : 'Copy credit text'}
                  </button>
                </>
              )}
            </div>
          )}
          {info.stale && (
            <p className="cg-sb-stale" role="note">The scenes have changed since this video was made. Make a new one to see the changes.</p>
          )}
          <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={blockers.length > 0}
            title={blockers.length ? blockers.join(' ') : 'Download the video'} onClick={download}>
            Download MP4
          </button>
        </>
      )}
      {info?.state === 'cancelled' && <p className="cg-text-xs cg-text-muted">Stopped. Nothing was kept.</p>}
      {info?.state === 'error' && <p className="cg-caption-error" role="alert">{info.error}</p>}
      {error && <p className="cg-caption-error" role="alert">{error}</p>}
    </div>
  );
}
