import { useState } from "react";
import { getJSON } from "./api.js";

// One finished clip: preview, music controls, and the copyright checklist before download.
export default function ClipCard({ jobId, clip, tracks, onUpdated }) {
  const [trackId, setTrackId] = useState(clip.music?.track_id || "");
  const [volume, setVolume] = useState(clip.music?.volume ?? 0.6);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false); // checklist panel open
  const [ticked, setTicked] = useState([]);
  const [copied, setCopied] = useState(false);

  const base = `/api/jobs/${jobId}/clips/${clip.id}`;

  async function post(path, body) {
    return getJSON(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function applyMusic() {
    setBusy(true);
    setError("");
    try {
      onUpdated(await post("/music", { track_id: trackId || null, volume }));
      setChecking(false);
      setTicked([]);
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  }

  async function confirmAndDownload() {
    setBusy(true);
    setError("");
    try {
      onUpdated(await post("/checklist", { items: ticked }));
      setChecking(false);
      window.location.href = `${base}/download`; // the server only allows this after confirming
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  }

  function toggle(id) {
    setTicked((t) => (t.includes(id) ? t.filter((x) => x !== id) : [...t, id]));
  }

  async function copyCredits() {
    try {
      await navigator.clipboard.writeText(clip.credits);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard not available: the text is selectable in the box */
    }
  }

  const musicChanged = (clip.music?.track_id || "") !== trackId ||
    (trackId && Math.abs((clip.music?.volume ?? 0) - volume) > 0.001);
  const allTicked = clip.checklist.every((i) => ticked.includes(i.id));

  return (
    <div className="clip">
      <video src={`${base}.mp4?v=${clip.version || 0}#t=1`} controls preload="metadata" />
      <p><b>{clip.title || `Clip ${clip.id}`}</b></p>
      <p>
        {clip.duration}s{clip.mood && clip.mood !== "other" ? ` · ${clip.mood}` : ""}
        {clip.score ? ` · score ${clip.score}/10` : ""}
      </p>
      <p className="why">{clip.reason}</p>

      <div className="music-box">
        <label>🎵 Music{" "}
          <select value={trackId} onChange={(e) => setTrackId(e.target.value)} disabled={busy}>
            <option value="">No music</option>
            {tracks.map((t) => (
              <option key={t.id} value={t.id}>{t.title} ({t.moods[0]})</option>
            ))}
          </select>
        </label>
        {trackId && (
          <label>Volume {Math.round(volume * 100)}%{" "}
            <input type="range" min="0" max="1" step="0.05" value={volume} disabled={busy}
              onChange={(e) => setVolume(+e.target.value)} />
          </label>
        )}
        {trackId && <audio controls preload="none" src={`/api/music/${trackId}/preview`} />}
        {musicChanged && (
          <button type="button" onClick={applyMusic} disabled={busy}>
            {busy ? "Mixing…" : "Apply music"}
          </button>
        )}
        {clip.music && <p className="hint">Licence: {clip.music.license}</p>}
      </div>

      {clip.warnings.map((w) => <p key={w} className="warn">⚠️ {w}</p>)}
      {error && <p className="error small">⚠️ {error}</p>}

      {clip.confirmed ? (
        <>
          <a className="button" href={`${base}/download`}>Download MP4</a>
          {clip.credits && (
            <div className="credits">
              <b>Credits for your video description</b>
              <textarea readOnly rows={3} value={clip.credits} />
              <button type="button" onClick={copyCredits}>{copied ? "Copied ✓" : "Copy credits"}</button>
            </div>
          )}
          <a className="link-a" href={`${base}/report`}>Save rights report (JSON)</a>
        </>
      ) : checking ? (
        <div className="checklist">
          <b>Before you download</b>
          {clip.checklist.map((i) => (
            <label key={i.id} className="check">
              <input type="checkbox" checked={ticked.includes(i.id)} onChange={() => toggle(i.id)} />
              <span>{i.text}</span>
            </label>
          ))}
          <div className="row">
            <button type="button" onClick={confirmAndDownload} disabled={!allTicked || busy}>
              Confirm and download
            </button>
            <button type="button" className="link" onClick={() => setChecking(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button type="button" onClick={() => setChecking(true)}>Download…</button>
      )}
    </div>
  );
}
