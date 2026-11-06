import { useEffect, useRef, useState } from 'react';
import { getJSON } from '../api.js';
import Icon from './Icon.jsx';
import { CopyEditor, ThumbnailMaker } from './ContentTools.jsx';
import { Panda, Sprig } from './Botanicals.jsx';
import './AssistantHome.css';

// Home: the creator assistant. You say what you want; it picks one of CocoGenie's real tools, shows a
// plan, and runs it with live progress. It never writes made-up answers: replies are either a tool's
// real result or a plain sentence about what it is doing (or why something isn't available yet).

const CONV_KEY = 'clipgenie.conversation';
const MODE_LABELS = { auto: 'Auto Edit', assist: 'AI + Manual', custom: 'Custom Style' };
const RIGHTS = [
  { value: 'own', label: 'I made it or own it' },
  { value: 'permission', label: "I have the owner's permission" },
  { value: 'licensed', label: 'Public domain or licensed for reuse' },
  { value: 'unsure', label: "I'm not sure", uploadOnly: true },
];
const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function StepList({ steps }) {
  return (
    <ol className="cg-as-steps">
      {steps.map((s) => (
        <li key={s.key} className={`cg-as-step cg-as-step--${s.status}`}>
          <span className="cg-as-step-mark" aria-hidden="true">
            {s.status === 'done' ? '✓' : s.status === 'running' ? <span className="cg-spinner" /> : s.status === 'error' ? '!' : s.status === 'skipped' ? '–' : ''}
          </span>
          <span className="cg-as-step-title">{s.title}</span>
          {s.detail && <span className="cg-as-step-detail">{s.detail}</span>}
          {s.status === 'skipped' && <span className="cg-as-step-detail">already done</span>}
        </li>
      ))}
    </ol>
  );
}

