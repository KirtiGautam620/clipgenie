import { useEffect, useState } from 'react';
import { getJSON } from '../api.js';
import { isCut, outputLength, sourceToOut } from '../studioTracks.js';

const round1 = (n) => Math.round(n * 10) / 10;
const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}.${Math.floor((t % 1) * 10)}`;

const MODE_LABELS = { auto: 'Auto Edit', assist: 'AI + Manual', custom: 'Custom Style' };

// "AI edit": what CocoGenie decided for this video, and a way to change or undo each decision.
// Nothing here is a separate editor: every button changes the video's manifest on the server and the
// server remakes only what changed.
export default function EditDecisionsPanel({ jobId, clip, man, onApplied, onOpenText }) {
  const [styles, setStyles] = useState([]);
  const [styleId, setStyleId] = useState('');
  const [saveName, setSaveName] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [note, setNote] = useState('');

  const edit = clip.edit || {};
  const hook = clip.text?.hook;

  useEffect(() => {
    getJSON('/api/styles').then((d) => {
      setStyles(d.styles);
      setStyleId((current) => current || edit.style_id || d.default);
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setError(''); setNote(''); }, [clip.id, clip.version]);

  async function call(label, url, options, after) {
    setBusy(label);
    setError('');
    setNote('');
    try {
      const result = await getJSON(url, options);
      if (after) after(result);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy('');
    }
  }

  const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

  // Each removed stretch is the gap between two kept parts. Putting it back joins the two parts.
  const gaps = man ? man.segments.slice(0, -1).map((seg, i) => ({
    index: i,
    removed: man.segments[i + 1].start - seg.end,
    at: sourceToOut(man, seg.end),
  })) : [];

  function putBack(index) {
    const parts = man.segments;
    const joined = [...parts.slice(0, index), { start: parts[index].start, end: parts[index + 1].end }, ...parts.slice(index + 2)];
    const doc = { ...man, segments: joined };
    call(`gap-${index}`, `/api/jobs/${jobId}/clips/${clip.id}/manifest`,
      { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(doc) }, onApplied);
  }

  function applyStyle() {
    call('style', `/api/jobs/${jobId}/clips/${clip.id}/style`, post({ style_id: styleId }), (updated) => {
      onApplied(updated);
      const skipped = updated.edit?.skipped || [];
      if (skipped.length) setNote(`Done, except: ${skipped.join('; ')}.`);
    });
  }

  function saveStyle() {
    call('save', '/api/styles', post({ name: saveName.trim(), job_id: jobId, clip_id: clip.id }), (saved) => {
      setStyles((list) => [...list, saved]);
      setStyleId(saved.id);
      setSaveName('');
      setNote(`Saved "${saved.name}". You can choose it when you create a video, or apply it to another video.`);
    });
  }

  function reset() {
    if (!window.confirm("Go back to CocoGenie's own edit of this video? Your changes to the cuts, trim, motion, fades, music and caption words are undone. Your caption look and any headline or hook stay.")) return;
    call('reset', `/api/jobs/${jobId}/clips/${clip.id}/reset`, { method: 'POST' }, onApplied);
  }

  return (
    <div className="cg-panel-content">
      <div className="cg-panel-header">
        <h3 className="cg-heading-sm">AI edit</h3>
        {edit.mode && <span className="cg-badge cg-badge--muted">{MODE_LABELS[edit.mode] || edit.mode}</span>}
      </div>
      <p className="cg-text-xs cg-text-muted">
        What CocoGenie decided for this video. Change any of it, or leave it as it is: editing by hand is optional.
        {edit.style_name ? ` Edited in the “${edit.style_name}” style.` : ''}
      </p>

      <h4 className="cg-panel-subhead">Pauses</h4>
      {man && isCut(man) ? (
        <ul className="cg-decision-list">
          {gaps.map((g) => (
            <li key={g.index}>
              <span>
                {round1(g.removed)}s removed at {clock(g.at ?? 0)}
              </span>
              <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={!!busy}
                onClick={() => putBack(g.index)}>
                {busy === `gap-${g.index}` ? 'Putting back…' : 'Put it back'}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="cg-text-xs cg-text-muted">
          No long pauses were removed from this video{man ? ` (${round1(outputLength(man))}s, as spoken)` : ''}.
        </p>
      )}

      {hook && !hook.approved && (
        <>
          <h4 className="cg-panel-subhead">Hook</h4>
          <p className="cg-text-xs cg-text-muted">
            A hook line is waiting for your approval: “{hook.text}”. It is not on the video yet.
          </p>
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={onOpenText}>Review the hook</button>
        </>
      )}

      <h4 className="cg-panel-subhead">Editing style</h4>
      <label className="cg-field">
        <span className="cg-text-sm">Make this video follow a style</span>
        <select className="cg-select" value={styleId} disabled={!!busy} onChange={(e) => setStyleId(e.target.value)}>
          {styles.map((s) => <option key={s.id} value={s.id}>{s.name}{s.builtin ? '' : ' (yours)'}</option>)}
        </select>
      </label>
      {styles.find((s) => s.id === styleId)?.description && (
        <p className="cg-text-xs cg-text-muted">{styles.find((s) => s.id === styleId).description}</p>
      )}
      <p className="cg-text-xs cg-text-muted">
        Changes its framing, motion, fades, caption look, music level and how long pauses may be. The words
        and any headline or hook you wrote stay.
      </p>
      <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={!styleId || !!busy} onClick={applyStyle}>
        {busy === 'style' ? 'Applying…' : 'Apply style'}
      </button>

      <h4 className="cg-panel-subhead">Keep this look</h4>
      <label className="cg-field">
        <span className="cg-text-sm">Save how this video is edited as a style</span>
        <input className="cg-input" value={saveName} maxLength={40} placeholder="e.g. My intro look" disabled={!!busy}
          onChange={(e) => setSaveName(e.target.value)} />
      </label>
      <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={!saveName.trim() || !!busy} onClick={saveStyle}>
        {busy === 'save' ? 'Saving…' : 'Save style'}
      </button>

      <h4 className="cg-panel-subhead">Start over</h4>
      <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={!!busy} onClick={reset}>
        {busy === 'reset' ? 'Going back…' : "Go back to CocoGenie's edit"}
      </button>

      {note && <p className="cg-text-xs cg-text-muted">{note}</p>}
      {error && <p className="cg-text-xs cg-text-error">{error}</p>}
      <p className="cg-text-xs cg-text-muted">Any change remakes the video and needs its checklist confirmed again.</p>
    </div>
  );
}
