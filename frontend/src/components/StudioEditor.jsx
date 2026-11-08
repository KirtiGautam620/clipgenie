import React, { useState, useRef, useEffect } from 'react';
import Timeline from './Timeline.jsx';
import EditDecisionsPanel from './EditDecisionsPanel.jsx';
import CaptionsStylePanel from './CaptionsStylePanel.jsx';
import SongPartPicker from './SongPartPicker.jsx';
import ExportStudioModal from './ExportStudioModal.jsx';
import { getJSON } from '../api.js';
import { buildTracks, FRAMING_LABELS, keptSeconds, outputLength, outToSource, isCut, cutSegments, removedGaps, restoreGap, movePart } from '../studioTracks.js';
import './StudioEditor.css';

// Everything in this screen does what it says: what is shown comes from the clip's own data, and
// every control changes the real video (captions, headline, music, zoom and pan). AI visuals and an
// AI assistant are not here because they are not built yet.

import './StudioClideo.css';

// The left icon rail: the same tools as before, shown as icons with names (Clideo-style).
const RAIL = [['ai', 'AI edit', '✦'], ['text', 'Text', 'T'], ['captions', 'Captions', 'CC'],
  ['picture', 'Effects', '◐'], ['audio', 'Music', '♪']];

// The time, as m:ss.hh
function clock(seconds) {
  const s = Math.max(0, seconds || 0);
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(2).padStart(5, '0')}`;
}

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

function describeFades(fades) {
  const fin = fades?.in || 0;
  const fout = fades?.out || 0;
  if (!fin && !fout) return 'None';
  return [fin ? `in ${fin}s` : null, fout ? `out ${fout}s` : null].filter(Boolean).join(', ');
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
  const [start, setStart] = useState(clip.music?.start ?? 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setTrackId(clip.music?.track_id || '');
    setVolume(clip.music?.volume ?? 0.6);
    setStart(clip.music?.start ?? 0);
    setError('');
  }, [clip.id, clip.version]); // eslint-disable-line react-hooks/exhaustive-deps

  // Which part of a long song: the clip is this many seconds, so the start can go up to song - clip.
  const track = tracks.find((t) => t.id === trackId);
  const songLength = track?.seconds || 0;
  const clipLength = clip.duration || 0;
  const startAt = Math.min(start, Math.max(0, songLength - (clipLength || songLength)));

  const changed = (clip.music?.track_id || '') !== trackId
    || (trackId && (Math.abs((clip.music?.volume ?? 0) - volume) > 0.001
      || Math.abs((clip.music?.start ?? 0) - startAt) > 0.01));

  async function apply() {
    setBusy(true);
    setError('');
    try {
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/music`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: trackId || null, volume, start: startAt }),
      });
      onApplied(updated);
    } catch (e) {
      setError(e.message || 'Could not apply the music.');
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
          onChange={(e) => { setTrackId(e.target.value); setStart(0); }}>
          <option value="">No music</option>
          {tracks.map((t) => (
            <option key={t.id} value={t.id}>{t.title}{t.moods?.[0] ? ` (${t.moods[0]})` : ''}</option>
          ))}
        </select>
      </div>
      {trackId && (
        <SongPartPicker id="studio-music" songSeconds={songLength} start={startAt} onStart={setStart}
          minLength={clipLength || songLength} maxLength={clipLength || songLength}
          previewUrl={`/api/music/${trackId}/preview`} disabled={busy} />
      )}
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

const round1 = (n) => Math.round(n * 10) / 10;

// Effects, fades and trim. One panel, one Apply: everything is sent to the server as the clip's
// editing manifest, and the server remakes only the parts that changed.
function EffectsPanel({ jobId, clip, man, onApplied, onScrub }) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState('none');
  const [fadeIn, setFadeIn] = useState(0);
  const [fadeOut, setFadeOut] = useState(0);
  const [fadeSound, setFadeSound] = useState(true);
  const [dissolveOn, setDissolveOn] = useState(false);     // soften the cuts where pauses were removed
  const [dissolveSecs, setDissolveSecs] = useState(0.2);
  const [speed, setSpeed] = useState(1);             // the whole clip faster or slower (1 = as recorded)
  const [parts, setParts] = useState(null);          // the kept parts, with any cut-outs applied (source seconds)
  const [cutFrom, setCutFrom] = useState(0);         // finished-video seconds
  const [cutTo, setCutTo] = useState(0);
  const [cutError, setCutError] = useState('');
  const [trimStart, setTrimStart] = useState(0);   // seconds from the start of the finished video as it is now
  const [trimEnd, setTrimEnd] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // the finished video's length: the kept parts added up (shorter than the range when pauses were tightened)
  const length = man ? outputLength(man) : 0;

  // start from what the server has, and again whenever the clip is remade
  useEffect(() => {
    if (!man) return;
    setError('');
    setZoom(man.effects.zoom);
    setPan(man.effects.pan);
    setFadeIn(man.fades.in);
    setFadeOut(man.fades.out);
    setFadeSound(man.audio.fade_with_video);
    setDissolveOn(man.transition?.type === 'dissolve');
    setDissolveSecs(man.transition?.seconds ?? 0.2);
    setSpeed(man.speed || 1);
    setParts(man.segments.map((s) => ({ ...s })));
    setCutFrom(0);
    setCutTo(0);
    setCutError('');
    setTrimStart(0);
    setTrimEnd(round1(outputLength(man)));
  }, [man]);

  if (!man) {
    return (
      <div className="cg-panel-content">
        <div className="cg-panel-header"><h3 className="cg-heading-sm">Effects</h3></div>
        <p className="cg-text-xs cg-text-muted">Loading…</p>
      </div>
    );
  }

  const hasCuts = man.segments.length > 1;
  const currentParts = parts || man.segments;
  const cutsPending = JSON.stringify(currentParts) !== JSON.stringify(man.segments);
  const partsMoved = currentParts.some((p, i) => i > 0 && p.start < currentParts[i - 1].end - 0.001);
  const keptAfterCuts = round1(outputLength({ segments: currentParts, transition: man.transition }));
  const trimmed = trimStart > 0.04 || trimEnd < round1(length) - 0.04;
  const changed = trimmed
    || Math.abs(man.effects.zoom - zoom) > 0.001 || man.effects.pan !== pan
    || Math.abs(man.fades.in - fadeIn) > 0.001 || Math.abs(man.fades.out - fadeOut) > 0.001
    || man.audio.fade_with_video !== fadeSound
    || dissolveOn !== (man.transition?.type === 'dissolve')
    || (dissolveOn && Math.abs((man.transition?.seconds ?? 0.2) - dissolveSecs) > 0.001)
    || cutsPending
    || Math.abs((man.speed || 1) - speed) > 0.001;
  const fadesToLong = fadeIn + fadeOut > (trimEnd - trimStart);
  const kept = round1(trimEnd - trimStart);

  async function apply() {
    setBusy(true);
    setError('');
    try {
      const doc = JSON.parse(JSON.stringify(man));
      doc.effects = { zoom, pan };
      doc.fades = { in: fadeIn, out: fadeOut };
      doc.audio.fade_with_video = fadeSound;
      doc.transition = { type: dissolveOn ? 'dissolve' : 'none', seconds: dissolveSecs };
      if (cutsPending) doc.segments = currentParts;
      doc.speed = speed;
      if (trimmed) {                           // sliders are in the finished video's time: back to source seconds
        doc.clip = { start: round1(outToSource(man, trimStart)), end: round1(outToSource(man, trimEnd)) };
      }                                        // untouched: the exact original range goes back
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/manifest`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(doc),
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
        Changes are applied to the real video, and the captions stay sharp. Applying remakes the video,
        which takes a little while, and it needs its checklist confirmed again.
      </p>

      <h4 className="cg-panel-subhead">Motion</h4>
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

      <label className="cg-field">
        <span className="cg-text-sm">Speed: {speed.toFixed(2)}×</span>
        <input className="cg-range" type="range" min="0.8" max="1.25" step="0.05" value={speed} disabled={busy}
          onChange={(e) => setSpeed(parseFloat(e.target.value))} />
      </label>

      <h4 className="cg-panel-subhead">Fades</h4>
      <label className="cg-field">
        <span className="cg-text-sm">Fade in: {fadeIn.toFixed(1)}s</span>
        <input className="cg-range" type="range" min="0" max="3" step="0.1" value={fadeIn} disabled={busy}
          onChange={(e) => setFadeIn(parseFloat(e.target.value))} />
      </label>
      <label className="cg-field">
        <span className="cg-text-sm">Fade out: {fadeOut.toFixed(1)}s</span>
        <input className="cg-range" type="range" min="0" max="3" step="0.1" value={fadeOut} disabled={busy}
          onChange={(e) => setFadeOut(parseFloat(e.target.value))} />
      </label>
      <label className="cg-toggle">
        <input type="checkbox" checked={fadeSound} disabled={busy} onChange={(e) => setFadeSound(e.target.checked)} />
        <span className="cg-toggle-track" />
        <span className="cg-toggle-label">Fade the sound with the picture</span>
      </label>

      {hasCuts && (
        <>
          <h4 className="cg-panel-subhead">Between cuts</h4>
          <label className="cg-toggle">
            <input type="checkbox" checked={dissolveOn} disabled={busy || partsMoved} onChange={(e) => setDissolveOn(e.target.checked)} />
            <span className="cg-toggle-track" />
            <span className="cg-toggle-label">Soften the cuts where pauses were removed</span>
          </label>
          {dissolveOn && (
            <label className="cg-field">
              <span className="cg-text-sm">Dissolve: {dissolveSecs.toFixed(1)}s</span>
              <input className="cg-range" type="range" min="0.1" max="0.6" step="0.1" value={dissolveSecs} disabled={busy}
                onChange={(e) => setDissolveSecs(parseFloat(e.target.value))} />
            </label>
          )}
        </>
      )}

      <h4 className="cg-panel-subhead">Cut out a part</h4>
      <p className="cg-text-xs cg-text-muted">
        Remove a stretch from the middle, in the finished video's seconds. Cuts apply when you press Apply.
      </p>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <label className="cg-field" style={{ flex: 1 }}>
          <span className="cg-text-sm">From (s)</span>
          <input type="number" min="0" step="0.1" className="cg-input" value={cutFrom} disabled={busy}
            onChange={(e) => setCutFrom(parseFloat(e.target.value) || 0)} />
        </label>
        <label className="cg-field" style={{ flex: 1 }}>
          <span className="cg-text-sm">To (s)</span>
          <input type="number" min="0" step="0.1" className="cg-input" value={cutTo} disabled={busy}
            onChange={(e) => setCutTo(parseFloat(e.target.value) || 0)} />
        </label>
        <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={busy}
          onClick={() => {
            if (!(cutTo > cutFrom)) { setCutError('The end must be after the start.'); return; }
            const next = cutSegments({ segments: currentParts, transition: man.transition }, cutFrom, cutTo);
            if (!next.length || keptSeconds({ segments: next }) < 1) {
              setCutError('A video must keep at least 1 second.'); return;
            }
            setParts(next);
            setCutError('');
          }}>Cut out</button>
      </div>
      {cutError && <p className="cg-text-xs cg-text-error">{cutError}</p>}
      {cutsPending && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className="cg-text-xs">{keptAfterCuts}s kept after cuts</span>
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={busy}
            onClick={() => { setParts(man.segments.map((s) => ({ ...s }))); setCutError(''); }}>Undo cuts</button>
        </div>
      )}

      {currentParts.length > 1 && (
        <>
          <h4 className="cg-panel-subhead">Play order</h4>
          <p className="cg-text-xs cg-text-muted">Move a part earlier or later. Applies when you press Apply.</p>
          {currentParts.map((p, i) => (
            <div key={`${p.start}-${p.end}`} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span className="cg-text-sm" style={{ flex: 1 }}>
                {i + 1}. {p.start.toFixed(1)}s–{p.end.toFixed(1)}s
              </span>
              <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={busy || i === 0}
                aria-label={`Move part ${i + 1} earlier`} onClick={() => { setParts(movePart(currentParts, i, -1)); setCutError(''); }}>↑</button>
              <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={busy || i === currentParts.length - 1}
                aria-label={`Move part ${i + 1} later`} onClick={() => { setParts(movePart(currentParts, i, 1)); setCutError(''); }}>↓</button>
            </div>
          ))}
        </>
      )}

      {removedGaps(currentParts).length > 0 && (
        <>
          <h4 className="cg-panel-subhead">Put back a removed part</h4>
          <p className="cg-text-xs cg-text-muted">Bring back a pause or cut stretch. Applies when you press Apply.</p>
          {removedGaps(currentParts).map((g) => (
            <div key={g.start} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className="cg-text-sm" style={{ flex: 1 }}>Removed {g.length.toFixed(2)}s</span>
              <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={busy}
                onClick={() => { setParts(restoreGap(currentParts, g.index)); setCutError(''); }}>Put back</button>
            </div>
          ))}
        </>
      )}

      <h4 className="cg-panel-subhead">Trim</h4>
      <label className="cg-field">
        <span className="cg-text-sm">Start at {trimStart.toFixed(1)}s</span>
        <input className="cg-range" type="range" min="0" max={Math.max(0, round1(length) - 1)} step="0.1"
          value={trimStart} disabled={busy || cutsPending}
          onChange={(e) => { const v = parseFloat(e.target.value); setTrimStart(v); if (trimEnd - v < 1) setTrimEnd(round1(v + 1)); onScrub(v); }} />
      </label>
      <label className="cg-field">
        <span className="cg-text-sm">End at {trimEnd.toFixed(1)}s</span>
        <input className="cg-range" type="range" min="1" max={round1(length)} step="0.1" value={trimEnd} disabled={busy || cutsPending}
          onChange={(e) => { const v = parseFloat(e.target.value); setTrimEnd(v); if (v - trimStart < 1) setTrimStart(round1(Math.max(0, v - 1))); onScrub(Math.max(0, v - 0.05)); }} />
      </label>
      <p className="cg-text-xs cg-text-muted">
        {trimmed ? `Keeps ${kept}s of ${round1(length)}s. ` : `Whole video: ${round1(length)}s. `}
        Trimming only shortens a video and cannot be undone here: to get the full length back, make the
        videos again with Regenerate.{isCut(man) ? ' Long pauses were already shortened in this video.' : ''}
      </p>

      {fadesToLong && <p className="cg-text-xs cg-text-error">The two fades are longer than the video you are keeping.</p>}
      {error && <p className="cg-text-xs cg-text-error">{error}</p>}
      <button type="button" className="cg-btn cg-btn--primary cg-btn--sm"
        disabled={!changed || busy || fadesToLong} onClick={apply}>
        {busy ? 'Making the video…' : 'Apply changes'}
      </button>
    </div>
  );
}

// The look a new heading gets (the same as the server's default for headings)
const DEFAULT_HOOK_PRESET = 'plain';
// How long a heading stays on screen: 0 = the whole clip
const HOOK_DURATIONS = [3, 5, 8, 0];
const durationLabel = (s) => (s === 0 ? 'Whole clip' : `${s} seconds`);

// The hook: a title card over the first seconds, shown together with the captions. A suggestion from
// CocoGenie is only a draft: nothing goes on the video until you press "Add to video".
function HookSection({ jobId, clip, onApplied }) {
  const hook = clip.text?.hook;
  const [text, setText] = useState(hook?.text || '');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [seconds, setSeconds] = useState(hook?.style?.seconds ?? 0);

  useEffect(() => { setText(hook?.text || ''); setError(''); }, [clip.id, clip.version, hook?.text]);
  useEffect(() => { setSeconds(hook?.style?.seconds ?? 0); }, [clip.id, clip.version, hook?.style?.seconds]);

  async function send(body, label) {
    setBusy(label);
    setError('');
    try {
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/hook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      onApplied(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  const drawn = !!hook?.approved;
  const suggested = hook?.source === 'ai' && !drawn;
  const clean = text.trim();
  const previewQuery = new URLSearchParams({ preset: hook?.style?.preset || DEFAULT_HOOK_PRESET, seconds: String(hook?.style?.seconds || 3),
    ...(clean ? { text: clean } : {}) }).toString();
  // The server only puts a heading on clips whose speech it can trust (or with no text at all)
  const blocked = clip.text?.mode !== 'captions' && clip.text?.mode !== 'none';

  return (
    <div className="cg-hook-section">
      <h4 className="cg-panel-subhead">Heading</h4>
      {blocked && (
        <p className="cg-text-xs cg-text-muted">
          A heading can't be added to this clip because its speech isn't clear enough to trust. Use
          “Change the text” above and choose a headline you write instead.
        </p>
      )}
      {suggested && (
        <p className="cg-text-xs cg-text-muted">
          CocoGenie suggests this heading from what is said. It is not on your video yet: edit it if you like, then add it.
        </p>
      )}
      {!hook && !blocked && (
        <p className="cg-text-xs cg-text-muted">
          A short title over the top of the video, shown together with the captions. Write your own.
        </p>
      )}
      <label className="cg-field">
        <span className="cg-text-sm">{drawn ? 'On your video' : 'Heading text'}</span>
        <textarea className="cg-input cg-headline-input" rows={2} maxLength={120} value={text}
          placeholder="e.g. the one thing most people miss" disabled={!!busy || blocked}
          onChange={(e) => setText(e.target.value)} />
      </label>
      {!blocked && (
        <label className="cg-field">
          <span className="cg-text-sm">How long it stays</span>
          <select className="cg-input" value={seconds} disabled={!!busy}
            onChange={(e) => setSeconds(Number(e.target.value))}>
            {[...new Set([...HOOK_DURATIONS, seconds])].sort((a, b) => (a === 0 ? 1 : b === 0 ? -1 : a - b))
              .map((v) => <option key={v} value={v}>{durationLabel(v)}</option>)}
          </select>
        </label>
      )}
      {clean && !blocked && <div className="cg-caption-preview"><img src={`/api/headline-preview.png?${previewQuery}`} alt="Heading preview" /></div>}
      {error && <p className="cg-text-xs cg-text-error">{error}</p>}
      <div className="cg-hook-actions">
        <button type="button" className="cg-btn cg-btn--primary cg-btn--sm"
          disabled={blocked || !clean || !!busy || (drawn && clean === hook.text)}
          onClick={() => send({ text: clean, approve: true, style: { seconds } }, 'add')}>
          {busy === 'add' ? 'Adding…' : drawn ? 'Update heading' : 'Add to video'}
        </button>
        {hook && (
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={!!busy}
            onClick={() => send({ remove: true }, 'remove')}>
            {drawn ? 'Remove from video' : 'Discard suggestion'}
          </button>
        )}
      </div>
      {drawn && <p className="cg-text-xs cg-text-muted">Adding or removing a heading remakes the video and needs its checklist confirmed again.</p>}
    </div>
  );
}

// Make the clip longer at its end, so it does not stop in the middle of a sentence. The footage
// after the clip is used, and the captions said in that time are added.
function ExtendSection({ jobId, clip, onApplied }) {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  async function extend(body, label) {
    setBusy(label);
    setError('');
    try {
      const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/extend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      onApplied(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="cg-hook-section">
      <h4 className="cg-panel-subhead">Length</h4>
      <p className="cg-text-xs cg-text-muted">
        This clip is {Math.round(clip.duration)} seconds. If it stops in the middle of a thought, make it longer.
        The footage after the clip is used, and its captions are added. Extending remakes the video, so its checklist must be confirmed again.
      </p>
      <div className="cg-hook-actions">
        <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={!!busy}
          onClick={() => extend({ to_sentence: true }, 'sentence')}>
          {busy === 'sentence' ? 'Extending…' : 'Extend to end of sentence'}
        </button>
        {[2, 5].map((n) => (
          <button key={n} type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={!!busy}
            onClick={() => extend({ seconds: n }, `s${n}`)}>
            {busy === `s${n}` ? 'Extending…' : `+${n} seconds`}
          </button>
        ))}
      </div>
      {error && <p className="cg-text-xs cg-text-error">{error}</p>}
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
  const [leftTab, setLeftTab] = useState(   // text | captions | picture | audio | ai
    initialClip.text?.needs_decision ? 'captions' : initialClip.edit?.mode === 'assist' ? 'ai' : 'text');
  const [showSafeZones, setShowSafeZones] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(initialClip.duration || 45);
  const [showExportModal, setShowExportModal] = useState(false);
  const [man, setMan] = useState(null);          // the clip's editing manifest (see the Effects tab)
  const videoRef = useRef(null);

  const base = `/api/jobs/${jobId}/clips/${clip.id}`;

  const applied = (updated) => {
    setClip(updated);
    if (onClipUpdated) onClipUpdated(updated);
  };

  // Make the clip longer from the timeline (drag the end of the video). The footage after it is used.
  async function extendClip(seconds) {
    const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/extend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds }),
    });
    applied(updated);
  }

  // Change how long the hook stays, from the timeline. Same text and look; only the length changes.
  async function resizeHook(seconds) {
    const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/hook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: clip.text.hook.text, approve: true, style: { seconds } }),
    });
    applied(updated);
  }

  // Fix the words of one caption block from the timeline. The block keeps the same number of words
  // (adding or removing words is done in the Captions tab), so the timing stays as it was.
  async function editCaption(block, text) {
    const saved = clip.captions?.words || [];
    const parts = text.split(/\s+/).filter(Boolean);
    const count = block.wordIdx.length;
    if (parts.length !== count) {
      throw new Error(`Keep ${count} word${count === 1 ? '' : 's'} in this caption. `
        + 'To add or remove words, use the Captions tab.');
    }
    const texts = saved.map((w) => w.text);
    block.wordIdx.forEach((idx, k) => { texts[idx] = parts[k]; });
    const updated = await getJSON(`/api/jobs/${jobId}/clips/${clip.id}/captions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: null, style: {}, words: texts }),
    });
    applied(updated);
  }

  // the manifest describes how this clip is made; load it again whenever the clip is remade
  useEffect(() => {
    let cancelled = false;
    getJSON(`/api/jobs/${jobId}/clips/${clip.id}/manifest`).then((m) => { if (!cancelled) setMan(m); })
      .catch(() => { if (!cancelled) setMan(null); });
    return () => { cancelled = true; };
  }, [jobId, clip.id, clip.version]);

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
        <nav className="cg-studio-rail" aria-label="Editing tools">
          {RAIL.map(([id, label, glyph]) => (
            <button key={id} type="button" className={`cg-rail-btn ${leftTab === id ? 'active' : ''}`}
              aria-current={leftTab === id ? 'true' : undefined} onClick={() => setLeftTab(id)}>
              <span className="cg-rail-glyph" aria-hidden="true">{glyph}</span>
              <span className="cg-rail-label">{label}</span>
            </button>
          ))}
        </nav>

        <aside className="cg-left-panel">

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
                  CocoGenie keeps the transcript private. It only shows words it can trust, as
                  captions, or a headline you write and approve.
                </p>
                <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={() => setLeftTab('captions')}>
                  Change the text
                </button>
                <HookSection jobId={jobId} clip={clip} onApplied={applied} />
              </div>
            )}
            {leftTab === 'captions' && <CaptionsStylePanel jobId={jobId} clip={clip} onApplied={applied} />}
            {leftTab === 'ai' && (
              <EditDecisionsPanel jobId={jobId} clip={clip} man={man} onApplied={applied} onOpenText={() => setLeftTab('text')} />
            )}
            {leftTab === 'picture' && (
              <>
                <ExtendSection jobId={jobId} clip={clip} onApplied={applied} />
                <EffectsPanel jobId={jobId} clip={clip} man={man} onApplied={applied} onScrub={handleSeek} />
              </>
            )}
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
            <span className="cg-clock">{clock(currentTime)} / {clock(duration)}</span>
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
              <dt>Pauses</dt>
              <dd>{man && isCut(man)
                ? `${round1(man.clip.end - man.clip.start - keptSeconds(man))}s of long pauses removed`
                : 'As spoken'}</dd>
              <dt>Fades</dt>
              <dd>{describeFades(clip.fades)}</dd>
              <dt>Voice</dt>
              <dd>{describeVoice(clip.audio)}</dd>
              <dt>Text</dt>
              <dd>{describeText(clip.text)}</dd>
              <dt>Music</dt>
              <dd>{clip.music ? `${clip.music.title}, ${Math.round((clip.music.volume ?? 0.6) * 100)}%` : 'None'}</dd>
            </dl>
            <p className="cg-text-xs cg-text-muted">Coming to the editor:</p>
            <ul className="cg-soon-list">
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
        tracks={buildTracks(clip, duration, man)}
        isPlaying={isPlaying}
        onTogglePlay={handleTogglePlay}
        onEditCaption={editCaption}
        onExtend={extendClip}
        onResizeHook={resizeHook}
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