function PlanForm({ wf, styles, onStarted }) {
  const [count, setCount] = useState(wf.args.count);
  const [mode, setMode] = useState(wf.args.edit_mode);
  const [styleId, setStyleId] = useState(wf.args.edit_mode === 'custom' ? wf.args.style_id : 'punchy');
  const [rights, setRights] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const fromLink = wf.source.kind === 'url';

  async function act(kind) {
    setBusy(kind);
    setError('');
    try {
      const body = kind === 'start'
        ? { count, edit_mode: mode, style_id: mode === 'custom' ? styleId : 'natural', ...(wf.needs_rights ? { rights } : {}) }
        : {};
      onStarted(await getJSON(`/api/assistant/workflows/${wf.id}/${kind === 'start' ? 'confirm' : 'cancel'}`, post(body)));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="cg-as-plan">
      <div className="cg-as-plan-row">
        <label className="cg-field">
          <span className="cg-label">How many clips</span>
          <div className="cg-number-input">
            <button type="button" onClick={() => setCount(Math.max(1, count - 1))} disabled={count <= 1}>−</button>
            <span>{count}</span>
            <button type="button" onClick={() => setCount(Math.min(10, count + 1))} disabled={count >= 10}>+</button>
          </div>
        </label>
        <label className="cg-field">
          <span className="cg-label">How to edit</span>
          <select className="cg-select" value={mode} onChange={(e) => setMode(e.target.value)}>
            {Object.entries(MODE_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        {mode === 'custom' && (
          <label className="cg-field">
            <span className="cg-label">Style</span>
            <select className="cg-select" value={styleId} onChange={(e) => setStyleId(e.target.value)}>
              {styles.filter((s) => s.id !== 'natural').map((s) => <option key={s.id} value={s.id}>{s.name}{s.builtin ? '' : ' (yours)'}</option>)}
            </select>
          </label>
        )}
      </div>
      {wf.needs_rights && (
        <fieldset className="cg-as-rights">
          <legend className="cg-label">Who owns this video?</legend>
          {RIGHTS.filter((r) => !(fromLink && r.uploadOnly)).map((r) => (
            <label key={r.value} className={`cg-as-right ${rights === r.value ? 'is-on' : ''}`}>
              <input type="radio" name={`rights-${wf.id}`} value={r.value} checked={rights === r.value}
                onChange={() => setRights(r.value)} />
              {r.label}
            </label>
          ))}
        </fieldset>
      )}
      {wf.warning && <p className="cg-as-warning">{wf.warning}</p>}
      {wf.note && <p className="cg-text-xs cg-text-muted">{wf.note}</p>}
      {error && <p className="cg-text-xs cg-text-error">{error}</p>}
      <div className="cg-as-plan-actions">
        <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" disabled={!!busy || (wf.needs_rights && !rights)}
          onClick={() => act('start')}>{busy === 'start' ? 'Starting…' : 'Start'}</button>
        <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" disabled={!!busy} onClick={() => act('cancel')}>Cancel</button>
      </div>
    </div>
  );
}

function ThumbnailCard({ wf, onOpenProject }) {
  const [clipId, setClipId] = useState(null);
  const clips = wf.result.clips;
  if (clips.length === 0) return <p className="cg-text-sm cg-text-muted">This project has no clips.</p>;
  return (
    <div className="cg-as-result">
      <div className="cg-as-clips" role="radiogroup" aria-label="Clips">
        {clips.map((c) => (
          <button key={c.id} type="button" role="radio" aria-checked={clipId === c.id}
            className={`cg-as-clip ${clipId === c.id ? 'is-on' : ''}`} onClick={() => setClipId(c.id)}>
            <span className="cg-as-clip-thumb">
              <video src={`/api/jobs/${wf.job_id}/clips/${c.id}.mp4?v=${c.version}#t=0.5`} preload="metadata" muted playsInline tabIndex={-1} />
            </span>
            <span className="cg-as-clip-title">{c.title}</span>
          </button>
        ))}
      </div>
      {clipId !== null && <ThumbnailMaker key={clipId} jobId={wf.job_id} clipId={clipId} />}
      <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={() => onOpenProject(wf.job_id)}>Open the project</button>
    </div>
  );
}

function ScriptCard({ wf }) {
  const [copied, setCopied] = useState(false);
  const r = wf.result;
  const text = [`Hook: ${r.hook}`, ...r.points.map((p, i) => `${i + 1}. ${p}`), r.closing && `Closing: ${r.closing}`]
    .filter(Boolean).join('\n');
  async function copy() {
    try {
      await navigator.clipboard.writeText(`${r.idea.title}\n\n${text}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch { /* the text stays on screen to copy by hand */ }
  }
  return (
    <div className="cg-as-result cg-as-script">
      <p className="cg-as-draft-label">Draft outline · {r.idea.title}</p>
      <p className="cg-text-sm"><strong>Hook:</strong> {r.hook}</p>
      <ol className="cg-as-script-points">{r.points.map((p) => <li key={p} className="cg-text-sm">{p}</li>)}</ol>
      {r.closing && <p className="cg-text-sm"><strong>Closing:</strong> {r.closing}</p>}
      <p className="cg-text-xs cg-text-muted">{r.note}</p>
      <div><button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={copy}>{copied ? '✓ Copied' : 'Copy outline'}</button></div>
    </div>
  );
}

function IdeaScriptButton({ wfId, index, onConversation }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function go() {
    setBusy(true);
    setError('');
    try {
      const out = await getJSON(`/api/assistant/workflows/${wfId}/script`, post({ index }));
      onConversation(out.conversation);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="cg-as-idea-actions">
      <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" disabled={busy} onClick={go}>
        {busy ? 'Starting…' : 'Draft a script'}
      </button>
      {error && <span className="cg-text-xs cg-text-error">{error}</span>}
    </span>
  );
}

function WorkflowCard({ id, styles, onOpenProject, onConversation }) {
  const [wf, setWf] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getJSON(`/api/assistant/workflows/${id}`).then((data) => { if (!cancelled) setWf(data); }).catch(() => {});
    return () => { cancelled = true; };
  }, [id]);

  if (!wf) return null;
  const restart = (data) => setWf(data);     // after Start, keep following
  const clips = wf.result?.clips || [];
  const project = wf.result?.project;

  return (
    <div className={`cg-as-card cg-as-card--${wf.status}`}>
      {wf.status === 'awaiting_confirmation' && <PlanForm wf={wf} styles={styles} onStarted={restart} />}
      {wf.status === 'cancelled' && <p className="cg-text-sm cg-text-muted">Cancelled. Nothing was started.</p>}
      {(wf.status === 'running' || wf.status === 'done' || wf.status === 'error') && <StepList steps={wf.steps} />}
      {wf.status === 'running' && <FollowWhileRunning id={wf.id} onUpdate={setWf} />}
      {wf.status === 'error' && <p className="cg-as-error">{wf.error}</p>}

      {wf.status === 'done' && wf.tool === 'make_clips' && (
        <div className="cg-as-result">
          <div className="cg-as-clips">
            {clips.map((c) => (
              <button key={c.id} type="button" className="cg-as-clip" onClick={() => onOpenProject(wf.job_id)}
                aria-label={`Open ${c.title}`}>
                <span className="cg-as-clip-thumb">
                  <video src={`/api/jobs/${wf.job_id}/clips/${c.id}.mp4?v=${c.version}#t=0.5`} preload="metadata" muted playsInline tabIndex={-1} />
                </span>
                <span className="cg-as-clip-title">{c.title}</span>
                <span className="cg-as-clip-meta">{Math.round(c.duration || 0)}s{c.needs_decision ? ' · needs your choice' : ''}</span>
              </button>
            ))}
          </div>
          {clips.length === 0 && <p className="cg-text-sm cg-text-muted">No clips came out of this video.</p>}
          <button type="button" className="cg-btn cg-btn--primary cg-btn--sm" onClick={() => onOpenProject(wf.job_id)}>
            Open {project?.title ? `“${project.title}”` : 'the videos'}
          </button>
        </div>
      )}

      {wf.status === 'done' && wf.tool === 'video_ideas' && (
        <div className="cg-as-result">
          <ol className="cg-as-ideas">
            {wf.result.ideas.map((idea, index) => (
              <li key={idea.title}>
                <p className="cg-as-idea-title">{idea.title}</p>
                <p className="cg-text-sm">{idea.angle}</p>
                {idea.why && <p className="cg-text-xs cg-text-muted">{idea.why}</p>}
                <p className="cg-as-idea-quote">From what you said: “{idea.based_on}”</p>
                <IdeaScriptButton wfId={wf.id} index={index} onConversation={onConversation} />
              </li>
            ))}
          </ol>
          <p className="cg-text-xs cg-text-muted">{wf.result.note}</p>
        </div>
      )}

      {wf.status === 'done' && wf.tool === 'create_thumbnail' && <ThumbnailCard wf={wf} onOpenProject={onOpenProject} />}

      {wf.status === 'done' && wf.tool === 'write_copy' && (
        <div className="cg-as-result">
          {wf.result.drafts.map((d) => (
            <div key={d.id} className="cg-as-copy">
              <p className="cg-as-draft-label">Clip {d.id}</p>
              <CopyEditor jobId={wf.job_id} clipId={d.id} compact />
            </div>
          ))}
          <p className="cg-text-xs cg-text-muted">{wf.result.note}</p>
        </div>
      )}

      {wf.status === 'done' && wf.tool === 'script_outline' && <ScriptCard wf={wf} />}
    </div>
  );
}

