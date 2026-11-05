import { useEffect, useRef, useState } from 'react';
import { getJSON } from '../api.js';
import GalleryClipCard from './GalleryClipCard.jsx';
import VideoPreviewModal from './VideoPreviewModal.jsx';
import Icon from './Icon.jsx';
import { LeafTrio } from './Botanicals.jsx';
import './Gallery.css';

const DEFAULTS = { minLen: 30, maxLen: 60, count: 5, useAi: true, framing: 'crop' };

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// "https://youtu.be/abc?si=..." -> "youtu.be": enough to tell where it came from, nothing more
function sourceHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return ''; }
}

/** The regeneration controls, in a side drawer. Same settings and API call as before. */
function RegenerateDrawer({ jobId, onClose, onStarted }) {
  const [minLen, setMinLen]   = useState(DEFAULTS.minLen);
  const [maxLen, setMaxLen]   = useState(DEFAULTS.maxLen);
  const [count, setCount]     = useState(DEFAULTS.count);
  const [useAi, setUseAi]     = useState(DEFAULTS.useAi);
  const [framing, setFraming] = useState(DEFAULTS.framing);
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState('');
  const closeRef = useRef(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  async function submit() {
    setBusy(true);
    setError('');
    try {
      const params = new URLSearchParams({ min_len: minLen, max_len: maxLen, count, use_ai: useAi, framing });
      await getJSON(`/api/jobs/${jobId}/clips?${params}`, { method: 'POST' });
      onStarted();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="cg-drawer-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <aside className="cg-drawer" role="dialog" aria-modal="true" aria-labelledby="regen-title">
        <header className="cg-drawer-head">
          <div>
            <h2 id="regen-title" className="cg-heading-md">Regenerate videos</h2>
            <p className="cg-text-sm cg-text-secondary">
              Make a fresh set from the same source video. Your current videos will be replaced.
            </p>
          </div>
          <button ref={closeRef} type="button" className="cg-btn cg-btn--ghost cg-btn--sm cg-drawer-close"
            onClick={onClose} disabled={busy} aria-label="Close">✕</button>
        </header>

        <div className="cg-drawer-body">
          <div className="cg-field">
            <label className="cg-label">Number of videos</label>
            <div className="cg-number-input">
              <button type="button" onClick={() => setCount(clamp(count - 1, 1, 10))} disabled={busy || count <= 1}>−</button>
              <span>{count}</span>
              <button type="button" onClick={() => setCount(clamp(count + 1, 1, 10))} disabled={busy || count >= 10}>+</button>
            </div>
          </div>

          <div className="cg-field">
            <label className="cg-label">Length: {minLen}s – {maxLen}s</label>
            <div className="cg-gallery-range-row">
              <input className="cg-range" type="range" min="5" max="120" step="5" value={minLen} disabled={busy}
                aria-label="Shortest length"
                onChange={(e) => { const v = +e.target.value; setMinLen(v); if (v > maxLen) setMaxLen(v); }} />
              <input className="cg-range" type="range" min="5" max="180" step="5" value={maxLen} disabled={busy}
                aria-label="Longest length"
                onChange={(e) => { const v = +e.target.value; setMaxLen(v); if (v < minLen) setMinLen(v); }} />
            </div>
          </div>

          <div className="cg-field">
            <label className="cg-label" htmlFor="rr-framing">Framing</label>
            <select id="rr-framing" className="cg-select" value={framing} disabled={busy}
              onChange={(e) => setFraming(e.target.value)}>
              <option value="crop">Follow the speaker (crop)</option>
              <option value="blur">Whole picture on a blurred background</option>
            </select>
          </div>

          <label className="cg-toggle">
            <input type="checkbox" checked={useAi} disabled={busy} onChange={(e) => setUseAi(e.target.checked)} />
            <span className="cg-toggle-track" />
            <span className="cg-toggle-label">Use AI to choose the best moments</span>
          </label>

          {error && <div className="cg-alert cg-alert--error" role="alert"><span>{error}</span></div>}
        </div>

        <footer className="cg-drawer-foot">
          <button type="button" className="cg-btn cg-btn--secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="cg-btn cg-btn--primary" onClick={submit} disabled={busy}>
            {busy ? <><span className="cg-spinner" aria-hidden="true" /> Starting…</> : 'Regenerate'}
          </button>
        </footer>
      </aside>
    </div>
  );
}

export default function Gallery({
  jobId, clips, result, onClipUpdated, onEdit, onExport, onNewVideo, onRegenerated,
}) {
  const [showRegen, setShowRegen] = useState(false);
  const [previewing, setPreviewing] = useState(null);
  const hasNote = result?.note && result.note !== 'ok';
  // Where the videos came from, in plain words. The rights declaration itself is never shown here:
  // it stays stored with the project and in the export dialog's rights report.
  const source = result?.source
    ? { label: result.source.url ? 'YouTube import' : 'Uploaded video',
        host: result.source.url ? sourceHost(result.source.url) : '' }
    : null;

  return (
    <main className="cg-main cg-vg-page">
      <header className="cg-vg-header">
        <div className="cg-vg-title">
          <div className="cg-vg-title-row">
            <h1 className="cg-heading-xl">Your Videos</h1>
            <span className="cg-vg-count">{clips.length} {clips.length === 1 ? 'video' : 'videos'}</span>
          </div>
          <p className="cg-vg-subtitle">All your creations, ready to edit and export.</p>
        </div>
        <div className="cg-vg-actions">
          <button type="button" className="cg-btn cg-btn--secondary" onClick={() => setShowRegen(true)}>
            <Icon name="refresh" size={14} />
            <span>Regenerate</span>
          </button>
          <button type="button" className="cg-btn cg-btn--primary" onClick={onNewVideo}>
            <Icon name="create" size={16} stroke={2} />
            <span>Create Video</span>
          </button>
        </div>
      </header>

      {hasNote && <p className="cg-vg-note" role="status">{result.note}</p>}

      {clips.length === 0 ? (
        <div className="cg-vg-empty">
          <LeafTrio size={64} />
          <h2 className="cg-heading-sm">No videos were found</h2>
          <p className="cg-text-sm cg-text-secondary">
            Try regenerating with a shorter minimum length, or create a new video.
          </p>
          <button type="button" className="cg-btn cg-btn--secondary cg-btn--sm" onClick={() => setShowRegen(true)}>
            Regenerate
          </button>
        </div>
      ) : (
        <div className="cg-vg-grid">
          {clips.map((c) => (
            <GalleryClipCard
              key={`${c.id}-${c.version || 0}`}
              jobId={jobId}
              clip={c}
              source={source}
              onPreview={setPreviewing}
              onEdit={onEdit}
              onExport={onExport}
              onUpdated={onClipUpdated}
            />
          ))}
        </div>
      )}

      {result?.disclaimer && <p className="cg-text-xs cg-text-muted cg-gallery-disclaimer">{result.disclaimer}</p>}

      {previewing && (
        <VideoPreviewModal
          jobId={jobId}
          clip={previewing}
          onClose={() => setPreviewing(null)}
          onEdit={(c) => { setPreviewing(null); onEdit(c); }}
        />
      )}

      {showRegen && (
        <RegenerateDrawer
          jobId={jobId}
          onClose={() => setShowRegen(false)}
          onStarted={() => { setShowRegen(false); if (onRegenerated) onRegenerated(); }}
        />
      )}
    </main>
  );
}
