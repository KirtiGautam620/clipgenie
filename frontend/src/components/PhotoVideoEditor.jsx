import { useRef, useState } from 'react';
import { getJSON } from '../api.js';
import './PhotoVideoEditor.css';
import './PhotoStudio.css';

const MIN_SECONDS = 1.5;      // the same shortest time a photo may show as the server
const TRANSITIONS = [
  ['cut', 'Cut'], ['fade', 'Fade in'],
  ['slide_left', 'Slide from left'], ['slide_right', 'Slide from right'],
  ['slide_top', 'Slide from top'], ['slide_bottom', 'Slide from bottom'],
  ['dice', 'Dice (tiles)'],
];
const TRANSITION_LABEL = Object.fromEntries(TRANSITIONS);
const TEXT_MOTION = [['none', 'Stays still'], ['left', 'From left'], ['right', 'From right'],
  ['top', 'From top'], ['bottom', 'From bottom']];
const SPEEDS = [['slow', 'Slow'], ['medium', 'Medium'], ['fast', 'Fast']];
const FRAMES = [['none', 'No frame'], ['white', 'White frame'], ['black', 'Black frame']];

// The time, as m:ss.hh
function clock(seconds) {
  const s = Math.max(0, seconds || 0);
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(2).padStart(5, '0')}`;
}

const round1 = (n) => Math.round(n * 10) / 10;

// Clideo-style editor: a preview, a settings panel for the selected photo, and a timeline. Drag a photo to
// move it, drag the edge between two photos to change how long each shows, click a marker to change a
// transition. Changes are kept here until "Make video" (one render for all of them).
export default function PhotoVideoEditor({ project, onProject, working }) {
  const photos = project.photos;
  const total = project.song_seconds || 0;
  const isLyrics = Boolean(project.timing);
  const baseline = project.photo_times || photos.map(() => total / Math.max(1, photos.length));
  const [order, setOrder] = useState(() => photos.map((p) => p.file));   // display order (file names)
  const [lengths, setLengths] = useState(() => Object.fromEntries(photos.map((p, i) => [p.file, baseline[i]])));
  const [pending, setPending] = useState({});                             // file -> changed fields
  const [selected, setSelected] = useState(photos[0]?.file);
  const [tab, setTab] = useState('text');
  const [dragFile, setDragFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reply, setReply] = useState('');
  const [now, setNow] = useState(0);
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef(null);
  const trackRef = useRef(null);
  const locked = working || saving;

  const originalIndex = (file) => photos.findIndex((p) => p.file === file);
  const orderChanged = order.some((file, i) => file !== photos[i].file);
  const lengthsChanged = photos.some((p, i) => Math.abs(lengths[p.file] - baseline[i]) > 0.01);
  const changeCount = Object.keys(pending).length + (orderChanged ? 1 : 0) + (lengthsChanged ? 1 : 0);

  // The photos in display order, with their start times and lengths.
  const shown = [];
  let at = 0;
  order.forEach((file, pos) => {
    const base = photos[originalIndex(file)];
    const dur = lengths[file] || 0;
    shown.push({ ...base, ...(pending[file] || {}), file, pos, start: at, dur });
    at += dur;
  });
  const current = shown.find((p) => p.file === selected) || shown[0];
  const done = project.status === 'done';

  function photoUrl(file) {
    return `/api/photo-videos/${project.id}/photos/${file}`;
  }

  function stage(file, fields) {
    setPending((prev) => ({ ...prev, [file]: { ...(prev[file] || {}), ...fields } }));
    setError('');
    setReply('');
  }

  function moveTo(file, to) {
    setOrder((prev) => {
      const from = prev.indexOf(file);
      if (from < 0 || to < 0 || to >= prev.length || from === to) return prev;
      const next = [...prev];
      next.splice(from, 1);
      next.splice(to, 0, file);
      return next;
    });
    setError('');
  }

  function equalLengths() {
    setLengths(Object.fromEntries(photos.map((p) => [p.file, total / photos.length])));
  }

  function discard() {
    setPending({});
    setOrder(photos.map((p) => p.file));
    setLengths(Object.fromEntries(photos.map((p, i) => [p.file, baseline[i]])));
    setError('');
  }

  // Drag the edge after photo `pos`: that photo and the next one share their time between them.
  function startResize(e, pos) {
    e.preventDefault();
    e.stopPropagation();
    const left = shown[pos].file;
    const right = shown[pos + 1].file;
    const startX = e.clientX;
    const pair = lengths[left] + lengths[right];
    const startLeft = lengths[left];
    const width = trackRef.current ? trackRef.current.getBoundingClientRect().width : 1;
    const move = (ev) => {
      const delta = ((ev.clientX - startX) / width) * total;
      const next = round1(Math.min(Math.max(startLeft + delta, MIN_SECONDS), pair - MIN_SECONDS));
      setLengths((prev) => ({ ...prev, [left]: next, [right]: round1(pair - next) }));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }

  async function makeVideo() {
    setSaving(true);
    setError('');
    setReply('');
    // the server applies the changes first, then the order and the lengths, which are in the new order
    const body = {
      changes: Object.entries(pending).map(([file, fields]) => ({ index: originalIndex(file) + 1, ...fields })),
    };
    if (orderChanged) body.order = order.map((file) => originalIndex(file) + 1);
    if (lengthsChanged) {
      const parts = order.map((file) => round1(lengths[file]));
      parts[parts.length - 1] = round1(total - parts.slice(0, -1).reduce((a, b) => a + b, 0));  // exact total
      body.durations = parts;
    }
    try {
      const updated = await getJSON(`/api/photo-videos/${project.id}/changes`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      setPending({});
      onProject(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function sendRequest(e) {
    e.preventDefault();
    if (!message.trim()) return;
    setSaving(true);
    setError('');
    try {
      const result = await getJSON(`/api/photo-videos/${project.id}/edit`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }),
      });
      setReply(result.reply);
      if (result.changed) {
        setMessage('');
        onProject(result.project);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  // Playback follows the rendered video (the real transitions).
  function togglePlay() {
    const v = videoRef.current;
    if (!v || !done) return;
    if (v.paused) v.play(); else v.pause();
  }

  function seekTo(seconds) {
    const t = Math.min(Math.max(0, seconds), total);
    setNow(t);
    if (videoRef.current && done) videoRef.current.currentTime = t;
  }

  function seekFromTrack(e) {
    const rect = trackRef.current.getBoundingClientRect();
    seekTo(((e.clientX - rect.left) / rect.width) * total);
  }

  const playheadLeft = total ? `${(now / total) * 100}%` : '0%';
  const videoSrc = `/api/photo-videos/${project.id}/video.mp4?v=${project.version || 0}`;

  return (
    <section className="pvs" aria-label="Photo video editor">
      <div className="pvs-top">
        <div>
          <h2 className="pvs-title">Edit your photo video</h2>
          <p className="pvs-sub">{photos.length} photos · {Math.round(total)} s · {isLyrics ? 'with lyrics' : 'no lyrics'}</p>
        </div>
        <div className="pvs-top-actions">
          {changeCount > 0 && (
            <>
              <span className="pvs-count">{changeCount} change{changeCount === 1 ? '' : 's'} not made yet</span>
              <button type="button" className="pve-button pve-button--secondary" disabled={locked} onClick={discard}>
                Discard
              </button>
              <button type="button" className="pve-button pve-button--primary" disabled={locked} onClick={makeVideo}>
                {saving ? 'Making the video…' : 'Make video'}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="pvs-body">
        <aside className="pvs-panel" aria-label="Photo settings">
          {current && (
            <>
              <div className="pvs-tabs" role="tablist">
                {[['text', 'Text'], ['transition', 'Transition'], ['frame', 'Frame']].map(([id, label]) => (
                  <button key={id} type="button" role="tab" aria-selected={tab === id}
                    className={`pvs-tab${tab === id ? ' pvs-tab--on' : ''}`} onClick={() => setTab(id)}>{label}</button>
                ))}
              </div>
              <div className="pvs-photo-head">
                <span className="pvs-photo-num">{current.pos + 1}</span>
                <span className="pvs-photo-name" title={current.name}>{current.name}</span>
              </div>

              {tab === 'text' && (
                <PhotoText key={`${current.file}-${current.text}`} photo={current} locked={locked || isLyrics}
                  onStage={(fields) => stage(current.file, fields)} />
              )}
              {tab === 'transition' && (
                <div className="pvs-fields">
                  <label className="pve-label" htmlFor="pvs-transition">Photo comes in</label>
                  <select id="pvs-transition" value={current.transition || 'cut'}
                    disabled={locked || current.pos === 0}
                    onChange={(e) => stage(current.file, { transition: e.target.value })}>
                    {TRANSITIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  <label className="pve-label" htmlFor="pvs-speed">Speed</label>
                  <select id="pvs-speed" value={current.transition_speed || 'medium'}
                    disabled={locked || current.transition === 'cut' || current.pos === 0}
                    onChange={(e) => stage(current.file, { transition_speed: e.target.value })}>
                    {SPEEDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  <label className="pve-label" htmlFor="pvs-text-motion">Text comes in</label>
                  <select id="pvs-text-motion" value={current.text_motion || 'none'} disabled={locked || isLyrics}
                    onChange={(e) => stage(current.file, { text_motion: e.target.value })}>
                    {TEXT_MOTION.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  {current.pos === 0 && <p className="pve-hint">The first photo has nothing before it, so it cannot slide or land in.</p>}
                </div>
              )}
              {tab === 'frame' && (
                <div className="pvs-fields">
                  <label className="pve-label" htmlFor="pvs-frame">Border</label>
                  <select id="pvs-frame" value={current.frame || 'none'} disabled={locked}
                    onChange={(e) => stage(current.file, { frame: e.target.value })}>
                    {FRAMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              )}

              <div className="pvs-move">
                <button type="button" className="pve-button" disabled={locked || current.pos === 0}
                  onClick={() => moveTo(current.file, current.pos - 1)}>← Move earlier</button>
                <button type="button" className="pve-button" disabled={locked || current.pos === shown.length - 1}
                  onClick={() => moveTo(current.file, current.pos + 1)}>Move later →</button>
              </div>
              {isLyrics && <p className="pve-hint">Lyric videos keep their photo order, lengths and text. The lyric lines show while they are sung.</p>}
            </>
          )}

          <form className="pve-command" onSubmit={sendRequest}>
            <label className="pve-label" htmlFor="pv-command">Or type a request</label>
            <div className="pve-command-row">
              <input id="pv-command" type="text" value={message} disabled={locked}
                placeholder="e.g. slide in from the top on photo 2, fast"
                onChange={(e) => setMessage(e.target.value)} />
              <button type="submit" className="pve-button pve-button--primary" disabled={locked || !message.trim()}>
                {saving ? 'Working…' : 'Apply'}
              </button>
            </div>
          </form>
          {reply && <p className="pve-status" role="status">{reply}</p>}
          {error && <p className="pve-error" role="alert">{error}</p>}
        </aside>

        <div className="pvs-stage">
          <div className="pvs-screen">
            {done ? (
              <video ref={videoRef} className="pvs-video" src={videoSrc} playsInline
                onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
                onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
                onEnded={() => setPlaying(false)} />
            ) : current && (
              <div className="pvs-still">
                <img src={photoUrl(current.file)} alt="" />
                {current.text && <span className="pvs-still-text">{current.text}</span>}
              </div>
            )}
            {working && <div className="pvs-busy">Making your video…</div>}
          </div>
          <p className="pvs-note">
            {done && changeCount > 0
              ? 'This is the last video made. Press Make video to show your changes.'
              : done ? 'Playing the video as it was made.' : 'The video is not made yet. Press Make video when ready.'}
          </p>
        </div>
      </div>

      <div className="pvs-timeline">
        <div className="pvs-controls">
          <button type="button" className="pvs-play" disabled={!done} onClick={togglePlay}
            aria-label={playing ? 'Pause' : 'Play'}>{playing ? '❚❚' : '▶'}</button>
          <span className="pvs-clock">{clock(now)} / {clock(total)}</span>
          <div className="pvs-controls-right">
            {lengthsChanged && (
              <button type="button" className="pve-button pve-button--secondary" disabled={locked} onClick={equalLengths}>
                Equal lengths
              </button>
            )}
          </div>
        </div>

        <div className="pvs-track-wrap">
          <div className="pvs-track" ref={trackRef} onClick={seekFromTrack} role="presentation">
            {shown.map((p) => (
              <div key={p.file}
                className={`pvs-block${current && p.file === current.file ? ' pvs-block--on' : ''}`}
                style={{ left: `${total ? (p.start / total) * 100 : 0}%`, width: `${total ? (p.dur / total) * 100 : 0}%` }}
                draggable={!locked && !isLyrics}
                onDragStart={(e) => { setDragFile(p.file); e.dataTransfer.effectAllowed = 'move'; }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); moveTo(dragFile, p.pos); setDragFile(null); }}
                onClick={(e) => { e.stopPropagation(); setSelected(p.file); }}
                title={`${p.name} · ${p.dur.toFixed(1)} s`}>
                <img src={photoUrl(p.file)} alt="" draggable={false} />
                <span className="pvs-block-num">{p.pos + 1}</span>
                <span className="pvs-block-len">{p.dur.toFixed(1)} s</span>
              </div>
            ))}
            {shown.slice(0, -1).map((p) => (
              <div key={`h-${p.file}`} className="pvs-handle" style={{ left: `${total ? ((p.start + p.dur) / total) * 100 : 0}%` }}
                onPointerDown={(e) => { if (!locked && !isLyrics) startResize(e, p.pos); }}
                onClick={(e) => e.stopPropagation()}
                role="separator" aria-orientation="vertical" aria-label={`Change the length of photo ${p.pos + 1}`}
                title="Drag to change how long each photo shows" />
            ))}
            <div className="pvs-playhead" style={{ left: playheadLeft }} aria-hidden="true" />
          </div>
          {/* transition markers sit ABOVE the track, so they never cover the photos */}
          <div className="pvs-markers">
            {shown.slice(1).map((p) => (
              <button key={`m-${p.file}`} type="button"
                className={`pvs-marker${current && p.file === current.file && tab === 'transition' ? ' pvs-marker--on' : ''}`}
                style={{ left: `${total ? (p.start / total) * 100 : 0}%` }}
                title={`${TRANSITION_LABEL[p.transition] || 'Cut'}: click to change`}
                onClick={(e) => { e.stopPropagation(); setSelected(p.file); setTab('transition'); }}>
                {TRANSITION_LABEL[p.transition] || 'Cut'}
              </button>
            ))}
          </div>
        </div>
        <p className="pvs-hint-line">
          {isLyrics
            ? 'Lyric videos keep their order and lengths.'
            : 'Drag a photo to move it · drag the line between two photos to change their lengths · click a transition to change it.'}
        </p>
      </div>
    </section>
  );
}

// The text box of the selected photo. It is kept here until you press Make video.
function PhotoText({ photo, locked, onStage }) {
  const [text, setText] = useState(photo.text || '');
  function save() {
    if (text.trim() !== (photo.text || '')) onStage({ text });
  }
  return (
    <div className="pvs-fields">
      <label className="pve-label" htmlFor="pvs-text">Text on this photo</label>
      <input id="pvs-text" type="text" value={text} maxLength={40} disabled={locked} placeholder="No text"
        onChange={(e) => setText(e.target.value)} onBlur={save}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
      <p className="pve-hint">Press Enter or click away to keep it. Press Make video to show it on the video.</p>
    </div>
  );
}
