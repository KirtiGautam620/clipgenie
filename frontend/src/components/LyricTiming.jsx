import { useState } from 'react';
import { getJSON } from '../api.js';
import './PhotoVideoEditor.css';

// Lets the user check where each lyric line was placed in the song, change any time, then make the video.
export default function LyricTiming({ project, onProject }) {
  const lines = project.timing?.lines || [];
  const songSeconds = project.song_total_seconds || 0;
  const [starts, setStarts] = useState(() => lines.map((l) => l.start));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const invalid = starts.some((s, i) => !Number.isFinite(s) || s < 0 || s > songSeconds
    || (i > 0 && s < starts[i - 1]));

  function setLine(i, value) {
    setStarts((prev) => prev.map((s, j) => (j === i ? Number(value) : s)));
  }

  async function makeVideo() {
    setSaving(true);
    setError('');
    try {
      onProject(await getJSON(`/api/photo-videos/${project.id}/timing`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ starts }),
      }));
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="pve" aria-labelledby="lt-title">
      <h2 id="lt-title" className="pve-title">Check the lyric times</h2>
      <p className="pve-hint">
        Each line is placed where the song seems to sing it. Lines marked "estimated" were not heard clearly,
        so check those first. Times are in seconds from the start of the song (the whole song is {Math.round(songSeconds)} s).
      </p>
      <ol className="pve-timing">
        {lines.map((line, i) => (
          <li key={i} className="pve-timing-row">
            <input type="number" step="0.1" min="0" max={songSeconds} value={starts[i]}
              aria-label={`Start time of line ${i + 1}`} disabled={saving}
              onChange={(e) => setLine(i, e.target.value)} />
            <span className="pve-timing-text">{line.text}</span>
            {!line.heard && <span className="pve-tag">estimated</span>}
          </li>
        ))}
      </ol>
      {invalid && <p className="pve-error" role="alert">Times must be in order and inside the song.</p>}
      {error && <p className="pve-error" role="alert">{error}</p>}
      <div>
        <button type="button" className="pve-button pve-button--primary" disabled={invalid || saving} onClick={makeVideo}>
          {saving ? 'Making the video…' : 'Make video with these times'}
        </button>
      </div>
    </section>
  );
}
