import React, { useState, useEffect, useRef } from 'react';
import { getJSON } from '../api.js';
import { CopyEditor, ThumbnailMaker } from './ContentTools.jsx';
import './ExportStudioModal.css';

export default function ExportStudioModal({ jobId, clip, onClose, onConfirmed, onChooseText }) {
  const [ticked, setTicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
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

  const needsDecision = !!clip.text?.needs_decision;

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
            <h2 className="cg-heading-md">Export Short Studio</h2>
            <span className="cg-text-xs cg-text-muted">Vertical 9:16 MP4, 1080 × 1920</span>
          </div>
          <button className="cg-btn cg-btn--icon cg-btn--secondary" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {/* 1. What you get: exactly what CocoGenie produces (there are no quality options to choose) */}
        <div className="cg-export-section">
          <label className="cg-label">Your file</label>
          <p className="cg-text-sm">MP4 video · 1080 × 1920 (9:16) · H.264 video with AAC audio</p>
        </div>

        {/* 2. Copyright Verification Checklist */}
        <div className="cg-export-section">
          <div className="cg-checklist-title-row">
            <label className="cg-label">Copyright & Rights Verification</label>
            <span className="cg-badge cg-badge--warning">Required before download</span>
          </div>
          <p className="cg-text-xs cg-text-muted" style={{ marginBottom: 8 }}>
            Confirm these items to unlock the download. Your confirmations are saved in a rights report you can download.
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

        {/* 3. Title, description and hashtags: yours, or an AI draft you edit and save */}
        <div className="cg-export-section">
          <label className="cg-label">Title, description & hashtags</label>
          <CopyEditor jobId={jobId} clipId={clip.id} />
        </div>

        {/* 4. Thumbnail: a real frame of the clip, with your text */}
        <div className="cg-export-section">
          <label className="cg-label">Thumbnail</label>
          <ThumbnailMaker jobId={jobId} clipId={clip.id} confirmed={clip.confirmed} />
        </div>

        {needsDecision && (
          <div className="cg-alert cg-alert--warn" role="alert">
            <span>
              The speech in this clip could not be trusted, so it has no captions. Choose a headline of
              your own, or export without text, before downloading.
              {onChooseText && (
                <> <button type="button" className="cg-btn cg-btn--sm cg-btn--secondary"
                  onClick={() => onChooseText(clip)}>Choose text</button></>
              )}
            </span>
          </div>
        )}

        {error && (
          <div className="cg-alert cg-alert--error" role="alert">
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
            Rights Report (JSON)
          </a>
          <div style={{ flex: 1 }} />
          <button className="cg-btn cg-btn--secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="cg-btn cg-btn--primary"
            onClick={handleConfirmAndDownload}
            disabled={!allTicked || busy || needsDecision}
          >
            {busy ? (
              <><span className="cg-spinner" /> Preparing…</>
            ) : (
              '↓ Download MP4'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