// while a card is running it re-reads itself every 1.5 s, and stops as soon as it ends
function FollowWhileRunning({ id, onUpdate }) {
  useEffect(() => {
    const timer = setInterval(() => {
      getJSON(`/api/assistant/workflows/${id}`).then(onUpdate).catch(() => {});
    }, 1500);
    return () => clearInterval(timer);
  }, [id, onUpdate]);
  return null;
}

export default function AssistantHome({ health, onOpenProject, onStartCreate }) {
  const [tools, setTools] = useState([]);
  const [styles, setStyles] = useState([]);
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [conv, setConv] = useState(null);
  const [text, setText] = useState('');
  const [attachment, setAttachment] = useState(null);     // {job_id, filename} or {uploading: name}
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);
  const inputRef = useRef(null);
  const endRef = useRef(null);
  const serverDown = health?.status === 'down';

  useEffect(() => {
    getJSON('/api/assistant/tools').then((d) => setTools(d.tools)).catch(() => {});
    getJSON('/api/styles').then((d) => setStyles(d.styles)).catch(() => {});
    getJSON('/api/projects').then((d) => setProjects(d.projects)).catch(() => {}).finally(() => setProjectsLoaded(true));
    let saved = null;
    try { saved = localStorage.getItem(CONV_KEY); } catch { /* ignore */ }
    if (saved) getJSON(`/api/assistant/conversations/${saved}`).then(setConv).catch(() => {});
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'nearest' }); }, [conv?.messages?.length]);

  async function send(message) {
    const words = (message ?? text).trim();
    if (!words || sending) return;
    setSending(true);
    setError('');
    try {
      const out = await getJSON('/api/assistant/messages', post({
        text: words, conversation_id: conv?.id || null,
        attachment_job_id: attachment?.job_id || null,
      }));
      setConv(out.conversation);
      try { localStorage.setItem(CONV_KEY, out.conversation.id); } catch { /* ignore */ }
      setText('');
      if (out.workflow) setAttachment(null);          // the plan now holds the video
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }

  async function attach(file) {
    if (!file) return;
    setError('');
    setAttachment({ uploading: file.name });
    try {
      const form = new FormData();
      form.append('file', file);
      setAttachment(await getJSON('/api/assistant/upload', { method: 'POST', body: form }));
      inputRef.current?.focus();
    } catch (e) {
      setAttachment(null);
      setError(e.message);
    }
  }

  function shortcut(tool) {
    if (!tool.available) return;
    if (tool.name === 'make_clips') {          // needs a video: start the sentence, the user adds the video
      setText((t) => t || 'Make 5 Shorts from ');
      inputRef.current?.focus();
    } else {
      send(tool.example);
    }
  }

  function newChat() {
    setConv(null);
    try { localStorage.removeItem(CONV_KEY); } catch { /* ignore */ }
  }

  const messages = conv?.messages || [];

  return (
    <main className="cg-main cg-as-page">
      <section className="cg-as-hero">
        <div className="cg-as-hero-text">
          <p className="cg-dash-eyebrow">CocoGenie assistant</p>
          <h1 className="cg-heading-xl">What would you like to create today?</h1>
        </div>
        <div className="cg-as-hero-art" aria-hidden="true"><Panda width={92} pose="waving" /><Sprig width={110} tone="leaf" /></div>
      </section>

      {serverDown && (
        <div className="cg-alert cg-alert--error" role="alert">
          <span>CocoGenie can't reach its server. Start it with <code className="cg-code">./run.sh</code> and refresh this page.</span>
        </div>
      )}

      {messages.length > 0 && (
        <section className="cg-as-thread" aria-live="polite">
          <div className="cg-as-thread-head">
            <span className="cg-text-xs cg-text-muted">This conversation</span>
            <button type="button" className="cg-btn cg-btn--ghost cg-btn--sm" onClick={newChat}>New chat</button>
          </div>
          {messages.map((m, i) => (
            <div key={i} className={`cg-as-msg cg-as-msg--${m.role}`}>
              <p className="cg-as-bubble">{m.text}</p>
              {m.workflow_id && <WorkflowCard id={m.workflow_id} styles={styles} onOpenProject={onOpenProject} onConversation={setConv} />}
            </div>
          ))}
          <div ref={endRef} />
        </section>
      )}

      {health?.system?.messages?.length > 0 && (
        <div className={`cg-alert ${health.system.level === 'block' ? 'cg-alert--error' : 'cg-alert--warn'}`} role="status">
          <span>{health.system.messages[0]}</span>
        </div>
      )}

      <section className="cg-as-paths" aria-label="Choose how to start">
        <button type="button" className="cg-as-path cg-as-path--own" disabled={serverDown}
          onClick={() => onStartCreate?.('file')}>
          <span className="cg-as-path-icon"><Icon name="upload" size={20} /></span>
          <span className="cg-as-path-body">
            <span className="cg-as-path-title">Create Shorts from my videos</span>
            <span className="cg-as-path-text">Upload an MP4 you made. CocoGenie finds the best moments and adds captions.</span>
          </span>
          <Icon name="arrow" size={16} />
        </button>
        <button type="button" className="cg-as-path cg-as-path--repurpose" disabled={serverDown}
          onClick={() => onStartCreate?.('url')}>
          <span className="cg-as-path-icon"><Icon name="link" size={20} /></span>
          <span className="cg-as-path-body">
            <span className="cg-as-path-title">Repurpose a video from another creator</span>
            <span className="cg-as-path-text">Paste a YouTube link. You confirm you have permission to reuse it before any clips are made.</span>
          </span>
          <Icon name="arrow" size={16} />
        </button>
      </section>

      <form className="cg-as-composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        {attachment && (
          <div className="cg-as-attachment">
            <Icon name="videos" size={14} />
            <span>{attachment.uploading ? `Uploading ${attachment.uploading}…` : attachment.filename}</span>
            {!attachment.uploading && (
              <button type="button" className="cg-as-attachment-x" onClick={() => setAttachment(null)} aria-label="Remove the video">✕</button>
            )}
          </div>
        )}
        <div className="cg-as-input-row">
          <button type="button" className="cg-as-attach" onClick={() => fileRef.current?.click()} disabled={serverDown || !!attachment?.uploading}
            title="Attach a video (MP4)" aria-label="Attach a video">
            <Icon name="upload" size={18} />
          </button>
          <input ref={fileRef} type="file" accept="video/mp4" hidden onChange={(e) => { attach(e.target.files[0]); e.target.value = ''; }} />
          <input ref={inputRef} className="cg-as-input" value={text} disabled={serverDown}
            placeholder="Describe what you want, or paste a YouTube link…"
            onChange={(e) => setText(e.target.value)} maxLength={2000} aria-label="Message" />
          <button type="submit" className="cg-btn cg-btn--primary" disabled={!text.trim() || sending || serverDown || !!attachment?.uploading}>
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
        {error && <p className="cg-text-xs cg-text-error">{error}</p>}
      </form>

      <div className="cg-as-chips" role="list">
        {tools.map((t) => (
          <button key={t.name} type="button" role="listitem" className={`cg-as-chip ${t.available ? '' : 'is-soon'}`}
            disabled={!t.available || serverDown} title={t.available ? t.description : t.reason} onClick={() => shortcut(t)}>
            {t.title}
            {!t.available && <span className="cg-as-soon">Soon</span>}
          </button>
        ))}
      </div>

      {projectsLoaded && projects.length === 0 && (
        <div className="cg-as-empty">
          <Panda width={88} />
          <p className="cg-as-empty-title">Your finished Shorts will appear here</p>
          <p className="cg-as-empty-text">Start with one of the two paths above. It takes a few minutes.</p>
        </div>
      )}

      {projects.length > 0 && (
        <section>
          <h2 className="cg-dash-section-title">Recent projects</h2>
          <div className="cg-as-projects">
            {projects.slice(0, 6).map((p) => (
              <button key={p.job_id} type="button" className="cg-as-project" onClick={() => onOpenProject(p.job_id)}>
                <span className="cg-as-project-thumb">
                  {p.first_clip && (
                    <video src={`/api/jobs/${p.job_id}/clips/${p.first_clip.id}.mp4?v=${p.first_clip.version}#t=0.5`}
                      preload="metadata" muted playsInline tabIndex={-1} />
                  )}
                </span>
                <span className="cg-as-project-body">
                  <span className="cg-as-project-title">{p.title}</span>
                  <span className="cg-as-project-meta">
                    {p.clips ? `${p.clips} video${p.clips === 1 ? '' : 's'}` : p.status === 'done' ? 'No videos'
                      : p.status === 'waiting' ? 'Not started' : p.status === 'error' ? 'Stopped' : 'In progress'}
                    {' · '}{new Date(p.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
