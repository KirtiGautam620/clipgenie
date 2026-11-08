import { useEffect, useRef, useState } from 'react';
import './SongPartPicker.css';

export function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

// Pick which part of a song to use. The part is `windowLength` seconds long:
// at least `minLength` and at most `maxLength` (less only when the song ends first).
// `start` is where that part begins, in seconds from the start of the song.
export default function SongPartPicker({ id = 'song-part', songSeconds, start, onStart,
  minLength, maxLength, previewUrl, disabled = false }) {
  const [playing, setPlaying] = useState(false);
  const previewRef = useRef(null);

  const maxStart = Math.max(0, songSeconds - minLength);
  const at = Math.min(Math.max(0, start), maxStart);
  const windowLength = Math.max(0, Math.min(maxLength, songSeconds - at));

  function stopPreview() {
    if (previewRef.current) previewRef.current.pause();
    previewRef.current = null;
    setPlaying(false);
  }

  useEffect(() => () => { if (previewRef.current) previewRef.current.pause(); }, []);
  useEffect(() => { stopPreview(); }, [previewUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!(songSeconds > 0)) return null;

  function togglePreview() {
    if (playing) { stopPreview(); return; }
    const audio = new Audio(previewUrl);
    audio.preload = 'auto';
    // Browsers ignore a start position set before the file's length is known, so set it once it is.
    audio.addEventListener('loadedmetadata', () => { audio.currentTime = at; }, { once: true });
    audio.ontimeupdate = () => { if (audio.currentTime >= at + (windowLength || 30)) stopPreview(); };
    audio.onended = stopPreview;
    audio.play().catch(() => stopPreview());
    previewRef.current = audio;
    setPlaying(true);
  }

  return (
    <div className="cg-field">
      <div className="cg-position-header">
        <label className="cg-label" htmlFor={`${id}-start`}>Part of the song</label>
        <span className="cg-text-xs cg-text-secondary">
          {formatTime(at)} to {formatTime(at + windowLength)} of {formatTime(songSeconds)}
        </span>
      </div>
      <div className="cg-song-bar" aria-hidden="true">
        <div className="cg-song-window"
          style={{ left: `${(at / songSeconds) * 100}%`, width: `${(windowLength / songSeconds) * 100}%` }} />
      </div>
      {maxStart > 0 ? (
        <input id={`${id}-start`} type="range" className="cg-range" min="0" max={maxStart} step="0.5"
          value={at} disabled={disabled} onChange={(e) => onStart(Number(e.target.value))} />
      ) : (
        <p className="cg-text-xs cg-text-muted">This song is not longer than the part, so it starts from its beginning.</p>
      )}
      {previewUrl && (
        <button type="button" className="cg-btn cg-btn--sm" onClick={togglePreview} disabled={disabled}>
          {playing ? 'Stop preview' : 'Preview this part'}
        </button>
      )}
    </div>
  );
}
