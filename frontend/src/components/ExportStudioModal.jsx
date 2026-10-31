import React, { useState, useEffect, useRef } from 'react';
import { getJSON } from '../api.js';
import './ExportStudioModal.css';

export default function ExportStudioModal({ jobId, clip, onClose, onConfirmed }) {
  const [resolution, setResolution] = useState('1080p');
  const [codec, setCodec] = useState('h264');
  const [bitrate, setBitrate] = useState('high');
  const [ticked, setTicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copiedMeta, setCopiedMeta] = useState(false);
  const dialogRef = useRef(null);

  const base = `/api/jobs/${jobId}/clips/${clip.id}`;

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    el.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const toggle = (id) => {
    setTicked((t) => t.includes(id) ? t.filter((x) => x !== id) : [...t, id]);
  };

  const checklistItems = clip.checklist || [];
  const allTicked = checklistItems.length === 0 || checklistItems.every((i) => ticked.includes(i.id));

  const handleConfirmAndDownload = async () => {
    setBusy(true);
    setError('');
    try {
      const updated = await getJSON(`${base}/checklist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: ticked }),
      });
      if (onConfirmed) onConfirmed(updated);
      // Trigger actual file download
      window.location.href = `${base}/download`;
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };

  const socialTitle = clip.title || `Viral Highlight #${clip.id}`;
  const socialDescription = `${clip.title}\n\n${clip.reason || ''}\n\n#shorts #podcast #viral #clipgenie\n\n${clip.credits || ''}`;

  const handleCopyMeta = async () => {
    try {
      await navigator.clipboard.writeText(socialDescription);
      setCopiedMeta(true);
      setTimeout(() => setCopiedMeta(false), 1800);
    } catch {
      // fallback
    }
  };

  return (
    <div
      className="cg-modal-backdrop"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="Export Video Studio Modal"
    >
      <div className="cg-modal cg-export-studio-modal" ref={dialogRef} tabIndex={-1}>
        <div className="cg-export-modal-header">
          <div>
            <h2 className="cg-heading-md">📤 Export Short Studio</h2>
            <span className="cg-text-xs cg-text-muted">High-fidelity 9:16 vertical render</span>
          </div>
          <button className="cg-btn cg-btn--icon cg-btn--secondary" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {/* 1. Format & Resolution Settings */}
        <div className="cg-export-section">
          <label className="cg-label">Render Quality & Codec</label>
          <div className="cg-export-options-grid">
            <div className="cg-export-option-group">
              <span className="cg-text-xs cg-text-secondary">Resolution</span>
              <select className="cg-select" value={resolution} onChange={(e) => setResolution(e.target.value)}>
                <option value="1080p">1080 × 1920 (Standard HD)</option>
                <option value="4k">2160 × 3840 (4K Ultra-Sharp)</option>
              </select>
            </div>
            <div className="cg-export-option-group">
              <span className="cg-text-xs cg-text-secondary">Codec</span>
              <select className="cg-select" value={codec} onChange={(e) => setCodec(e.target.value)}>
                <option value="h264">H.264 (Maximum Compatibility)</option>
                <option value="hevc">HEVC / H.265 (High Efficiency)</option>
              </select>
            </div>
            <div className="cg-export-option-group">
              <span className="cg-text-xs cg-text-secondary">Bitrate</span>
              <select className="cg-select" value={bitrate} onChange={(e) => setBitrate(e.target.value)}>
                <option value="high">16 Mbps (High Dynamic Range)</option>
                <option value="normal">8 Mbps (Standard Web)</option>
              </select>
            </div>
          </div>
        </div>

        {/* 2. Copyright Verification Checklist */}
        <div className="cg-export-section">
          <div className="cg-checklist-title-row">
            <label className="cg-label">📋 Copyright & Rights Verification</label>
            <span className="cg-badge cg-badge--warning">Required by Law</span>
          </div>
          <p className="cg-text-xs cg-text-muted" style={{ marginBottom: 8 }}>
            Confirm these items to authorize the render and generate your tamper-evident rights report.
          </p>

          <div className="cg-export-checklist">
            {checklistItems.map((item) => {
              const checked = ticked.includes(item.id);
              return (
                <label
                  key={item.id}
                  className={`cg-checklist-item ${checked ? 'cg-checklist-item--checked' : ''}`}
                >
                  <div className={`cg-checklist-box ${checked ? 'cg-checklist-box--checked' : ''}`}>
                    {checked && <span>✓</span>}
                  </div>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(item.id)}
                    className="cg-checklist-radio"
                    disabled={busy}
                  />
                  <span className="cg-checklist-text cg-text-sm">{item.text}</span>
                </label>
              );
            })}
          </div>
        </div>

        {/* 3. Social Publishing Metadata */}
        <div className="cg-export-section">
          <div className="cg-checklist-title-row">
            <label className="cg-label">📱 Social Metadata & Attribution</label>
            <button
              type="button"
              className="cg-btn cg-btn--sm cg-btn--secondary"
              onClick={handleCopyMeta}
            >
              {copiedMeta ? '✓ Copied' : '📋 Copy All Metadata'}
            </button>
          </div>
          <div className="cg-meta-preview-box">
            <p className="cg-meta-preview-title"><strong>Title:</strong> {socialTitle}</p>
            <p className="cg-meta-preview-desc"><strong>Tags:</strong> #shorts #podcast #tech #viral</p>
            {clip.credits && (
              <p className="cg-meta-preview-credits"><strong>Attribution:</strong> {clip.credits}</p>
            )}
          </div>
        </div>

        {error && (
          <div className="cg-alert cg-alert--error" role="alert">
            <span className="cg-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {/* Actions Bar */}
        <div className="cg-export-modal-actions">
          <a
            className="cg-btn cg-btn--secondary cg-btn--sm"
            href={`${base}/report`}
            download
            title="Download JSON provenance record"
          >
            🗒 Rights Report (JSON)
          </a>
          <div style={{ flex: 1 }} />
          <button className="cg-btn cg-btn--secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="cg-btn cg-btn--primary"
            onClick={handleConfirmAndDownload}
            disabled={!allTicked || busy}
          >
            {busy ? (
              <><span className="cg-spinner" /> Encoding…</>
            ) : (
              '↓ Render & Download MP4'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

