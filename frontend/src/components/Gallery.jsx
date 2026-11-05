import { useState } from 'react';
import { getJSON } from '../api.js';
import GalleryClipCard from './GalleryClipCard.jsx';
import MusicLibraryPanel from './MusicLibraryPanel.jsx';
import { LeafTrio } from './Botanicals.jsx';
import './Gallery.css';

const DEFAULTS = { minLen: 30, maxLen: 60, count: 5, useAi: true, framing: 'crop' };

export default function Gallery({
  jobId, clips, result, library, onClipUpdated, onEdit, onExport, onNewVideo, onLibraryChange
}) {
  const [minLen, setMinLen]     = useState(DEFAULTS.minLen);
  const [maxLen, setMaxLen]     = useState(DEFAULTS.maxLen);
  const [count, setCount]       = useState(DEFAULTS.count);
  const [useAi, setUseAi]       = useState(DEFAULTS.useAi);
  const [framing, setFraming]   = useState(DEFAULTS.framing);
  const [rerunning, setRerunning] = useState(false);
  const [rerunErr, setRerunErr]   = useState('');
  const [showMusic, setShowMusic] = useState(false);

  async function handleRerun() {
    setRerunning(true);
    setRerunErr('');
    try {
      const params = new URLSearchParams({ min_len: minLen, max_len: maxLen, count, use_ai: useAi, framing });
      await getJSON(`/api/jobs/${jobId}/clips?${params}`, { method: 'POST' });
      // Parent watches job status and will update when done
    } catch (e) {
      setRerunErr(e.message);
    }
    setRerunning(false);
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  const hasNote = result?.note && result.note !== 'ok';

  return (
    <main className="cg-main cg-gallery-page">
      <div className="cg-section-header">
        <div>
          <h1 className="cg-heading-md">
            Your Clips
            <span className="cg-badge cg-badge--muted" style={{ marginLeft: 8, verticalAlign: 'middle', fontSize: '0.8rem' }}>
              {clips.length}
            </span>
          </h1>
          {result?.source && (
            <p className="cg-text-sm cg-text-secondary" style={{ marginTop: 4 }}>
              Source: {result.source.rights_label}
              {result.source.url && <> · <a href={result.source.url} target="_blank" rel="noreferrer" className="cg-text-secondary">{result.source.url}</a></>}
            </p>
          )}
        </div>
        <button className="cg-btn cg-btn--ghost cg-btn--sm" onClick={onNewVideo}>
          + New video
        </button>
      </div>

      {hasNote && (
        <div className="cg-alert cg-alert--info" style={{ marginBottom: 'var(--cg-space-5)' }} role="status">
          <span>{result.note}</span>
        </div>
      )}

      <div className="cg-two-panel cg-gallery-layout">
        {/* Sidebar */}
        <aside className="cg-gallery-sidebar">
          <div className="cg-card cg-gallery-sidebar-card">
            <h2 className="cg-heading-sm cg-gallery-sidebar-title">Regenerate Clips</h2>
            <p className="cg-text-sm cg-text-muted">Re-run on the same video with different settings.</p>

            <div className="cg-field">
              <label className="cg-label">Number of clips</label>
              <div className="cg-number-input">
                <button type="button" onClick={() => setCount(clamp(count - 1, 1, 10))} disabled={rerunning || count <= 1}>−</button>
                <span>{count}</span>
                <button type="button" onClick={() => setCount(clamp(count + 1, 1, 10))} disabled={rerunning || count >= 10}>+</button>
              </div>
            </div>

            <div className="cg-field">
              <label className="cg-label">Clip length: {minLen}s – {maxLen}s</label>
              <div className="cg-gallery-range-row">
                <input className="cg-range" type="range" min="5" max="120" step="5"
                  value={minLen} disabled={rerunning}
                  onChange={(e) => { const v = +e.target.value; setMinLen(v); if (v > maxLen) setMaxLen(v); }}
                />
                <input className="cg-range" type="range" min="5" max="180" step="5"
                  value={maxLen} disabled={rerunning}
                  onChange={(e) => { const v = +e.target.value; setMaxLen(v); if (v < minLen) setMinLen(v); }}
                />
              </div>
            </div>

            <div className="cg-field">
              <label className="cg-label" htmlFor="rr-framing">Framing</label>
              <select id="rr-framing" className="cg-select" value={framing}
                onChange={(e) => setFraming(e.target.value)} disabled={rerunning}>
                <option value="crop">Crop (fast)</option>
                <option value="blur">Blur background</option>
              </select>
            </div>

            <label className="cg-toggle">
              <input type="checkbox" checked={useAi} disabled={rerunning}
                onChange={(e) => setUseAi(e.target.checked)} />
              <span className="cg-toggle-track" />
              <span className="cg-toggle-label">Use AI</span>
            </label>

            {rerunErr && (
              <div className="cg-alert cg-alert--error" role="alert">
                <span>{rerunErr}</span>
              </div>
            )}

            <button
              className="cg-btn cg-btn--secondary cg-btn--sm"
              onClick={handleRerun}
              disabled={rerunning}
            >
              {rerunning ? <><span className="cg-spinner" aria-hidden="true" /> Regenerating…</> : 'Regenerate'}
            </button>
          </div>

          {/* Music library toggle */}
          <div className="cg-card cg-gallery-sidebar-card">
            <button
              className="cg-btn cg-btn--ghost cg-btn--sm"
              onClick={() => setShowMusic(!showMusic)}
              style={{ alignSelf: 'flex-start', marginBottom: showMusic ? 'var(--cg-space-4)' : 0 }}
            >
              {showMusic ? '▾' : '▸'} Music library ({library.tracks?.length || 0} tracks)
            </button>
            {showMusic && (
              <MusicLibraryPanel library={library} onChanged={onLibraryChange} />
            )}
          </div>
        </aside>

        {/* Clip grid */}
        <section>
          {clips.length === 0 ? (
            <div className="cg-empty">
              <span className="cg-empty-icon"><LeafTrio size={64} /></span>
              <p className="cg-heading-sm">No clips found</p>
              <p className="cg-text-sm cg-text-muted">Try a shorter minimum clip length in the sidebar and regenerate.</p>
            </div>
          ) : (
            <div className="cg-grid-clips">
              {clips.map((c) => (
                <GalleryClipCard
                  key={`${c.id}-${c.version || 0}`}
                  jobId={jobId}
                  clip={c}
                  onEdit={onEdit}
                  onExport={onExport}
                  onUpdated={onClipUpdated}
                />
              ))}
            </div>
          )}

          {result?.disclaimer && (
            <p className="cg-text-xs cg-text-muted cg-gallery-disclaimer">
              {result.disclaimer}
            </p>
          )}
        </section>
      </div>
    </main>
  );
}

