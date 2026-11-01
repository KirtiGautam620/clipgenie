import React, { useRef, useState } from 'react';
import { getJSON } from '../api.js';
import StoryboardAnimatic from './StoryboardAnimatic.jsx';
import { copyText } from '../copy.js';
import StoryboardSceneCard from './StoryboardSceneCard.jsx';

const strip = (sb) => { const { geometry, blockers, ...rest } = sb; return rest; }; // eslint-disable-line no-unused-vars
const blockersOf = (d) => [
  ...(d.rights === 'unsure' ? ['Confirm that you have the right to use this photo.'] : []),
  ...(d.people === 'no_consent' ? ['The people in this photo have not agreed to appear in a video.'] : []),
];

export default function StoryboardEditor({ storyboard, options, onSaved, onBack, onDelete }) {
  const [saved, setSaved] = useState(storyboard);                  // as the server has it
  const [draft, setDraft] = useState(strip(storyboard));
  const [geometry, setGeometry] = useState(storyboard.geometry);
  const [selected, setSelected] = useState(storyboard.scenes[0]?.id);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [replan, setReplan] = useState(null);                       // the "new plan" form, when open
  const photoRef = useRef(null);

  const dirty = JSON.stringify(draft) !== JSON.stringify(strip(saved));
  const blockers = blockersOf(draft);
  const base = `/api/storyboards/${draft.id}`;
  const sceneIndex = draft.scenes.findIndex((s) => s.id === selected);

  const apply = (sb) => {
    setSaved(sb);
    setDraft(strip(sb));
    setGeometry(sb.geometry);
    onSaved(sb);
  };
  const flash = (key) => { setCopied(key); setTimeout(() => setCopied(''), 1500); };

  async function save() {
    setBusy('save');
    setError('');
    try {
      const sb = await getJSON(base, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft) });
      apply(sb);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy('');
    }
  }
  const ensureSaved = async () => (dirty ? save() : true);

  const setScenes = (fn) => setDraft((d) => ({ ...d, scenes: fn(d.scenes) }));
  const setScene = (id, patch) => setScenes((list) => list.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  const nextId = () => {
    const used = new Set(draft.scenes.map((s) => s.id));
    let n = 1;
    while (used.has(`s${n}`)) n += 1;
    return `s${n}`;
  };

  function move(id, dir) {
    setScenes((list) => {
      const i = list.findIndex((s) => s.id === id);
      const j = i + dir;
      if (j < 0 || j >= list.length) return list;
      const copy = [...list];
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  }
  function duplicate(id) {
    const id2 = nextId();
    setScenes((list) => {
      const i = list.findIndex((s) => s.id === id);
      const copy = { ...list[i], id: id2, title: `${list[i].title} (copy)`.slice(0, 60), focus: [...list[i].focus] };
      return [...list.slice(0, i + 1), copy, ...list.slice(i + 1)];
    });
    setGeometry((g) => ({ ...g, [id2]: g[id] }));
    setSelected(id2);
  }
  function remove(id) {
    setScenes((list) => list.filter((s) => s.id !== id));
    if (selected === id) setSelected(draft.scenes.find((s) => s.id !== id)?.id);
  }

  async function rebuild(scene) {
    setError('');
    try {
      const { prompt } = await getJSON(`${base}/compose-prompt`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera: scene.camera, detail: scene.detail, duration: scene.duration,
          product: draft.product, style: draft.style, aspect: draft.aspect }) });
      setScene(scene.id, { prompt });
      return prompt;
    } catch (e) {
      setError(e.message);
      return null;
    }
  }

  async function addScene(shotId) {
    const shot = options.shots.find((s) => s.id === shotId);
    const last = draft.scenes[draft.scenes.length - 1];
    const scene = {
      id: nextId(), title: shot ? shot.label : 'New scene', shot: shot ? shot.id : 'custom',
      camera: shot ? shot.camera : '', detail: shot ? shot.detail : '', prompt: '',
      duration: shot ? shot.duration : 3, zoom: shot ? shot.zoom : 1.2, focus: shot ? [...shot.focus] : [0.5, 0.5],
      motion: shot ? shot.motion : 'hold', intensity: shot ? shot.intensity : 0.5,
      transition: last ? last.transition : 'fade', transition_seconds: last ? last.transition_seconds : 0.6,
    };
    setScenes((list) => [...list, scene]);
    setSelected(scene.id);
    if (shot) await rebuild(scene);
  }

  function setFocus(e) {
    const scene = draft.scenes[sceneIndex];
    if (!scene || !photoRef.current) return;
    const rect = photoRef.current.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const fy = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
    setScene(scene.id, { focus: [Math.round(fx * 1000) / 1000, Math.round(fy * 1000) / 1000] });
  }

  async function fetchOrFail(url) {
    const res = await fetch(url);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    return res;
  }
  async function copyAll() {
    setError('');
    if (!(await ensureSaved())) return;
    try {
      const text = await (await fetchOrFail(`${base}/prompts.txt`)).text();
      if (await copyText(text)) flash('all');
      else setError('The browser would not let ClipGenie copy. Download the package instead.');
    } catch (e) {
      setError(e.message);
    }
  }
  async function download() {
    setError('');
    if (!(await ensureSaved())) return;
    try {
      const blob = await (await fetchOrFail(`${base}/package.zip`)).blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `storyboard_${draft.id}.zip`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      setError(e.message);
    }
  }
  async function copyScene(scene) {
    if (await copyText(scene.prompt)) flash(scene.id);
    else setError('The browser would not let ClipGenie copy. Select the prompt text and copy it by hand.');
  }

  async function newPlan() {
    if (!window.confirm('Build a new plan? This replaces every scene, including any edits you made.')) return;
    setBusy('plan');
    setError('');
    try {
      const sb = await getJSON(`${base}/plan`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(replan) });
      apply(sb);
      setSelected(sb.scenes[0]?.id);
      setReplan(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  const notes = draft.plan?.notes || [];
  const understood = draft.plan?.understood || {};
  const locked = blockers.length > 0;

  return (
    <div className="cg-sb-editor">
      <header className="cg-sb-top">
        <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={onBack}>← Storyboards</button>
        <input className="cg-input cg-sb-name" value={draft.title} maxLength={80} aria-label="Storyboard title"
          onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
        <span className="cg-badge cg-badge--muted">{draft.aspect}</span>
        <span className="cg-badge cg-badge--muted">{draft.scenes.length} scenes</span>
        {dirty && <span className="cg-badge cg-badge--warning">Unsaved changes</span>}
        <div className="cg-sb-top-actions">
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={!dirty || busy === 'save'} onClick={save}>
            {busy === 'save' ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={locked} onClick={copyAll}>
            {copied === 'all' ? '✓ Copied' : 'Copy all prompts'}
          </button>
          <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={locked} onClick={download}>
            Download package
          </button>
          <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={onDelete}>Delete</button>
        </div>
      </header>

      <p className="cg-sb-banner" role="note">
        This is a <strong>shot plan built from templates and your prompt</strong>. The preview frames are crops of
        your own photo: they show framing and zoom, not new camera angles, and nothing here is AI-generated.
        The prompts are for you to use in an external video tool.
      </p>
      {locked && (
        <div className="cg-alert cg-alert--warn" role="alert">
          <span className="cg-alert-icon">⚠️</span>
          <span>Copying and downloading are locked. {blockers.join(' ')}</span>
        </div>
      )}
      {error && <p className="cg-caption-error" role="alert">{error}</p>}

      <div className="cg-sb-layout">
        <aside className="cg-sb-side">
          <div className="cg-card cg-sb-photo">
            <p className="cg-sb-caption">Your photo{sceneIndex >= 0 ? `: scene ${sceneIndex + 1} selected` : ''}</p>
            <div className="cg-sb-photo-wrap" onClick={setFocus}>
              <img ref={photoRef} src={`${base}/photo.jpg?v=${saved.updated}`} alt="Your photo" draggable={false} />
              {draft.scenes.map((s, i) => {
                const g = geometry[s.id];
                if (!g) return null;
                const [l, t, r, b] = g.start;
                return (
                  <span key={s.id} className={`cg-sb-box ${s.id === selected ? 'selected' : ''}`}
                    style={{ left: `${l * 100}%`, top: `${t * 100}%`, width: `${(r - l) * 100}%`, height: `${(b - t) * 100}%` }}>
                    <span className="cg-sb-box-num">{i + 1}</span>
                  </span>
                );
              })}
            </div>
            <div className="cg-sb-chipbar" role="tablist" aria-label="Scenes">
              {draft.scenes.map((s, i) => (
                <button key={s.id} type="button" role="tab" aria-selected={s.id === selected}
                  className={`cg-sb-chip ${s.id === selected ? 'active' : ''}`} onClick={() => setSelected(s.id)}>{i + 1}</button>
              ))}
            </div>
            <p className="cg-text-xs cg-text-muted">The boxes show where each scene starts. Click the photo to move the selected scene.</p>
          </div>

          <div className="cg-card cg-sb-rights">
            <h2 className="cg-heading-sm">About this photo</h2>
            <label className="cg-sb-ctl">Right to use it
              <select className="cg-select" value={draft.rights} onChange={(e) => setDraft({ ...draft, rights: e.target.value })}>
                {options.rights.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </label>
            <label className="cg-sb-ctl">People in it
              <select className="cg-select" value={draft.people} onChange={(e) => setDraft({ ...draft, people: e.target.value })}>
                {options.people.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </label>
          </div>

          <StoryboardAnimatic storyboardId={draft.id} blockers={blockers} ensureSaved={ensureSaved} savedAt={saved.updated}
            music={draft.music || { track_id: null, volume: 0.7 }} onMusic={(m) => setDraft({ ...draft, music: m })} />

          <div className="cg-card">
            <h2 className="cg-heading-sm">What was found in your prompt</h2>
            <ul className="cg-sb-found">
              <li>Style: <strong>{understood.style || 'none'}</strong></li>
              <li>Shots asked for: {understood.shots?.length ? understood.shots.join(', ') : 'none (default shot list used)'}</li>
              <li>Scenes: {understood.scenes}{understood.seconds ? `, ${understood.seconds} s in total` : ''}</li>
              {notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
            <p className="cg-text-xs cg-text-muted">This reads keywords. It does not look at your photo.</p>
            {replan ? (
              <div className="cg-sb-replan">
                <textarea className="cg-input" rows={3} value={replan.prompt} maxLength={options.limits.prompt}
                  aria-label="New prompt" onChange={(e) => setReplan({ ...replan, prompt: e.target.value })} />
                <input className="cg-input" value={replan.product} maxLength={200} aria-label="What is in the photo"
                  placeholder="What is in the photo?" onChange={(e) => setReplan({ ...replan, product: e.target.value })} />
                <div className="cg-sb-row">
                  <select className="cg-select" value={replan.style} aria-label="Style" onChange={(e) => setReplan({ ...replan, style: e.target.value })}>
                    <option value="">Style from prompt</option>
                    {options.styles.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                  </select>
                  <select className="cg-select" value={replan.count} aria-label="Scenes" onChange={(e) => setReplan({ ...replan, count: e.target.value })}>
                    <option value="">Scenes from prompt</option>
                    {Array.from({ length: options.limits.scenes[1] - options.limits.scenes[0] + 1 }, (_, i) => options.limits.scenes[0] + i)
                      .map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
                <div className="cg-caption-actions">
                  <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={busy === 'plan'} onClick={newPlan}>
                    {busy === 'plan' ? 'Planning…' : 'Build a new plan'}
                  </button>
                  <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={() => setReplan(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm"
                onClick={() => setReplan({ prompt: draft.prompt, product: draft.product, style: '', count: '', aspect: draft.aspect })}>
                Build a new plan from a different prompt…
              </button>
            )}
          </div>
        </aside>

        <section className="cg-sb-scenes" aria-label="Scenes">
          {draft.scenes.map((scene, i) => (
            <StoryboardSceneCard
              key={scene.id} storyboardId={draft.id} scene={scene} index={i} total={draft.scenes.length}
              selected={scene.id === selected} geometry={geometry[scene.id]} aspect={draft.aspect} options={options}
              copied={copied === scene.id} onSelect={() => setSelected(scene.id)}
              onChange={(patch) => setScene(scene.id, patch)} onMove={(dir) => move(scene.id, dir)}
              onDuplicate={() => duplicate(scene.id)} onRemove={() => remove(scene.id)}
              onRebuildPrompt={() => rebuild(scene)} onCopy={() => copyScene(scene)}
              onGeometry={(id, g) => setGeometry((cur) => ({ ...cur, [id]: g }))}
            />
          ))}
          <div className="cg-card cg-sb-add">
            <label className="cg-sb-ctl">Add a scene
              <select className="cg-select" value="" disabled={draft.scenes.length >= options.limits.saved_scenes[1]}
                onChange={(e) => e.target.value && addScene(e.target.value)} aria-label="Add a scene">
                <option value="">Choose a shot…</option>
                {options.shots.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                <option value="custom">Blank scene (write your own)</option>
              </select>
            </label>
          </div>
        </section>
      </div>
    </div>
  );
}
