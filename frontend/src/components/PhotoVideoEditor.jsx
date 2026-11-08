import { useState } from 'react';
import { getJSON } from '../api.js';
import './PhotoVideoEditor.css';

const COMES_IN = [
  ['cut', 'Cut (no move)'], ['fade', 'Fade in'],
  ['slide_left', 'Slide in from left'], ['slide_right', 'Slide in from right'],
  ['slide_top', 'Slide in from top'], ['slide_bottom', 'Slide in from bottom'],
];
const TEXT_COMES_IN = [
  ['none', 'Stays still'], ['left', 'Comes in from left'], ['right', 'Comes in from right'],
  ['top', 'Comes in from top'], ['bottom', 'Comes in from bottom'],
];
const SPEEDS = [['slow', 'Slow'], ['medium', 'Medium'], ['fast', 'Fast']];
const FRAMES = [['none', 'No frame'], ['white', 'White frame'], ['black', 'Black frame']];

// Change one photo at a time, or type a request such as "slide in from the top on photo 2, fast".
export default function PhotoVideoEditor({ project, onProject, working }) {
  const [message, setMessage] = useState('');
  const [reply, setReply] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const locked = working || saving;

  async function changePhoto(index, body) {
    setSaving(true);
    setError('');
    setReply('');
    try {
      onProject(await getJSON(`/api/photo-videos/${project.id}/photos/${index}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }));
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

  return (
    <section className="pve" aria-labelledby="pve-title">
      <h2 id="pve-title" className="pve-title">Change a part of the video</h2>
      <p className="pve-hint">Change one photo at a time, or type a request below. Each change makes the video again.</p>

      <div className="pve-cards">
        {project.photos.map((p, i) => (
          <PhotoCard key={`${p.file}-${project.version || 0}`} index={i} photo={p} locked={locked}
            onChange={(body) => changePhoto(i + 1, body)} />
        ))}
      </div>

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
    </section>
  );
}

function PhotoCard({ index, photo, locked, onChange }) {
  const [text, setText] = useState(photo.text || '');
  const comesIn = photo.transition === 'slide' ? 'slide_right' : (photo.transition || 'cut');
  const textMotion = photo.text_motion || 'none';

  function saveText() {
    if (text.trim() !== (photo.text || '')) onChange({ text });
  }

  return (
    <article className="pve-card">
      <header className="pve-card-head">
        <span className="pve-number">{index + 1}</span>
        <span className="pve-name">{photo.name}</span>
      </header>

      <div className="pve-field pve-field--wide">
        <label className="pve-label" htmlFor={`pve-text-${index}`}>Text on this photo</label>
        <input id={`pve-text-${index}`} type="text" value={text} maxLength={40} disabled={locked}
          placeholder="No text" onChange={(e) => setText(e.target.value)} onBlur={saveText}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }} />
      </div>

      <div className="pve-row">
        <div className="pve-field">
          <label className="pve-label" htmlFor={`pve-motion-${index}`}>Text movement</label>
          <select id={`pve-motion-${index}`} value={textMotion} disabled={locked}
            onChange={(e) => onChange({ text_motion: e.target.value })}>
            {TEXT_COMES_IN.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="pve-field">
          <label className="pve-label" htmlFor={`pve-text-speed-${index}`}>Text speed</label>
          <select id={`pve-text-speed-${index}`} value={photo.text_speed || 'medium'}
            disabled={locked || textMotion === 'none'} onChange={(e) => onChange({ text_speed: e.target.value })}>
            {SPEEDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      <div className="pve-row">
        <div className="pve-field">
          <label className="pve-label" htmlFor={`pve-comes-${index}`}>Photo movement</label>
          <select id={`pve-comes-${index}`} value={comesIn} disabled={locked || index === 0}
            onChange={(e) => onChange({ transition: e.target.value })}>
            {COMES_IN.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="pve-field">
          <label className="pve-label" htmlFor={`pve-speed-${index}`}>Photo speed</label>
          <select id={`pve-speed-${index}`} value={photo.transition_speed || 'medium'}
            disabled={locked || comesIn === 'cut'} onChange={(e) => onChange({ transition_speed: e.target.value })}>
            {SPEEDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="pve-field">
          <label className="pve-label" htmlFor={`pve-frame-${index}`}>Frame</label>
          <select id={`pve-frame-${index}`} value={photo.frame || 'none'} disabled={locked}
            onChange={(e) => onChange({ frame: e.target.value })}>
            {FRAMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>
      {index === 0 && <p className="pve-hint">The first photo has nothing before it, so it cannot slide in.</p>}
    </article>
  );
}
